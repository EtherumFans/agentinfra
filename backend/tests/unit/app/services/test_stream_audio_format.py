from __future__ import annotations

import pytest

from app.services.stream_audio_format import (
    StreamAudioProbeStatus,
    parse_declared_stream_audio_format,
    probe_stream_audio,
)


@pytest.mark.parametrize(
    "mime_type",
    [
        "audio/ogg",
        "audio/webm; codecs=opus",
        "audio/opus",
        "audio/vorbis",
        "audio/mpeg",
        "audio/mp3",
        "audio/mpeg3",
        "audio/flac",
        "audio/mp4",
        "audio/m4a",
        "audio/pcm; rate=16000; channels=1; bits=16",
    ],
)
def test_official_stream_mime_types_are_accepted(mime_type):
    assert parse_declared_stream_audio_format(mime_type) is not None


@pytest.mark.parametrize(
    "mime_type",
    [
        "audio/wav",
        "audio/x-wav",
        "audio/pcm",
        "audio/pcm; rate=7999; channels=1; bits=16",
        "audio/pcm; rate=16000; channels=0; bits=16",
        "audio/pcm; rate=16000; channels=1; bits=12",
        "audio/pcm; rate=16000; channels=1; bits=16; endian=middle",
        "audio/pcm; rate=16000; channels=1; bits=16; encoding=float",
        "audio/pcm; rate=16000; rate=8000; channels=1; bits=16",
        "video/webm",
        "audio/ogg; rate=16000",
        "audio/mpeg; codecs=mp3",
        "audio/opus; codecs=vorbis",
    ],
)
def test_raw_wav_unknown_parameters_and_mismatched_codecs_are_rejected(mime_type):
    with pytest.raises(ValueError):
        parse_declared_stream_audio_format(mime_type)


def test_probe_detects_supported_container_and_declared_mismatch():
    ogg = b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 64
    accepted = probe_stream_audio(
        ogg,
        declared=parse_declared_stream_audio_format("audio/ogg; codecs=opus"),
    )
    assert accepted.status == StreamAudioProbeStatus.SUPPORTED
    assert accepted.resolved_mime_type == "audio/ogg"

    mismatch = probe_stream_audio(
        ogg,
        declared=parse_declared_stream_audio_format("audio/mpeg"),
    )
    assert mismatch.status == StreamAudioProbeStatus.MISMATCH


def test_probe_waits_for_small_header_then_rejects_unknown_final_bytes():
    assert probe_stream_audio(
        b"short", declared=None
    ).status == StreamAudioProbeStatus.NEED_MORE
    assert probe_stream_audio(
        b"short", declared=None, final=True
    ).status == StreamAudioProbeStatus.INVALID


def test_probe_accepts_declared_pcm_and_requires_complete_frames():
    declared = parse_declared_stream_audio_format(
        "audio/pcm; rate=16000; channels=1; bits=16"
    )
    assert declared is not None
    assert declared.frame_bytes == 2
    assert declared.canonical_media_type == (
        "audio/pcm; rate=16000; channels=1; bits=16; "
        "endian=little; encoding=sint"
    )
    assert probe_stream_audio(
        b"\x00", declared=declared
    ).status == StreamAudioProbeStatus.NEED_MORE
    accepted = probe_stream_audio(b"\x00\x00", declared=declared)
    assert accepted.status == StreamAudioProbeStatus.SUPPORTED
    assert accepted.resolved_mime_type == declared.canonical_media_type
    assert probe_stream_audio(
        b"\x00", declared=declared, final=True
    ).status == StreamAudioProbeStatus.INVALID


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\x1a\x45\xdf\xa3" + b"\x00" * 16, "audio/webm"),
        (b"fLaC" + b"\x00" * 16, "audio/flac"),
        (b"ID3" + b"\x00" * 20, "audio/mpeg"),
        (b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 8, "audio/mp4"),
    ],
)
def test_probe_autodetects_supported_encoded_containers(data, expected):
    result = probe_stream_audio(data, declared=None)
    assert result.status == StreamAudioProbeStatus.SUPPORTED
    assert result.resolved_mime_type == expected
