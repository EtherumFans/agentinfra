"""STT Service — FunASR Paraformer + medical term fuzzy matching.

Replaces openai-whisper with FunASR Paraformer (Alibaba DAMO Academy)
optimized for Chinese medical speech recognition.

Key improvements over Whisper:
- Paraformer is state-of-the-art for Chinese ASR
- Post-processing fuzzy matching against 15,000+ medical terms
  (standard Paraformer has NO native hotword API; post-processing
   is the correct and more reliable way to boost medical accuracy)
- GPU-accelerated with fp16
- Better Chinese punctuation restoration
- VAD (Voice Activity Detection) built-in

How medical term boosting works:
1. Paraformer produces raw transcription
2. Text is segmented into n-grams (2-10 chars)
3. Each n-gram is checked against 15K medical term list
4. If a candidate is within edit_distance=1 of a known term, it's corrected
5. This approach is ASR-engine-agnostic and empirically more reliable
   than model-level hotword biasing
"""
import array
import io
import logging
import math
import re
import threading
import time
import os
import sys
import tempfile
import wave
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from app.config import settings

logger = logging.getLogger(__name__)

_STT_ENGINE_DISABLED = "No approved local STT engine is enabled."
_STT_TRANSCRIPTION_FAILED = "Local STT transcription failed."

# Singleton model cache — protected by _model_lock
_stt_model = None           # Batch: VAD + Punc pipeline
_stt_streaming_model = None # Streaming: chunked incremental
_stt_model_name: str = ""

_FUNASR_BATCH_MODEL = (
    "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-"
    "common-vocab8404-pytorch@v2.0.4"
)
_FUNASR_STREAMING_MODEL = (
    "iic/speech_paraformer-large_asr_nat-zh-cn-16k-"
    "common-vocab8404-pytorch@v2.0.4"
)
_LAST_STT_TELEMETRY: ContextVar[dict[str, Any] | None] = ContextVar(
    "icoder_last_stt_telemetry", default=None,
)


@dataclass(frozen=True, slots=True)
class MultichannelAudioInfo:
    """Verified PCM WAV properties used by prerecorded multichannel STT."""

    channels: int
    sample_rate: int
    sample_width: int
    frame_count: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class STTChannelTranscript:
    """One independently recognized channel from a multichannel recording."""

    channel: int
    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class STTTranscriptSegment:
    """One provider-grounded phrase/utterance timestamp in milliseconds."""

    text: str
    start_ms: int
    end_ms: int


_LAST_STT_SEGMENTS: ContextVar[tuple[STTTranscriptSegment, ...]] = ContextVar(
    "icoder_last_stt_segments", default=(),
)

# Term index — protected by _term_lock
_term_index_loaded: bool = False
_term_index: dict[int, set[str]] = {}  # length -> set of terms
_term_trie: dict = {}

# Thread safety locks
_model_lock = threading.Lock()
_term_lock = threading.Lock()

HOTWORD_PATH = Path(__file__).parent.parent.parent / "data" / "medical_hotwords.txt"


def reset_stt_inference_telemetry() -> None:
    """Clear task-local ASR accounting before one inference attempt."""
    _LAST_STT_TELEMETRY.set(None)


def get_stt_inference_telemetry() -> dict[str, Any]:
    """Return a copy of task-local, content-free ASR accounting."""
    return dict(_LAST_STT_TELEMETRY.get() or {})


def reset_stt_transcript_segments() -> None:
    """Clear task-local phrase timestamps before one inference attempt."""

    _LAST_STT_SEGMENTS.set(())


def get_stt_transcript_segments() -> tuple[STTTranscriptSegment, ...]:
    """Return provider-grounded phrase timestamps without mutable aliases."""

    return tuple(_LAST_STT_SEGMENTS.get())


def _timestamp_milliseconds(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numeric) or numeric < 0 or numeric > 7_200_000:
        return None
    rounded = round(numeric)
    if abs(numeric - rounded) > 0.001:
        return None
    return int(rounded)


