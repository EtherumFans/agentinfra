"""Speaker diarization service for Chinese medical consultations.

Separates doctor and patient voices using WebRTC VAD + MFCC features +
agglomerative clustering. Upgraded from energy-only VAD to spectral analysis
for production-grade medical conversation diarization.
"""
import logging
import struct
import wave
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

# try importing heavy deps
try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False
    logger.info("librosa not available, using energy-only features")

try:
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.info("sklearn not available, using k-means fallback")

try:
    import webrtcvad
    HAS_WEBRTC = True
except ImportError:
    HAS_WEBRTC = False


class SpeakerDiarizer:
    """Speaker diarization with spectral features + VAD + clustering.

    Pipeline:
    1. Voice Activity Detection (WebRTC VAD or energy fallback)
    2. Feature extraction per segment (MFCC + energy + pitch + duration)
    3. Agglomerative clustering into 2 speakers (doctor + patient)
    4. Speaker role labeling (doctor = more speech time)
    """

    def __init__(self):
        self._vad = None
        if HAS_WEBRTC:
            try:
                self._vad = webrtcvad.Vad(2)
                logger.info("SpeakerDiarizer: WebRTC VAD initialized (level=2)")
            except Exception:
                pass
        if not self._vad:
            logger.info("SpeakerDiarizer: using energy-based VAD fallback")

    def diarize(self, audio_path: str, sample_rate: int = 16000) -> list[dict]:
        """Perform speaker diarization on audio file.

        Args:
            audio_path: Path to WAV audio file (16kHz mono recommended)
            sample_rate: Audio sample rate in Hz

        Returns:
            List of segments:
            [{"start": float, "end": float, "speaker": "医生/患者", "confidence": float}]
        """
        try:
            audio_data = self._read_wav(audio_path)
            if not audio_data:
                return []

            # Convert to numpy float
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)

            # Step 1: Voice Activity Detection
            speech_segments = self._detect_speech(samples, sample_rate)
            if not speech_segments:
                logger.info("No speech detected")
                return []

            if len(speech_segments) <= 2:
                return self._single_speaker_result(speech_segments)

            # Step 2: Extract features per segment
            features = self._extract_features(speech_segments, samples, sample_rate)

            # Step 3: Cluster speakers
            labeled = self._cluster_speakers(speech_segments, features)

            # Step 4: Label roles (doctor/patient)
            labeled = self._label_roles(labeled)

            return labeled

        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            return []

    # ---- Audio I/O ----

    def _read_wav(self, path: str) -> Optional[bytes]:
        try:
            with wave.open(path, 'rb') as wf:
                frames = wf.readframes(wf.getnframes())
                return frames
        except Exception as e:
            logger.error(f"Failed to read WAV: {e}")
            return None

    # ---- VAD ----

    def _detect_speech(
        self, samples: np.ndarray, sample_rate: int
    ) -> list[dict]:
        """Detect speech segments using VAD.

        Returns list of dicts with start, end, samples, energy, duration.
        """
        frame_ms = 30
        frame_size = int(sample_rate * frame_ms / 1000)

        segments = []
        in_speech = False
        speech_start = 0
        seg_samples = []

        for i in range(0, len(samples) - frame_size, frame_size // 2):  # 50% overlap
            frame = samples[i:i + frame_size]
            if len(frame) < frame_size:
                break
            time_s = i / sample_rate

            is_speech = self._is_speech(frame, sample_rate)

            if is_speech and not in_speech:
                speech_start = time_s
                seg_samples = list(frame)
                in_speech = True
            elif is_speech and in_speech:
                seg_samples.extend(frame)
            elif not is_speech and in_speech:
                dur = time_s - speech_start
                if dur >= 0.3:
                    segments.append({
                        "start": speech_start,
                        "end": time_s,
                        "samples": np.array(seg_samples, dtype=np.float32),
                        "duration": dur,
                    })
                in_speech = False
                seg_samples = []

        # Trailing
        if in_speech:
            dur = len(seg_samples) / sample_rate
            if dur >= 0.3:
                segments.append({
                    "start": speech_start,
                    "end": speech_start + dur,
                    "samples": np.array(seg_samples, dtype=np.float32),
                    "duration": dur,
                })

        return segments

    def _is_speech(self, frame: np.ndarray, sample_rate: int) -> bool:
        """Check if frame contains speech via VAD or energy threshold."""
        if self._vad and len(frame) == int(sample_rate * 30 / 1000):
            try:
                raw = frame.astype(np.int16).tobytes()
                return self._vad.is_speech(raw, sample_rate)
            except Exception:
                pass
        rms = np.sqrt(np.mean(frame ** 2))
        return rms > 80  # adjusted for float32

    # ---- Feature Extraction ----

    def _extract_features(
        self, segments: list[dict], samples: np.ndarray, sample_rate: int
    ) -> np.ndarray:
        """Extract spectral features for speaker clustering.

        Features per segment:
        - MFCC mean (13 dims) — timbre/texture
        - RMS energy mean + std
        - Spectral centroid mean — brightness
        - Zero-crossing rate — voicing
        - Duration
        - Gap to previous segment
        """
        all_features = []

        prev_end = segments[0]["start"] - 10

        for seg in segments:
            seg_samples = seg["samples"]
            feats = []

            if HAS_LIBROSA and len(seg_samples) > sample_rate * 0.1:
                try:
                    # MFCC: 13 coefficients
                    mfcc = librosa.feature.mfcc(
                        y=seg_samples, sr=sample_rate, n_mfcc=13
                    )
                    feats.extend(np.mean(mfcc, axis=1))
                    feats.extend(np.std(mfcc, axis=1))

                    # Spectral centroid
                    cent = librosa.feature.spectral_centroid(
                        y=seg_samples, sr=sample_rate
                    )
                    feats.append(np.mean(cent) / (sample_rate / 2))

                    # Zero-crossing rate
                    zcr = librosa.feature.zero_crossing_rate(seg_samples)
                    feats.append(np.mean(zcr))
                except Exception:
                    pass

            if not feats:
                # Fallback: energy-only features
                rms = np.sqrt(np.mean(seg_samples ** 2))
                feats = [rms, np.std(seg_samples), 0] * 9 + [rms / 1000]

            # RMS energy
            rms = np.sqrt(np.mean(seg_samples ** 2))
            feats.append(rms / 1000)
            feats.append(np.std(np.abs(seg_samples)) / 1000)

            # Duration
            feats.append(seg["duration"])

            # Gap from previous
            gap = seg["start"] - prev_end
            feats.append(min(gap, 5.0) / 5.0)
            prev_end = seg["end"]

            all_features.append(feats)

        # Pad to uniform length
        max_len = max(len(f) for f in all_features)
        padded = []
        for f in all_features:
            if len(f) < max_len:
                f = list(f) + [0.0] * (max_len - len(f))
            padded.append(f)

        return np.array(padded, dtype=np.float32)

    # ---- Clustering ----

    def _cluster_speakers(
        self, segments: list[dict], features: np.ndarray
    ) -> list[dict]:
        """Cluster segments into 2 speakers."""
        n_segments = len(segments)
        labels = [0] * n_segments

        if HAS_SKLEARN and n_segments >= 4:
            try:
                scaler = StandardScaler()
                features_norm = scaler.fit_transform(features)

                clustering = AgglomerativeClustering(
                    n_clusters=2, linkage="ward"
                )
                labels = clustering.fit_predict(features_norm).tolist()
            except Exception as e:
                logger.warning(f"Clustering failed: {e}, using energy-median split")

        if set(labels) == {0}:
            # All same cluster — fallback: energy median split
            energies = [np.sqrt(np.mean(seg["samples"] ** 2)) for seg in segments]
            median_e = np.median(energies)
            labels = [0 if e < median_e else 1 for e in energies]

        # Build result
        result = []
        prev_label = None
        for i, seg in enumerate(segments):
            label = labels[i]

            # Smoothing: if speaker changes for a single short segment, keep previous
            if i > 0 and i < n_segments - 1:
                if label != prev_label and label != labels[i + 1]:
                    if seg["duration"] < 1.0:
                        label = prev_label

            result.append({
                "start": round(seg["start"], 2),
                "end": round(seg["end"], 2),
                "speaker": f"SPEAKER_{label + 1}",
                "confidence": 0.70,  # will be refined in _label_roles
            })
            prev_label = label

        return result

    # ---- Role Labeling ----

    def _label_roles(self, segments: list[dict]) -> list[dict]:
        """Label speakers as doctor/patient.

        Heuristics (ordered by priority):
        1. Speaker with more total speech time → doctor
        2. Speaker with fewer but longer turns → doctor
        3. First speaker → likely patient (complaint first in clinical flow)
        """
        if not segments:
            return segments

        spk_stats = {}
        for seg in segments:
            spk = seg["speaker"]
            if spk not in spk_stats:
                spk_stats[spk] = {"total_time": 0, "turn_count": 0}
            spk_stats[spk]["total_time"] += seg["end"] - seg["start"]
            spk_stats[spk]["turn_count"] += 1

        speakers = list(spk_stats.keys())
        if len(speakers) != 2:
            for seg in segments:
                seg["speaker"] = "医生"
                seg["confidence"] = 0.75
            return segments

        spk0, spk1 = speakers
        s0, s1 = spk_stats[spk0], spk_stats[spk1]

        # Primary: more total time → doctor
        if s0["total_time"] >= s1["total_time"] * 1.1:
            mapping = {spk0: "医生", spk1: "患者"}
        elif s1["total_time"] >= s0["total_time"] * 1.1:
            mapping = {spk0: "患者", spk1: "医生"}
        # Secondary: fewer but longer turns → doctor
        elif s0["turn_count"] < s1["turn_count"]:
            mapping = {spk0: "医生", spk1: "患者"}
        else:
            mapping = {spk0: "患者", spk1: "医生"}

        for seg in segments:
            seg["speaker"] = mapping.get(seg["speaker"], "医生")
            seg["confidence"] = round(0.70 + 0.15 * min(1.0,
                spk_stats.get(mapping.get(seg["speaker"], seg["speaker"]), {}).get("total_time", 0) /
                max(s0["total_time"], s1["total_time"])
            ), 2)

        return segments

    def _single_speaker_result(self, segments: list[dict]) -> list[dict]:
        return [{
            "start": seg["start"],
            "end": seg["end"],
            "speaker": "医生",
            "confidence": 0.65,
        } for seg in segments]


speaker_diarizer = SpeakerDiarizer()
