"""Deterministic, content-free audio health events for governed PCM streams."""

from __future__ import annotations

import math
import sys
from array import array
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StreamAudioHealthEvent:
    event: str
    channel: int
    start_time_ms: int


class PcmS16leMonoHealthMonitor:
    """Detect bounded signal-quality transitions from 16 kHz mono PCM.

    The detector intentionally exposes only four Corti-compatible event names
    and timing metadata. It never stores decoded text or emits signal samples.
    Thresholds are deterministic engineering heuristics, not clinical claims.
    """

    _WINDOW_MILLISECONDS = 250
    _SILENCE_SECONDS = 10
    _SILENCE_RMS = 104.0  # approximately -50 dBFS
    _QUALITY_RMS = 4125.0  # approximately -18 dBFS
    _QUALITY_ZERO_CROSSING_RATE = 0.25
    _CLIP_AMPLITUDE = 32112
    _CLIP_RATIO = 0.01
    _QUALITY_WINDOWS = 4

    def __init__(self, *, sample_rate: int = 16000) -> None:
        if sample_rate != 16000:
            raise ValueError("pcm_health_sample_rate_not_supported")
        self._sample_rate = sample_rate
        self._window_samples = sample_rate * self._WINDOW_MILLISECONDS // 1000
        self._pending = bytearray()
        self._processed_samples = 0
        self._silence_windows = 0
        self._silence_active = False
        self._quality_bad_windows = 0
        self._quality_good_windows = 0
        self._quality_active = False

    def process(self, chunk: bytes) -> tuple[StreamAudioHealthEvent, ...]:
        if not chunk:
            return ()
        self._pending.extend(chunk)
        window_bytes = self._window_samples * 2
        events: list[StreamAudioHealthEvent] = []
        while len(self._pending) >= window_bytes:
            payload = bytes(self._pending[:window_bytes])
            del self._pending[:window_bytes]
            samples = array("h")
            samples.frombytes(payload)
            if sys.byteorder != "little":
                samples.byteswap()
            window_start = self._processed_samples
            self._processed_samples += len(samples)
            events.extend(self._process_window(samples, window_start))
        return tuple(events)

    def _process_window(
        self,
        samples: array,
        window_start: int,
    ) -> list[StreamAudioHealthEvent]:
        count = len(samples)
        square_sum = sum(int(value) * int(value) for value in samples)
        rms = math.sqrt(square_sum / count) if count else 0.0
        clipped = sum(1 for value in samples if abs(int(value)) >= self._CLIP_AMPLITUDE)
        crossings = sum(
            1
            for previous, current in zip(samples, samples[1:])
            if (previous < 0 <= current) or (previous >= 0 > current)
        )
        crossing_rate = crossings / max(1, count - 1)
        silent = rms <= self._SILENCE_RMS
        quality_bad = not silent and (
            clipped / max(1, count) >= self._CLIP_RATIO
            or (
                rms >= self._QUALITY_RMS
                and crossing_rate >= self._QUALITY_ZERO_CROSSING_RATE
            )
        )

        events: list[StreamAudioHealthEvent] = []
        if silent:
            self._silence_windows += 1
            required = self._SILENCE_SECONDS * 1000 // self._WINDOW_MILLISECONDS
            if not self._silence_active and self._silence_windows >= required:
                self._silence_active = True
                start_sample = self._processed_samples - required * self._window_samples
                events.append(self._event("longSilenceDetected", start_sample))
        else:
            if self._silence_active:
                events.append(self._event("longSilenceRecovered", window_start))
            self._silence_windows = 0
            self._silence_active = False

        if quality_bad:
            self._quality_bad_windows += 1
            self._quality_good_windows = 0
            if (
                not self._quality_active
                and self._quality_bad_windows >= self._QUALITY_WINDOWS
            ):
                self._quality_active = True
                start_sample = (
                    self._processed_samples
                    - self._QUALITY_WINDOWS * self._window_samples
                )
                events.append(self._event("speechQualityIssueDetected", start_sample))
        else:
            self._quality_bad_windows = 0
            if self._quality_active:
                self._quality_good_windows += 1
                if self._quality_good_windows >= self._QUALITY_WINDOWS:
                    recovery_sample = (
                        self._processed_samples
                        - self._QUALITY_WINDOWS * self._window_samples
                    )
                    events.append(self._event("speechQualityIssueRecovered", recovery_sample))
                    self._quality_active = False
                    self._quality_good_windows = 0
            else:
                self._quality_good_windows = 0
        return events

    def _event(self, name: str, sample: int) -> StreamAudioHealthEvent:
        return StreamAudioHealthEvent(
            event=name,
            channel=0,
            start_time_ms=max(0, sample * 1000 // self._sample_rate),
        )


class PcmS16leMultichannelHealthMonitor:
    """Route aligned interleaved PCM frames through one monitor per channel."""

    def __init__(self, *, sample_rate: int = 16000, channels: int) -> None:
        if channels < 2 or channels > 8:
            raise ValueError("pcm_health_channel_count_not_supported")
        self._channels = channels
        self._monitors = tuple(
            PcmS16leMonoHealthMonitor(sample_rate=sample_rate)
            for _ in range(channels)
        )
        self._pending = bytearray()

    def process(self, chunk: bytes) -> tuple[StreamAudioHealthEvent, ...]:
        if not chunk:
            return ()
        self._pending.extend(chunk)
        frame_bytes = self._channels * 2
        aligned_size = len(self._pending) - (len(self._pending) % frame_bytes)
        if aligned_size <= 0:
            return ()
        payload = bytes(self._pending[:aligned_size])
        del self._pending[:aligned_size]
        channel_payloads = [bytearray() for _ in range(self._channels)]
        view = memoryview(payload)
        for frame_start in range(0, len(payload), frame_bytes):
            for channel in range(self._channels):
                sample_start = frame_start + channel * 2
                channel_payloads[channel].extend(view[sample_start:sample_start + 2])
        events: list[StreamAudioHealthEvent] = []
        for channel, (monitor, channel_payload) in enumerate(
            zip(self._monitors, channel_payloads)
        ):
            events.extend(
                StreamAudioHealthEvent(
                    event=event.event,
                    channel=channel,
                    start_time_ms=event.start_time_ms,
                )
                for event in monitor.process(bytes(channel_payload))
            )
        return tuple(sorted(events, key=lambda item: (item.start_time_ms, item.channel, item.event)))


__all__ = [
    "PcmS16leMonoHealthMonitor",
    "PcmS16leMultichannelHealthMonitor",
    "StreamAudioHealthEvent",
]