def _validated_provider_segments(value: object) -> tuple[STTTranscriptSegment, ...]:
    """Accept only monotonic, bounded FunASR phrase timestamps."""

    if not isinstance(value, list) or not value or len(value) > 10_000:
        return ()
    segments: list[STTTranscriptSegment] = []
    previous_end = 0
    total_characters = 0
    for item in value:
        if not isinstance(item, dict):
            return ()
        text = item.get("text")
        if not isinstance(text, str):
            text = item.get("sentence")
        if not isinstance(text, str):
            return ()
        text = text.strip()
        start_ms = _timestamp_milliseconds(item.get("start"))
        end_ms = _timestamp_milliseconds(item.get("end"))
        if (
            not text
            or start_ms is None
            or end_ms is None
            or end_ms <= start_ms
            or start_ms < previous_end
        ):
            return ()
        total_characters += len(text)
        if total_characters > 1_000_000:
            return ()
        corrected = _restore_punctuation(_fuzzy_correct(text, max_edit=1))
        segments.append(
            STTTranscriptSegment(
                text=corrected,
                start_ms=start_ms,
                end_ms=end_ms,
            )
        )
        previous_end = end_ms
    return tuple(segments)


def _validated_whisper_segments(value: object) -> tuple[STTTranscriptSegment, ...]:
    """Normalize optional Whisper second-based segments to Corti milliseconds."""

    if not isinstance(value, list) or not value or len(value) > 10_000:
        return ()
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            return ()
        try:
            start = float(item.get("start")) * 1000
            end = float(item.get("end")) * 1000
        except (TypeError, ValueError, OverflowError):
            return ()
        normalized.append({"text": item.get("text"), "start": start, "end": end})
    return _validated_provider_segments(normalized)


def _record_stt_inference_telemetry(
    *,
    provider: str,
    model: str,
    latency_ms: int,
    status: str,
    fallback_used: bool,
    streaming: bool,
) -> None:
    def identifier(value: str, limit: int = 256) -> str:
        text = str(value or "").strip()
        if not text or len(text) > limit:
            return ""
        return text if all(
            char.isascii()
            and (char.isalnum() or char in "._:/@+-")
            for char in text
        ) else ""

    safe_status = identifier(status, 32)
    safe_provider = identifier(provider, 64)
    safe_model = identifier(model)
    try:
        safe_latency = max(0, min(int(latency_ms), 86_400_000))
    except (TypeError, ValueError, OverflowError):
        safe_latency = 0
    telemetry: dict[str, Any] = {
        "schema": "icoder/stt-inference-telemetry/v1",
        "latency_ms": safe_latency,
        "fallback_used": bool(fallback_used),
        "streaming": bool(streaming),
    }
    if safe_provider:
        telemetry["provider"] = safe_provider
    if safe_model:
        telemetry["model"] = safe_model
    if safe_status:
        telemetry["status"] = safe_status
    _LAST_STT_TELEMETRY.set(telemetry)


async def transcribe_bytes_with_telemetry(
    audio_bytes: bytes,
    media_type: str,
    *,
    keyterms: Sequence[str] = (),
) -> tuple[str, str, dict[str, Any]]:
    """Compatibility wrapper returning content-free task-local telemetry."""
    reset_stt_inference_telemetry()
    if keyterms:
        text, error = await transcribe_bytes(
            audio_bytes,
            media_type,
            keyterms=keyterms,
        )
    else:
        text, error = await transcribe_bytes(audio_bytes, media_type)
    return text, error, get_stt_inference_telemetry()


def inspect_multichannel_pcm_wav(
    audio_bytes: bytes,
    media_type: str,
    *,
    expected_channels: int = 2,
) -> MultichannelAudioInfo:
    """Validate the bounded prerecorded multichannel format we can honor.

    Corti recommends aligned 16-bit/16 kHz PCM with one participant per
    channel.  The local verified batch implementation intentionally accepts
    only an uncompressed PCM WAV container with exactly two channels.  Encoded
    stereo containers require a separately governed decoder and fail closed.
    """
    normalized = (media_type or "").split(";", 1)[0].strip().casefold()
    if normalized not in {"audio/wav", "audio/x-wav"}:
        raise ValueError("multichannel_pcm_wav_required")
    if expected_channels != 2:
        raise ValueError("multichannel_two_channels_required")
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as reader:
            channels = reader.getnchannels()
            sample_rate = reader.getframerate()
            sample_width = reader.getsampwidth()
            frame_count = reader.getnframes()
            compression = reader.getcomptype()
    except (EOFError, OSError, wave.Error) as exc:
        raise ValueError("multichannel_wav_invalid") from exc
    if compression != "NONE":
        raise ValueError("multichannel_pcm_wav_required")
    if channels != expected_channels:
        raise ValueError("multichannel_channel_count_mismatch")
    if sample_rate != 16000 or sample_width != 2:
        raise ValueError("multichannel_pcm_16khz_16bit_required")
    if frame_count <= 0:
        raise ValueError("multichannel_wav_empty")
    return MultichannelAudioInfo(
        channels=channels,
        sample_rate=sample_rate,
        sample_width=sample_width,
        frame_count=frame_count,
        duration_ms=max(1, round(frame_count * 1000 / sample_rate)),
    )


