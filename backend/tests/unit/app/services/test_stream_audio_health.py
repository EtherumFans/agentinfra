from __future__ import annotations

import math
import struct

from app.services.stream_audio_health import (
    PcmS16leMonoHealthMonitor,
    PcmS16leMultichannelHealthMonitor,
)


def _tone(*, seconds: float, amplitude: int = 6000, rate: int = 16000) -> bytes:
    samples = int(seconds * rate)
    return b"".join(
        struct.pack("<h", round(amplitude * math.sin(2 * math.pi * 440 * index / rate)))
        for index in range(samples)
    )


def test_long_silence_detects_at_ten_seconds_and_recovers_without_content():
    monitor = PcmS16leMonoHealthMonitor()
    events = monitor.process(b"\x00\x00" * (16000 * 10))
    assert [(event.event, event.channel, event.start_time_ms) for event in events] == [
        ("longSilenceDetected", 0, 0)
    ]

    recovered = monitor.process(_tone(seconds=0.25))
    assert [(event.event, event.channel, event.start_time_ms) for event in recovered] == [
        ("longSilenceRecovered", 0, 10000)
    ]


def test_clipping_quality_issue_requires_one_second_and_one_second_recovery():
    monitor = PcmS16leMonoHealthMonitor()
    detected = monitor.process(struct.pack("<h", 32767) * 16000)
    assert [(event.event, event.start_time_ms) for event in detected] == [
        ("speechQualityIssueDetected", 0)
    ]

    recovered = monitor.process(_tone(seconds=1.0))
    assert [(event.event, event.start_time_ms) for event in recovered] == [
        ("speechQualityIssueRecovered", 1000)
    ]


def test_high_zero_crossing_noise_detects_quality_issue():
    monitor = PcmS16leMonoHealthMonitor()
    noisy = b"".join(
        struct.pack("<h", 6000 if index % 2 == 0 else -6000)
        for index in range(16000)
    )

    assert [
        (event.event, event.channel, event.start_time_ms)
        for event in monitor.process(noisy)
    ] == [("speechQualityIssueDetected", 0, 0)]


def test_chunk_boundaries_do_not_change_window_results():
    monitor = PcmS16leMonoHealthMonitor()
    payload = b"\x00\x00" * (16000 * 10)
    events = []
    for start in range(0, len(payload), 317):
        events.extend(monitor.process(payload[start:start + 317]))
    assert [event.event for event in events] == ["longSilenceDetected"]


def test_multichannel_monitor_preserves_channel_identity_across_partial_frames():
    monitor = PcmS16leMultichannelHealthMonitor(channels=2)
    frames = b"".join(
        struct.pack("<hh", 0, round(6000 * math.sin(2 * math.pi * 440 * index / 16000)))
        for index in range(16000 * 10)
    )
    events = []
    for start in range(0, len(frames), 317):
        events.extend(monitor.process(frames[start:start + 317]))
    assert [(event.event, event.channel, event.start_time_ms) for event in events] == [
        ("longSilenceDetected", 0, 0),
    ]
