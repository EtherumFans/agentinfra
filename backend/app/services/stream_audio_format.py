"""Bounded format validation for Corti-compatible streamed audio.

Encoded inputs are verified from their bounded initial container header. Raw
PCM has no header, so its rate, channels, sample width, endian and encoding are
strictly declared and its frame alignment is checked. No audio content is
logged or retained by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


_MIME_TO_CONTAINER = {
    "audio/ogg": "ogg",
    "audio/webm": "webm",
    "audio/opus": "ogg",
    "audio/vorbis": "ogg",
    "audio/mpeg": "mpeg",
    "audio/mp3": "mpeg",
    "audio/mpeg3": "mpeg",
    "audio/flac": "flac",
    "audio/mp4": "mp4",
    "audio/m4a": "mp4",
    "audio/pcm": "pcm",
}
_ALLOWED_CODECS = frozenset({"flac", "opus", "vorbis"})


@dataclass(frozen=True, slots=True)
class DeclaredStreamAudioFormat:
    mime_type: str
    container: str
    codec: str | None
    rate: int | None = None
    channels: int | None = None
    bits: int | None = None
    endian: str | None = None
    encoding: str | None = None

    @property
    def frame_bytes(self) -> int | None:
        if self.container != "pcm" or self.channels is None or self.bits is None:
            return None
        return self.channels * (self.bits // 8)

    @property
    def canonical_media_type(self) -> str:
        if self.container != "pcm":
            return self.mime_type
        return (
            f"audio/pcm; rate={self.rate}; channels={self.channels}; bits={self.bits}; "
            f"endian={self.endian}; encoding={self.encoding}"
        )


class StreamAudioProbeStatus(str, Enum):
    NEED_MORE = "need_more"
    SUPPORTED = "supported"
    INVALID = "invalid"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class StreamAudioProbe:
    status: StreamAudioProbeStatus
    resolved_mime_type: str | None = None
    container: str | None = None
    codec: str | None = None


def parse_declared_stream_audio_format(
    value: str | None,
) -> DeclaredStreamAudioFormat | None:
    if value is None:
        return None
    parts = [part.strip() for part in value.split(";")]
    mime_type = parts[0].casefold()
    container = _MIME_TO_CONTAINER.get(mime_type)
    if container is None:
        raise ValueError("stream_audio_mime_not_supported")
    if container == "pcm":
        parameters: dict[str, str] = {}
        for parameter in parts[1:]:
            if not parameter:
                continue
            key, separator, raw_value = parameter.partition("=")
            normalized_key = key.strip().casefold()
            if separator != "=" or normalized_key not in {
                "rate", "channels", "bits", "endian", "encoding",
            }:
                raise ValueError("stream_audio_parameter_not_supported")
            if normalized_key in parameters:
                raise ValueError("stream_audio_parameter_duplicated")
            parameters[normalized_key] = raw_value.strip().strip('"').casefold()
        if not {"rate", "channels", "bits"}.issubset(parameters):
            raise ValueError("stream_audio_pcm_parameter_required")
        try:
            rate = int(parameters["rate"])
            channels = int(parameters["channels"])
            bits = int(parameters["bits"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("stream_audio_pcm_parameter_invalid") from exc
        endian = parameters.get("endian", "little")
        encoding = parameters.get("encoding", "sint")
        if not 8000 <= rate <= 48000:
            raise ValueError("stream_audio_pcm_rate_invalid")
        if not 1 <= channels <= 8:
            raise ValueError("stream_audio_pcm_channels_invalid")
        if bits not in {8, 16, 24, 32}:
            raise ValueError("stream_audio_pcm_bits_invalid")
        if endian not in {"little", "big"}:
            raise ValueError("stream_audio_pcm_endian_invalid")
        if encoding not in {"sint", "uint"}:
            raise ValueError("stream_audio_pcm_encoding_invalid")
        return DeclaredStreamAudioFormat(
            mime_type=mime_type,
            container=container,
            codec=None,
            rate=rate,
            channels=channels,
            bits=bits,
            endian=endian,
            encoding=encoding,
        )
    codec: str | None = None
    for parameter in parts[1:]:
        if not parameter:
            continue
        key, separator, raw_value = parameter.partition("=")
        if separator != "=" or key.strip().casefold() != "codecs":
            raise ValueError("stream_audio_parameter_not_supported")
        candidate = raw_value.strip().strip('"').casefold()
        if candidate not in _ALLOWED_CODECS:
            raise ValueError("stream_audio_codec_not_supported")
        if codec is not None:
            raise ValueError("stream_audio_codec_duplicated")
        codec = candidate
    if codec is not None and container not in {"ogg", "webm"}:
        raise ValueError("stream_audio_codec_parameter_invalid")
    implied_codec = {
        "audio/opus": "opus",
        "audio/vorbis": "vorbis",
    }.get(mime_type)
    if implied_codec is not None and codec not in {None, implied_codec}:
        raise ValueError("stream_audio_codec_mismatch")
    return DeclaredStreamAudioFormat(
        mime_type=mime_type,
        container=container,
        codec=codec or implied_codec,
    )


def _detect_container(data: bytes) -> tuple[str, str | None] | None:
    if data.startswith(b"OggS"):
        head = data[:512]
        codec = (
            "opus" if b"OpusHead" in head else
            "vorbis" if b"\x01vorbis" in head else
            "flac" if b"fLaC" in head else
            None
        )
        return "ogg", codec
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm", None
    if data.startswith(b"fLaC"):
        return "flac", "flac"
    if data.startswith(b"ID3") or (
        len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
    ):
        return "mpeg", None
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "mp4", None
    return None


def probe_stream_audio(
    data: bytes,
    *,
    declared: DeclaredStreamAudioFormat | None,
    final: bool = False,
) -> StreamAudioProbe:
    """Validate the bounded initial header and return a canonical MIME type."""

    if declared is not None and declared.container == "pcm":
        frame_bytes = declared.frame_bytes or 0
        if frame_bytes <= 0:
            return StreamAudioProbe(StreamAudioProbeStatus.INVALID)
        if len(data) < frame_bytes:
            return StreamAudioProbe(
                StreamAudioProbeStatus.INVALID if final else StreamAudioProbeStatus.NEED_MORE
            )
        if final and len(data) % frame_bytes:
            return StreamAudioProbe(StreamAudioProbeStatus.INVALID)
        return StreamAudioProbe(
            StreamAudioProbeStatus.SUPPORTED,
            resolved_mime_type=declared.canonical_media_type,
            container="pcm",
        )

    detected = _detect_container(data[:512])
    if detected is None:
        if not final and len(data) < 12:
            return StreamAudioProbe(StreamAudioProbeStatus.NEED_MORE)
        return StreamAudioProbe(StreamAudioProbeStatus.INVALID)

    container, detected_codec = detected
    if declared is not None and declared.container != container:
        return StreamAudioProbe(
            StreamAudioProbeStatus.MISMATCH,
            container=container,
            codec=detected_codec,
        )
    if (
        declared is not None
        and declared.container == "ogg"
        and declared.codec is not None
        and detected_codec is None
        and not final
        and len(data) < 512
    ):
        return StreamAudioProbe(StreamAudioProbeStatus.NEED_MORE)
    if (
        declared is not None
        and declared.container == "ogg"
        and declared.codec is not None
        and declared.codec != detected_codec
    ):
        return StreamAudioProbe(
            StreamAudioProbeStatus.MISMATCH,
            container=container,
            codec=detected_codec,
        )

    if declared is not None:
        resolved = declared.mime_type
    else:
        resolved = {
            "ogg": "audio/ogg",
            "webm": "audio/webm",
            "flac": "audio/flac",
            "mpeg": "audio/mpeg",
            "mp4": "audio/mp4",
        }[container]
    return StreamAudioProbe(
        StreamAudioProbeStatus.SUPPORTED,
        resolved_mime_type=resolved,
        container=container,
        codec=detected_codec,
    )


__all__ = [
    "DeclaredStreamAudioFormat",
    "StreamAudioProbe",
    "StreamAudioProbeStatus",
    "parse_declared_stream_audio_format",
    "probe_stream_audio",
]