def _split_multichannel_wav_to_temporary_mono_files(
    audio_bytes: bytes,
    info: MultichannelAudioInfo,
) -> list[str]:
    """Split interleaved PCM into bounded-memory mono WAV temp files."""
    paths: list[str] = []
    writers: list[wave.Wave_write] = []
    try:
        for channel in range(info.channels):
            handle = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=f"-channel-{channel}.wav",
            )
            path = handle.name
            handle.close()
            paths.append(path)
            writer = wave.open(path, "wb")
            writer.setnchannels(1)
            writer.setsampwidth(info.sample_width)
            writer.setframerate(info.sample_rate)
            writers.append(writer)

        with wave.open(io.BytesIO(audio_bytes), "rb") as reader:
            while True:
                frames = reader.readframes(8192)
                if not frames:
                    break
                samples = array.array("h")
                samples.frombytes(frames)
                if sys.byteorder != "little":
                    samples.byteswap()
                for channel, writer in enumerate(writers):
                    selected = samples[channel::info.channels]
                    if sys.byteorder != "little":
                        selected.byteswap()
                    writer.writeframesraw(selected.tobytes())
        for writer in writers:
            writer.close()
        writers.clear()
        return paths
    except Exception:
        for writer in writers:
            try:
                writer.close()
            except Exception:
                pass
        for path in paths:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise


def _aggregate_multichannel_telemetry(
    telemetry_items: Sequence[dict[str, Any]],
    *,
    status: str,
) -> dict[str, Any]:
    """Aggregate content-free per-channel telemetry without term or text data."""
    result: dict[str, Any] = {
        "schema": "icoder/stt-inference-telemetry/v1",
        "latency_ms": min(
            86_400_000,
            sum(
                item.get("latency_ms", 0)
                for item in telemetry_items
                if isinstance(item.get("latency_ms"), int)
                and not isinstance(item.get("latency_ms"), bool)
                and item.get("latency_ms", 0) >= 0
            ),
        ),
        "status": status,
        "fallback_used": any(item.get("fallback_used") is True for item in telemetry_items),
        "streaming": False,
    }
    for key in ("provider", "model"):
        values = {
            item.get(key)
            for item in telemetry_items
            if isinstance(item.get(key), str) and item.get(key)
        }
        if len(values) == 1:
            result[key] = values.pop()
    return result


async def validate_prerecorded_multichannel_audio(
    audio_bytes: bytes,
    media_type: str,
    *,
    expected_channels: int = 2,
) -> object:
    """Validate native PCM WAV or probe a declared encoded two-channel file."""

    if expected_channels != 2:
        raise ValueError("multichannel_two_channels_required")
    normalized = (media_type or "").split(";", 1)[0].strip().casefold()
    if normalized in {"audio/wav", "audio/x-wav"}:
        return inspect_multichannel_pcm_wav(
            audio_bytes,
            media_type,
            expected_channels=expected_channels,
        )
    from app.services.prerecorded_media_decoder import (
        probe_prerecorded_multichannel_audio,
    )

    return await probe_prerecorded_multichannel_audio(
        audio_bytes,
        media_type=media_type,
    )


