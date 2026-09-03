"""Exercise prerecorded Chinese dictation through a real local API process."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import struct
import subprocess
import time
import uuid
import wave

import httpx


RAW_TEXT = "患者主诉胸痛 逗号 持续三天 句号 左括号 房颤 右括号"
FORMATTED_TEXT = "患者主诉胸痛，持续三天。（房颤）"
KEYTERM_TEXT = "房颤患者由Corti Health随访"


def _synthetic_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(struct.pack("<" + "h" * 1600, *([0] * 1600)))
    return buffer.getvalue()


def _synthetic_stereo_wav() -> bytes:
    buffer = io.BytesIO()
    interleaved = [sample for _ in range(1600) for sample in (1400, -1400)]
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(struct.pack("<" + "h" * len(interleaved), *interleaved))
    return buffer.getvalue()


def _synthetic_stereo_flac() -> bytes:
    executable = os.environ.get("ICODER_E2E_FFMPEG_PATH", "").strip()
    if not executable or not Path(executable).is_file():
        raise RuntimeError("dictation E2E requires an explicit FFmpeg executable")
    environment = {"PATH": str(Path(executable).resolve().parent)}
    for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    completed = subprocess.run(
        [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-f",
            "wav",
            "-i",
            "pipe:0",
            "-map_metadata",
            "-1",
            "-c:a",
            "flac",
            "-f",
            "flac",
            "pipe:1",
        ],
        input=_synthetic_stereo_wav(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        shell=False,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.startswith(b"fLaC"):
        raise RuntimeError("synthetic stereo FLAC generation failed")
    return completed.stdout


def _transcript_text(payload: dict) -> str:
    rows = payload.get("transcripts")
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError("transcript response did not contain exactly one row")
    return str(rows[0].get("text", ""))


def run() -> dict[str, object]:
    base_url = os.environ.get("ICODER_E2E_BASE_URL", "").rstrip("/")
    if not base_url.startswith("http://127.0.0.1:"):
        raise RuntimeError("dictation E2E requires an explicit loopback base URL")
    suffix = uuid.uuid4().hex
    with httpx.Client(base_url=base_url, timeout=15, trust_env=False) as client:
        registration = client.post(
            "/api/auth/register",
            json={
                "username": f"dictation_{suffix}",
                "email": f"dictation-{suffix}@icoder.ai",
                "password": f"Dictation-{suffix}!",
                "full_name": "Dictation E2E",
                "organization_name": f"Dictation E2E {suffix}",
            },
        )
        registration.raise_for_status()
        token = registration.json().get("access_token")
        if not token:
            raise RuntimeError("registration did not return a tenant token")
        headers = {"Authorization": f"Bearer {token}"}
        interaction_id = str(uuid.uuid4())
        uploaded = client.post(
            f"/api/v2/tools/interactions/{interaction_id}/recordings/",
            content=_synthetic_wav(),
            headers={**headers, "Content-Type": "audio/wav"},
        )
        uploaded.raise_for_status()
        recording_id = uploaded.json()["recordingId"]

        sync = client.post(
            f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
            headers=headers,
            json={
                "recordingId": recording_id,
                "primaryLanguage": "zh-CN",
                "spokenPunctuation": True,
            },
        )
        if sync.status_code != 201:
            raise RuntimeError(f"synchronous dictation returned {sync.status_code}")
        if _transcript_text(sync.json()) != FORMATTED_TEXT:
            raise RuntimeError("synchronous dictation punctuation was not normalized")

        unformatted = client.post(
            f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
            headers=headers,
            json={"recordingId": recording_id, "primaryLanguage": "zh-CN"},
        )
        if unformatted.status_code != 201 or _transcript_text(unformatted.json()) != RAW_TEXT:
            raise RuntimeError("default transcription changed without dictation opt-in")

        keyterm_transcript = client.post(
            f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
            headers=headers,
            json={
                "recordingId": recording_id,
                "primaryLanguage": "zh-CN",
                "keyterms": {
                    "terms": [{"term": "房颤"}, {"term": "Corti Health"}],
                },
            },
        )
        if (
            keyterm_transcript.status_code != 201
            or _transcript_text(keyterm_transcript.json()) != KEYTERM_TEXT
        ):
            raise RuntimeError("ordered case-sensitive keyterms were not forwarded")

        asynchronous = client.post(
            f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
            headers=headers,
            json={
                "recordingId": recording_id,
                "primaryLanguage": "zh-CN",
                "isDictation": True,
                "async": True,
            },
        )
        if asynchronous.status_code != 202:
            raise RuntimeError(f"asynchronous dictation returned {asynchronous.status_code}")
        transcript_id = asynchronous.json()["id"]
        location = asynchronous.headers.get("location", "")
        if not location.endswith(f"/{transcript_id}/status"):
            raise RuntimeError("asynchronous dictation did not return its status location")
        status = "processing"
        for _ in range(50):
            polled = client.get(location, headers=headers)
            polled.raise_for_status()
            status = polled.json().get("status")
            if status != "processing":
                break
            time.sleep(0.05)
        if status != "completed":
            raise RuntimeError(f"asynchronous dictation ended as {status}")
        fetched = client.get(
            f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}",
            headers=headers,
        )
        fetched.raise_for_status()
        if _transcript_text(fetched.json()) != FORMATTED_TEXT:
            raise RuntimeError("asynchronous dictation punctuation was not normalized")

        multichannel_interaction_id = str(uuid.uuid4())
        stereo_upload = client.post(
            f"/api/v2/tools/interactions/{multichannel_interaction_id}/recordings/",
            content=_synthetic_stereo_wav(),
            headers={**headers, "Content-Type": "audio/wav"},
        )
        stereo_upload.raise_for_status()
        multichannel_request = {
            "recordingId": stereo_upload.json()["recordingId"],
            "primaryLanguage": "zh-CN",
            "isMultichannel": True,
            "participants": [
                {"channel": 0, "role": "doctor"},
                {"channel": 1, "role": "patient"},
            ],
            "keyterms": {
                "terms": [{"term": "房颤"}, {"term": "Corti Health"}],
            },
        }
        multichannel = client.post(
            f"/api/v2/tools/interactions/{multichannel_interaction_id}/transcripts/",
            headers=headers,
            json=multichannel_request,
        )
        if multichannel.status_code != 201:
            raise RuntimeError(
                f"synchronous multichannel transcript returned {multichannel.status_code}"
            )
        rows = multichannel.json().get("transcripts")
        expected_rows = [
            (0, 0, -1, "医生询问", 0, 40),
            (0, 0, -1, "房颤", 50, 90),
            (1, 1, -1, "患者回答", 0, 45),
            (1, 1, -1, "Corti Health", 50, 95),
        ]
        if not isinstance(rows, list) or [
            (
                row.get("channel"), row.get("participant"), row.get("speakerId"),
                row.get("text"), row.get("start"), row.get("end"),
            )
            for row in rows
        ] != expected_rows:
            raise RuntimeError("multichannel attribution or phrase timestamps were not preserved")

        encoded_interaction_id = str(uuid.uuid4())
        encoded_upload = client.post(
            f"/api/v2/tools/interactions/{encoded_interaction_id}/recordings/",
            content=_synthetic_stereo_flac(),
            headers={**headers, "Content-Type": "audio/flac"},
        )
        encoded_upload.raise_for_status()
        encoded_request = {
            **multichannel_request,
            "recordingId": encoded_upload.json()["recordingId"],
        }
        encoded = client.post(
            f"/api/v2/tools/interactions/{encoded_interaction_id}/transcripts/",
            headers=headers,
            json=encoded_request,
        )
        if encoded.status_code != 201 or [
            (
                row.get("channel"), row.get("participant"), row.get("speakerId"),
                row.get("text"), row.get("start"), row.get("end"),
            )
            for row in encoded.json().get("transcripts", [])
        ] != expected_rows:
            raise RuntimeError("encoded multichannel decode or timestamps were not preserved")

        encoded_request["async"] = True
        multichannel_async = client.post(
            f"/api/v2/tools/interactions/{encoded_interaction_id}/transcripts/",
            headers=headers,
            json=encoded_request,
        )
        if multichannel_async.status_code != 202:
            raise RuntimeError(
                f"asynchronous multichannel transcript returned {multichannel_async.status_code}"
            )
        async_location = multichannel_async.headers.get("location", "")
        for _ in range(50):
            async_status = client.get(async_location, headers=headers)
            async_status.raise_for_status()
            if async_status.json().get("status") != "processing":
                break
            time.sleep(0.05)
        multichannel_fetched = client.get(
            f"/api/v2/tools/interactions/{encoded_interaction_id}/transcripts/"
            f"{multichannel_async.json()['id']}",
            headers=headers,
        )
        multichannel_fetched.raise_for_status()
        if [
            (row.get("channel"), row.get("start"), row.get("end"))
            for row in multichannel_fetched.json().get("transcripts", [])
        ] != [(0, 0, 40), (0, 50, 90), (1, 0, 45), (1, 50, 95)]:
            raise RuntimeError("asynchronous encoded multichannel rows were not recovered")

    return {
        "status": "passed",
        "real_uvicorn": True,
        "tenant_authentication": True,
        "recording_upload": True,
        "synchronous_spoken_punctuation": True,
        "asynchronous_legacy_is_dictation": True,
        "default_is_non_mutating": True,
        "prerecorded_keyterms_forwarded_in_order": True,
        "prerecorded_stereo_pcm_split_without_crosstalk": True,
        "prerecorded_encoded_stereo_decoded_without_crosstalk": True,
        "prerecorded_phrase_timestamps_are_milliseconds": True,
        "prerecorded_multichannel_attribution_sync_async": True,
        "synthetic_audio_only": True,
        "synthetic_asr_boundary": True,
        "real_stt_used": False,
        "real_llm_used": False,
        "patient_audio_used": False,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
