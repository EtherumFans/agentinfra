"""Run deterministic real-ffmpeg format and malformed-media soak evidence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings
from app.services.stream_audio_format import (
    StreamAudioProbeStatus,
    parse_declared_stream_audio_format,
    probe_stream_audio,
)
from app.services.stream_media_decoder import (
    StreamMediaDecodeStatus,
    reset_stream_media_decoder_state_for_tests,
    stream_media_decoder_snapshot,
    validate_stream_audio_decode,
)


FORMATS = (
    ("ogg_opus", "audio/ogg; codecs=opus", ".ogg", ("-c:a", "libopus", "-f", "ogg")),
    ("webm_opus", "audio/webm; codecs=opus", ".webm", ("-c:a", "libopus", "-f", "webm")),
    ("mp3", "audio/mpeg", ".mp3", ("-c:a", "libmp3lame", "-f", "mp3")),
    ("flac", "audio/flac", ".flac", ("-c:a", "flac", "-f", "flac")),
    ("mp4_aac", "audio/mp4", ".m4a", ("-c:a", "aac", "-f", "mp4")),
)

PLAUSIBLE_INVALID = (
    ("fake_ogg_opus", "audio/ogg; codecs=opus", b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 64),
    ("fake_webm", "audio/webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 96),
    ("fake_mp3", "audio/mpeg", b"ID3" + b"\x00" * 97),
    ("fake_flac", "audio/flac", b"fLaC" + b"\x00" * 96),
    ("fake_mp4", "audio/mp4", b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 88),
)


def _minimal_environment(ffmpeg: Path) -> dict[str, str]:
    environment = {"PATH": str(ffmpeg.parent)}
    for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    if os.name != "nt":
        environment.update({"LANG": "C", "LC_ALL": "C"})
    return environment


def _generate_fixtures(ffmpeg: Path, root: Path) -> dict[str, tuple[str, bytes]]:
    fixtures: dict[str, tuple[str, bytes]] = {}
    environment = _minimal_environment(ffmpeg)
    for name, declared, suffix, codec_args in FORMATS:
        path = root / f"silent-{name}{suffix}"
        command = (
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.25",
            *codec_args, "-y", str(path),
        )
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            timeout=20,
            check=False,
        )
        if completed.returncode != 0 or not path.is_file():
            raise RuntimeError(f"synthetic fixture generation failed for {name}")
        audio = path.read_bytes()
        if not 64 <= len(audio) <= 64_000:
            raise RuntimeError(f"synthetic fixture size is outside Streams bounds for {name}")
        probe = probe_stream_audio(
            audio,
            declared=parse_declared_stream_audio_format(declared),
            final=True,
        )
        if probe.status != StreamAudioProbeStatus.SUPPORTED:
            raise RuntimeError(f"generated fixture failed the container contract for {name}")
        fixtures[name] = (declared, audio)
    return fixtures


def _mutate(audio: bytes, *, seed: int) -> bytes:
    value = bytearray(audio)
    randomizer = random.Random(seed)
    start = min(64, max(12, len(value) // 4))
    for _ in range(1 + seed % 4):
        position = randomizer.randrange(start, len(value))
        value[position] ^= 1 << randomizer.randrange(0, 8)
    if seed % 5 == 0 and len(value) > 96:
        del value[-randomizer.randrange(1, min(32, len(value) - 64)) :]
    return bytes(value)


async def _decode_case(name: str, media_type: str, audio: bytes) -> dict[str, object]:
    started = time.perf_counter()
    result = await validate_stream_audio_decode(audio, media_type=media_type)
    return {
        "name": name,
        "status": result.status.value,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }


async def run(args: argparse.Namespace) -> dict[str, object]:
    ffmpeg = Path(args.ffmpeg).resolve()
    if not ffmpeg.is_file():
        raise RuntimeError("ffmpeg executable is unavailable")
    if args.cases < 10 or args.cases > 500:
        raise RuntimeError("cases must be between 10 and 500")

    settings.ICODER_STREAM_MEDIA_VALIDATION_MODE = "decoder"
    settings.ICODER_STREAM_MEDIA_DECODER_PATH = str(ffmpeg)
    settings.ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS = 3.0
    settings.ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY = 4
    settings.ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS = 5.0
    reset_stream_media_decoder_state_for_tests()

    with tempfile.TemporaryDirectory(prefix="icoder-stream-media-soak-") as temporary:
        fixtures = _generate_fixtures(ffmpeg, Path(temporary))
        cases: list[tuple[str, str, bytes, str]] = []
        for name, (declared, audio) in fixtures.items():
            cases.append((name, declared.split(";", 1)[0], audio, "valid"))
        for name, declared, audio in PLAUSIBLE_INVALID:
            probe = probe_stream_audio(
                audio,
                declared=parse_declared_stream_audio_format(declared),
                final=True,
            )
            if probe.status != StreamAudioProbeStatus.SUPPORTED:
                raise RuntimeError(f"plausible malformed header did not reach decoder for {name}")
            cases.append((name, declared.split(";", 1)[0], audio, "invalid"))

        mutation_index = 0
        fixture_rows = list(fixtures.items())
        while len(cases) < args.cases:
            name, (declared, audio) = fixture_rows[mutation_index % len(fixture_rows)]
            cases.append((
                f"mutation_{mutation_index:03d}_{name}",
                declared.split(";", 1)[0],
                _mutate(audio, seed=20260824 + mutation_index),
                "mutation",
            ))
            mutation_index += 1

        results: list[dict[str, object]] = []
        for offset in range(0, len(cases), 4):
            batch = cases[offset : offset + 4]
            results.extend(await asyncio.gather(*(
                _decode_case(name, media_type, audio)
                for name, media_type, audio, _kind in batch
            )))

    by_name = {row[0]: row[3] for row in cases}
    for result in results:
        kind = by_name[str(result["name"])]
        status = result["status"]
        if kind == "valid" and status != StreamMediaDecodeStatus.VALID.value:
            raise RuntimeError(f"valid format failed decoder soak: {result['name']}")
        if kind == "invalid" and status != StreamMediaDecodeStatus.INVALID.value:
            raise RuntimeError(f"plausible malformed media bypassed decoder: {result['name']}")
        if status in {
            StreamMediaDecodeStatus.TIMEOUT.value,
            StreamMediaDecodeStatus.UNAVAILABLE.value,
            StreamMediaDecodeStatus.BUSY.value,
        }:
            raise RuntimeError(f"decoder soak hit an infrastructure failure: {status}")

    latencies = sorted(float(row["latency_ms"]) for row in results)
    snapshot = stream_media_decoder_snapshot()
    if snapshot["active"] != 0 or int(snapshot["maximum_active"]) > 4:
        raise RuntimeError("decoder concurrency evidence is inconsistent")
    status_counts = {
        status.value: sum(row["status"] == status.value for row in results)
        for status in StreamMediaDecodeStatus
    }
    fixture_evidence = {
        name: {
            "bytes": len(audio),
            "sha256": hashlib.sha256(audio).hexdigest(),
        }
        for name, (_declared, audio) in fixtures.items()
    }
    return {
        "schema_version": "icoder.stream-media-decoder-soak/v1",
        "status": "passed",
        "seed": 20260824,
        "cases": len(results),
        "valid_formats": len(FORMATS),
        "plausible_invalid_formats": len(PLAUSIBLE_INVALID),
        "mutations": len(results) - len(FORMATS) - len(PLAUSIBLE_INVALID),
        "status_counts": status_counts,
        "latency_ms": {
            "maximum": max(latencies),
            "p95": latencies[max(0, int(len(latencies) * 0.95) - 1)],
        },
        "decoder_metrics": snapshot,
        "fixtures": fixture_evidence,
        "real_patient_audio_used": False,
        "decoder_processes_remaining": 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--cases", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    report = asyncio.run(run(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: report[key] for key in ("status", "cases", "status_counts")}))