async def _recognize_multichannel_paths(
    paths: Sequence[str],
    *,
    duration_ms: int,
    keyterms: Sequence[str],
) -> tuple[list[STTChannelTranscript], str, dict[str, Any]]:
    rows: list[STTChannelTranscript] = []
    telemetry_items: list[dict[str, Any]] = []
    for channel, path in enumerate(paths):
        reset_stt_inference_telemetry()
        reset_stt_transcript_segments()
        if keyterms:
            text, error = await transcribe_audio(path, keyterms=keyterms)
        else:
            text, error = await transcribe_audio(path)
        telemetry_items.append(get_stt_inference_telemetry())
        if not text:
            if error == "No speech detected":
                continue
            return (
                [],
                error or _STT_TRANSCRIPTION_FAILED,
                _aggregate_multichannel_telemetry(
                    telemetry_items,
                    status="failed",
                ),
            )
        segments = get_stt_transcript_segments()
        if segments and all(item.end_ms <= duration_ms + 250 for item in segments):
            for item in segments:
                rows.append(
                    STTChannelTranscript(
                        channel=channel,
                        text=item.text,
                        start_ms=item.start_ms,
                        end_ms=min(duration_ms, item.end_ms),
                    )
                )
        else:
            rows.append(
                STTChannelTranscript(
                    channel=channel,
                    text=text,
                    start_ms=0,
                    end_ms=duration_ms,
                )
            )
    if not rows:
        return (
            [],
            "No speech detected",
            _aggregate_multichannel_telemetry(telemetry_items, status="empty"),
        )
    return (
        rows,
        "",
        _aggregate_multichannel_telemetry(telemetry_items, status="complete"),
    )


async def transcribe_multichannel_bytes_with_telemetry(
    audio_bytes: bytes,
    media_type: str,
    *,
    expected_channels: int = 2,
    keyterms: Sequence[str] = (),
) -> tuple[list[STTChannelTranscript], str, dict[str, Any]]:
    """Decode/split two aligned channels and recognize each independently.

    One silent channel is valid and simply emits no transcript row. Any real
    inference error fails the entire request so callers never receive a
    misleading partially processed clinical conversation.
    """

    normalized = (media_type or "").split(";", 1)[0].strip().casefold()
    if normalized in {"audio/wav", "audio/x-wav"}:
        info = inspect_multichannel_pcm_wav(
            audio_bytes,
            media_type,
            expected_channels=expected_channels,
        )
        paths = _split_multichannel_wav_to_temporary_mono_files(audio_bytes, info)
        try:
            return await _recognize_multichannel_paths(
                paths,
                duration_ms=info.duration_ms,
                keyterms=keyterms,
            )
        finally:
            for path in paths:
                try:
                    os.unlink(path)
                except OSError:
                    logger.warning("Failed to remove a temporary STT channel upload")

    if expected_channels != 2:
        raise ValueError("multichannel_two_channels_required")
    from app.services.prerecorded_media_decoder import (
        PrerecordedMediaDecoderError,
        decoded_prerecorded_multichannel_wavs,
    )

    try:
        async with decoded_prerecorded_multichannel_wavs(
            audio_bytes,
            media_type=media_type,
        ) as decoded:
            return await _recognize_multichannel_paths(
                decoded.channel_paths,
                duration_ms=decoded.duration_ms,
                keyterms=keyterms,
            )
    except PrerecordedMediaDecoderError as exc:
        return (
            [],
            exc.reason,
            _aggregate_multichannel_telemetry((), status="failed"),
        )


def apply_requested_replacements(text: str, replacements: list[dict[str, str]]) -> str:
    """Apply caller-requested terminology replacements case-insensitively.

    Corti describes ``find`` as case-insensitive.  Keeping this operation in
    one helper ensures synchronous, background and recovered jobs use exactly
    the same semantics. Empty ``find`` values are ignored defensively even
    though the public request schema rejects them.
    """
    result = text
    for replacement in replacements:
        find = str(replacement.get("find", ""))
        if find:
            result = re.sub(
                re.escape(find),
                lambda _match, value=str(replacement.get("replace", "")): value,
                result,
                flags=re.IGNORECASE,
            )
    return result


_ZH_DICTATION_PUNCTUATION: tuple[tuple[str, str], ...] = (
    ("左双引号", "“"),
    ("右双引号", "”"),
    ("左单引号", "‘"),
    ("右单引号", "’"),
    ("左括号", "（"),
    ("右括号", "）"),
    ("省略号", "……"),
    ("感叹号", "！"),
    ("叹号", "！"),
    ("问号", "？"),
    ("句号", "。"),
    ("逗号", "，"),
    ("冒号", "："),
    ("分号", "；"),
    ("顿号", "、"),
)


def apply_dictation_punctuation(
    text: str,
    *,
    primary_language: str,
    enabled: bool,
) -> str:
    """Normalize explicit Chinese punctuation words in dictation mode.

    This is intentionally a deterministic post-ASR transform, not a claim of
    model-level command recognition. It is disabled unless the caller opts in,
    and it only runs for the verified Chinese runtime. Longer command phrases
    are ordered before their suffixes so ``感叹号`` cannot be partially
    rewritten as ``感！``.
    """
    if not enabled or not primary_language.lower().startswith("zh"):
        return text
    result = text
    for phrase, symbol in _ZH_DICTATION_PUNCTUATION:
        result = result.replace(phrase, symbol)
    # ASR may emit spaces around a spoken punctuation phrase. Chinese document
    # punctuation does not retain those separator spaces.
    result = re.sub(r"[ \t]+([，。？！：；、（）“”‘’])", r"\1", result)
    result = re.sub(r"([，。？！：；、（“‘])[ \t]+", r"\1", result)
    return result


async def transcribe_bytes(
    audio_bytes: bytes,
    media_type: str,
    *,
    keyterms: Sequence[str] = (),
) -> tuple[str, str]:
    """Transcribe an uploaded recording without retaining it on disk.

    A short-lived file is required by FunASR/Whisper.  It is deleted in all
    success and failure paths; callers receive an explicit error instead of a
    fabricated transcript when no local STT engine is available.
    """
    normalized = (media_type or "application/octet-stream").split(";", 1)[0].lower()
    if normalized == "audio/pcm":
        from app.services.stream_audio_format import parse_declared_stream_audio_format

        try:
            declared = parse_declared_stream_audio_format(media_type)
        except ValueError:
            return "", _STT_TRANSCRIPTION_FAILED
        if (
            declared is None
            or declared.rate != 16000
            or declared.channels != 1
            or declared.bits != 16
            or declared.endian != "little"
            or declared.encoding != "sint"
            or len(audio_bytes) % 2
        ):
            return "", _STT_TRANSCRIPTION_FAILED
        output = io.BytesIO()
        with wave.open(output, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(audio_bytes)
        audio_bytes = output.getvalue()
        normalized = "audio/wav"

    suffix_by_type = {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mpeg3": ".mp3",
        "audio/mp4": ".m4a",
        "audio/m4a": ".m4a",
        "audio/ogg": ".ogg",
        "audio/opus": ".opus",
        "audio/vorbis": ".ogg",
        "audio/flac": ".flac",
    }
    suffix = suffix_by_type.get(normalized, ".bin")
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(audio_bytes)
            tmp_path = handle.name
        if keyterms:
            return await transcribe_audio(tmp_path, keyterms=keyterms)
        return await transcribe_audio(tmp_path)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.warning("Failed to remove temporary STT upload %s", tmp_path)


def _build_term_index(terms: list[str]):
    """Build length-indexed + trie structures for O(1) lookup.

    Must be called while holding _term_lock.
    """
    global _term_index, _term_trie
    idx: dict[int, set[str]] = {}
    trie: dict = {}
    for t in terms:
        length = len(t)
        if length not in idx:
            idx[length] = set()
        idx[length].add(t)
        # Build trie
        node = trie
        for ch in t:
            if ch not in node:
                node[ch] = {}
            node = node[ch]
        node["$"] = t  # terminal marker
    _term_index = idx
    _term_trie = trie


def _load_terms() -> list[str]:
    """Load medical terms for post-processing fuzzy matching (thread-safe)."""
    global _term_index_loaded

    # Fast path: check without lock
    if _term_index_loaded:
        return []

    with _term_lock:
        # Double-check after acquiring lock
        if _term_index_loaded:
            return []

        terms = []
        if HOTWORD_PATH.exists():
            with open(HOTWORD_PATH, "r", encoding="utf-8") as f:
                terms = [line.strip() for line in f if 2 <= len(line.strip()) <= 15]
            logger.info(f"Loaded {len(terms)} medical terms from {HOTWORD_PATH}")
        else:
            terms = [
                "主诉", "现病史", "既往史", "查体", "辅助检查", "初步诊断",
                "入院诊断", "出院诊断", "鉴别诊断", "高血压", "糖尿病",
                "冠心病", "脑梗死", "肺炎", "骨质疏松", "骨折", "肿瘤",
                "胆囊切除术", "阑尾切除术", "全髋关节置换术",
                "冠状动脉支架植入术", "心电图", "超声", "CT", "磁共振",
            ]

        _build_term_index(terms)
        _term_index_loaded = True
        return terms


def _edit_distance(s1: str, s2: str) -> int:
    """Levenshtein distance — fast for short strings."""
    if s1 == s2:
        return 0
    if len(s1) > len(s2):
        s1, s2 = s2, s1
    # s1 is shorter
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(
                prev[j + 1] + 1,       # delete
                curr[j] + 1,            # insert
                prev[j] + (c1 != c2),   # substitute
            ))
        prev = curr
    return prev[-1]


def _fuzzy_correct(text: str, max_edit: int = 1) -> str:
    """Scan text and correct misrecognized medical terms via fuzzy matching.

    Algorithm:
    1. Slide a window of 2-10 characters across the text
    2. For each window, check if it's in the term index (exact match -> skip)
    3. If not, find terms of similar length with edit distance <= max_edit
    4. Replace with the best match (highest character overlap)
    """
    if not _term_index_loaded:
        _load_terms()

    corrections: list[tuple[int, int, str]] = []  # (start, end, replacement)
    text_len = len(text)

    # Sliding window: lengths 2-10
    for length in range(2, min(11, text_len + 1)):
        candidates = _term_index.get(length, set())
        if not candidates:
            continue
        for start in range(text_len - length + 1):
            window = text[start:start + length]
            # Check exact match first (fast path)
            if window in candidates:
                continue  # Already correct

            # Fuzzy match
            best_term = None
            best_score = 999
            for term in candidates:
                # Quick pre-filter: first char must match or be similar
                if window[0] != term[0]:
                    continue
                dist = _edit_distance(window, term)
                if dist <= max_edit and dist < best_score:
                    best_score = dist
                    best_term = term
                    if dist == 1:
                        break  # Good enough

            if best_term and best_score <= max_edit:
                corrections.append((start, start + length, best_term))

    # Apply corrections from right to left (to preserve indices)
    corrections.sort(key=lambda x: -x[0])
    result = text
    for start, end, repl in corrections:
        # Only replace if not overlapping with a previous correction
        if repl not in result[max(0, start - 5):end + 5]:
            result = result[:start] + repl + result[end:]

    return result


def _get_stt_model():
    """Load FunASR Paraformer batch model (VAD + Punc pipeline) — thread-safe.

    Used for final transcription of complete audio files.
    """
    global _stt_model
    if not settings.ICODER_ENABLE_LOCAL_STT:
        raise ModuleNotFoundError("local STT is disabled by runtime policy")
    if _stt_model is not None:
        return _stt_model

    with _model_lock:
        if _stt_model is not None:
            return _stt_model

        from funasr import AutoModel
        device = _get_device()
        logger.info(f"Loading FunASR Paraformer (batch, VAD+punc) on {device}...")

        _stt_model = AutoModel(
            model="iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            model_revision="v2.0.4",
            vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
            vad_model_revision="v2.0.4",
            punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
            punc_model_revision="v2.0.4",
            device=device,
            disable_update=True,
        )
        logger.info(f"FunASR Paraformer batch model loaded on {device}")
        return _stt_model


def _get_stt_streaming_model():
    """Load FunASR Paraformer streaming model (chunked incremental) — thread-safe.

    Used for real-time interim transcription during recording.
    """
    global _stt_streaming_model
    if not settings.ICODER_ENABLE_LOCAL_STT:
        raise ModuleNotFoundError("local STT is disabled by runtime policy")
    if _stt_streaming_model is not None:
        return _stt_streaming_model

    with _model_lock:
        if _stt_streaming_model is not None:
            return _stt_streaming_model

        from funasr import AutoModel
        device = _get_device()
        logger.info(f"Loading FunASR Paraformer (streaming) on {device}...")

        _stt_streaming_model = AutoModel(
            model="iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            model_revision="v2.0.4",
            device=device,
            disable_update=True,
        )
        logger.info(f"FunASR Paraformer streaming model loaded on {device}")
        return _stt_streaming_model


def _get_device() -> str:
    """Determine the best available device for ASR inference."""
    if settings.STT_DEVICE != "auto":
        return settings.STT_DEVICE
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda:0"
    except ImportError:
        pass
    return "cpu"


async def transcribe_streaming(audio_path: str) -> tuple[str, str]:
    """Real-time streaming transcription for interim results.

    Uses base Paraformer without VAD (VAD blocks streaming).
    Punctuation restored via _restore_punctuation().
    Fuzzy medical term correction applied.

    Args:
        audio_path: Path to audio file (WAV, 16kHz mono)

    Returns:
        (text, error_message)
    """
    start = time.time()
    try:
        model = _get_stt_streaming_model()
        _load_terms()

        # Streaming mode: chunk_size enables incremental processing
        result = model.generate(
            input=audio_path,
            language="zh",
            use_itn=True,
            chunk_size=1600,  # 100ms chunks at 16kHz
        )

        text = ""
        if isinstance(result, list) and len(result) > 0:
            item = result[0]
            if isinstance(item, dict):
                text = item.get("text", "")
            elif isinstance(item, str):
                text = item

        if not text:
            _record_stt_inference_telemetry(
                provider="funasr",
                model=_FUNASR_STREAMING_MODEL,
                latency_ms=int((time.time() - start) * 1000),
                status="empty",
                fallback_used=False,
                streaming=True,
            )
            return "", "No speech detected"

        # Post-process
        corrected = _fuzzy_correct(text, max_edit=1)
        final_text = _restore_punctuation(corrected)

        elapsed = int((time.time() - start) * 1000)
        _record_stt_inference_telemetry(
            provider="funasr",
            model=_FUNASR_STREAMING_MODEL,
            latency_ms=elapsed,
            status="complete",
            fallback_used=False,
            streaming=True,
        )
        logger.info(f"Streaming ASR: {len(final_text)} chars in {elapsed}ms")
        return final_text, ""

    except Exception as error:
        _record_stt_inference_telemetry(
            provider="funasr",
            model=_FUNASR_STREAMING_MODEL,
            latency_ms=int((time.time() - start) * 1000),
            status="failed",
            fallback_used=False,
            streaming=True,
        )
        logger.warning("Streaming ASR failed type=%s", type(error).__name__)
        return "", _STT_TRANSCRIPTION_FAILED


async def transcribe_audio(
    audio_path: str,
    *,
    keyterms: Sequence[str] = (),
) -> tuple[str, str]:
    """Transcribe audio to Chinese text using FunASR Paraformer + fuzzy term correction.

    Pipeline:
    1. Paraformer: raw audio -> Chinese text (with VAD + punctuation)
    2. Fuzzy matching: scan text against 15K medical term index
    3. Correction: replace misrecognized terms with closest medical term
    4. Punctuation: restore Chinese punctuation structure

    Args:
        audio_path: Path to audio file (WAV, 16kHz mono preferred)

    Returns:
        (text, error_message). If text is empty, error_message explains why.
    """
    start = time.time()
    reset_stt_transcript_segments()
    try:
        model = _get_stt_model()
        _load_terms()  # Ensure term index is built

        # FunASR accepts a list through the runtime ``hotword`` parameter. The
        # caller-provided order and case are preserved exactly; schema and SDK
        # boundaries already cap the list at 1,000 terms and each term at 50
        # characters. No term content is written to logs or telemetry.
        generate_options: dict[str, Any] = {
            "input": audio_path,
            "language": "zh",
            "use_itn": True,
            # Current Corti Transcripts rows are phrase/utterance records with
            # integer millisecond bounds. FunASR's batch VAD+punc pipeline can
            # return the corresponding sentence_info without another model
            # call; invalid/missing timing safely falls back to one whole-file
            # row at the multichannel boundary.
            "sentence_timestamp": True,
        }
        if keyterms:
            generate_options["hotword"] = list(keyterms)
        result = model.generate(
            **generate_options,
        )

        text = ""
        recognized_item: dict[str, Any] | None = None
        if isinstance(result, list) and len(result) > 0:
            item = result[0]
            if isinstance(item, dict):
                recognized_item = item
                text = item.get("text", "")
            elif isinstance(item, str):
                text = item

        if not text:
            logger.info("FunASR returned empty text")
            _record_stt_inference_telemetry(
                provider="funasr",
                model=_FUNASR_BATCH_MODEL,
                latency_ms=int((time.time() - start) * 1000),
                status="empty",
                fallback_used=False,
                streaming=False,
            )
            return "", "No speech detected"

        # Step 2: Fuzzy medical term correction
        corrected = _fuzzy_correct(text, max_edit=1)

        # Step 3: Punctuation restoration
        final_text = _restore_punctuation(corrected)
        provider_segments = _validated_provider_segments(
            recognized_item.get("sentence_info") if recognized_item else None
        )
        _LAST_STT_SEGMENTS.set(provider_segments)

        elapsed = int((time.time() - start) * 1000)
        _record_stt_inference_telemetry(
            provider="funasr",
            model=_FUNASR_BATCH_MODEL,
            latency_ms=elapsed,
            status="complete",
            fallback_used=False,
            streaming=False,
        )
        logger.info(
            "FunASR completed chars=%d latency_ms=%d corrected=%s",
            len(text),
            elapsed,
            corrected != text,
        )

        return final_text, ""

    except (ImportError, ModuleNotFoundError) as error:
        logger.warning(
            "FunASR unavailable type=%s; trying configured Whisper fallback",
            type(error).__name__,
        )
        return await _whisper_fallback(
            audio_path,
            started_at=start,
            keyterms=keyterms,
        )
    except Exception as error:
        _record_stt_inference_telemetry(
            provider="funasr",
            model=_FUNASR_BATCH_MODEL,
            latency_ms=int((time.time() - start) * 1000),
            status="failed",
            fallback_used=False,
            streaming=False,
        )
        logger.error("FunASR transcription failed type=%s", type(error).__name__)
        return "", _STT_TRANSCRIPTION_FAILED


async def _whisper_fallback(
    audio_path: str,
    *,
    started_at: float | None = None,
    keyterms: Sequence[str] = (),
) -> tuple[str, str]:
    """Fallback to Whisper + fuzzy term correction."""
    started = started_at if started_at is not None else time.time()
    model_name = str(settings.STT_WHISPER_MODEL or "")
    if not settings.ICODER_ENABLE_LOCAL_STT or not model_name:
        _record_stt_inference_telemetry(
            provider="local_stt",
            model=model_name,
            latency_ms=int((time.time() - started) * 1000),
            status="disabled",
            fallback_used=True,
            streaming=False,
        )
        return "", _STT_ENGINE_DISABLED
    try:
        import whisper
        model = whisper.load_model(model_name)
        device = _get_device()
        kwargs = {"language": "zh", "fp16": device != "cpu"}
        if keyterms:
            kwargs["initial_prompt"] = "、".join(keyterms)
        elif settings.STT_MEDICAL_TERMS_BOOST:
            kwargs["initial_prompt"] = _build_medical_prompt()
        result = model.transcribe(audio_path, **kwargs)
        text = result["text"].strip()
        if text:
            text = _restore_punctuation(text)
            text = _fuzzy_correct(text, max_edit=1)
        _LAST_STT_SEGMENTS.set(_validated_whisper_segments(result.get("segments")))
        _record_stt_inference_telemetry(
            provider="whisper",
            model=model_name,
            latency_ms=int((time.time() - started) * 1000),
            status="complete" if text else "empty",
            fallback_used=True,
            streaming=False,
        )
        return text, ""
    except Exception as error:
        _record_stt_inference_telemetry(
            provider="whisper",
            model=model_name,
            latency_ms=int((time.time() - started) * 1000),
            status="failed",
            fallback_used=True,
            streaming=False,
        )
        logger.warning("Whisper fallback failed type=%s", type(error).__name__)
        return "", _STT_TRANSCRIPTION_FAILED


def _build_medical_prompt() -> str:
    """Build medical context prompt for Whisper initial_prompt."""
    if HOTWORD_PATH.exists():
        with open(HOTWORD_PATH, "r", encoding="utf-8") as f:
            words = [line.strip() for line in f if line.strip()]
        return (
            "以下是医生和患者的临床对话转录。包含医学术语、诊断名称、手术名称。"
            "常见词汇：" + "、".join(words[:200])
        )
    return (
        "以下是医生和患者的临床对话转录。包含医学术语、诊断名称、手术名称、"
        "检查项目、药品名称等。常见词汇：主诉、现病史、既往史、查体、辅助检查、"
        "初步诊断、入院诊断、出院诊断、鉴别诊断、建议、处理、治疗、手术、用药。"
    )


def _restore_punctuation(text: str) -> str:
    """Restore basic Chinese punctuation structure."""
    if not text or not text.strip():
        return text
    transitions = [
        "查体", "体检", "辅助检查", "既往史", "个人史", "家族史",
        "初步诊断", "入院诊断", "出院诊断", "诊断", "鉴别诊断",
        "建议", "处理", "治疗", "手术", "操作", "用药", "医嘱",
    ]
    for t in transitions:
        text = text.replace(f" {t}", f"。{t}")
        text = text.replace(f"{t} ", f"{t}，")
    if text and text[-1] not in "。！？…）)":
        text = text.rstrip() + "。"
    text = text.replace("。。", "。").replace("，，", "，")
    return text
