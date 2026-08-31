"""Speech To Text resource."""

import asyncio
import json
from typing import Any, Optional
from urllib.parse import quote

from ..client import iCoDerClient
from ..managed_stt_session import ManagedSttSession, ManagedSttSessionError
from ..request_options import RequestOptions
from ..types import HttpResult


class SpeechToTextResource:
    MAX_RECORDING_BYTES = 150 * 1024 * 1024

    def __init__(self, client: iCoDerClient):
        self._client = client

    def readiness(
        self,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            "/api/v2/tools/stt/readiness",
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    async def connect_managed_session_async(
        self,
        *,
        language: str = "zh-CN",
        mime_type: str = "audio/webm;codecs=opus",
        await_configuration: bool = True,
        reconnect_attempts: int = 3,
        reconnect_initial_delay: float = 0.25,
        reconnect_max_delay: float = 2.0,
        setup_timeout: float = 5.0,
    ) -> ManagedSttSession:
        """Open a typed managed session with safe pre-audio reconnection."""
        if not language.lower().startswith("zh"):
            raise ValueError(
                "the verified real-time STT runtime currently supports zh-CN only"
            )
        token = self._client.ensure_access_token()
        if not token:
            raise ValueError("an access token is required for real-time STT")
        try:
            import websockets
        except ImportError:
            raise ImportError(
                "websockets library required. Install: pip install websockets"
            ) from None

        ws_url = self._client.base_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        )

        async def prepare_connection() -> None:
            if not self._client.ensure_access_token():
                raise ManagedSttSessionError("missing_access_token")

        session = ManagedSttSession(
            websockets.connect,
            lambda: (
                f"{ws_url}/ws/speech-to-text?token="
                f"{quote(self._client.config.access_token or '', safe='')}"
            ),
            prepare_connection=prepare_connection,
            language=language,
            mime_type=mime_type,
            reconnect_attempts=reconnect_attempts,
            reconnect_initial_delay=reconnect_initial_delay,
            reconnect_max_delay=reconnect_max_delay,
            setup_timeout=setup_timeout,
        )
        return await session.connect(await_configuration)

    async def create_session_async(self, language: str = "zh-CN",
                                   punctuation: str = "auto",
                                   interim_results: bool = True):
        """Create a WebSocket STT session (async). Requires websockets library."""
        if not language.lower().startswith("zh"):
            raise ValueError("the verified real-time STT runtime currently supports zh-CN only")
        if punctuation == "spoken":
            raise ValueError("spoken punctuation is not supported by the verified real-time STT runtime")
        token = self._client.config.access_token
        if not token:
            raise ValueError("an access token is required for real-time STT")
        try:
            import websockets
        except ImportError:
            raise ImportError("websockets library required. Install: pip install websockets")

        ws_url = self._client.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws = None
        try:
            ws = await asyncio.wait_for(
                websockets.connect(
                    f"{ws_url}/ws/speech-to-text?token={quote(token, safe='')}"
                ),
                timeout=5,
            )
            await ws.send(json.dumps({
                "type": "start",
                "mimeType": "audio/webm;codecs=opus",
                "language": language,
            }))
            raw_ready = await asyncio.wait_for(ws.recv(), timeout=5)
            ready = json.loads(raw_ready)
            if not isinstance(ready, dict) or ready.get("type") != "ready":
                raise RuntimeError("server did not acknowledge ready")
            return ws
        except asyncio.CancelledError:
            if ws is not None:
                await ws.close()
            raise
        except Exception:
            if ws is not None:
                try:
                    await ws.close()
                except Exception:
                    pass
            # websockets exceptions can retain the full URI including token.
            raise ConnectionError(
                "unable to establish a ready real-time STT session"
            ) from None

    def upload_recording(
        self,
        interaction_id: str,
        audio: bytes,
        media_type: str = "application/octet-stream",
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        if not audio:
            raise ValueError("audio cannot be empty")
        if len(audio) > self.MAX_RECORDING_BYTES:
            raise ValueError(f"audio exceeds {self.MAX_RECORDING_BYTES} bytes")
        normalized_media_type = media_type.split(";", 1)[0].strip().lower()
        supported = {
            "application/octet-stream", "audio/wav", "audio/x-wav",
            "audio/webm", "audio/mpeg", "audio/mp3", "audio/mpeg3",
            "audio/mp4", "audio/m4a", "audio/ogg", "audio/opus",
            "audio/vorbis", "audio/flac",
        }
        if normalized_media_type not in supported:
            raise ValueError(f"unsupported recording media type: {normalized_media_type or '<empty>'}")
        response = self._client.post(
            f"/api/v2/tools/interactions/{quote(interaction_id, safe='')}/recordings",
            content=audio,
            headers={"Content-Type": media_type},
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def list_recordings(
        self,
        interaction_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/v2/tools/interactions/{quote(interaction_id, safe='')}/recordings",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def download_recording(
        self,
        interaction_id: str,
        recording_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> bytes:
        response = self._client.get(
            f"/api/v2/tools/interactions/{quote(interaction_id, safe='')}/recordings/"
            f"{quote(recording_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.content

    def delete_recording(
        self,
        interaction_id: str,
        recording_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        response = self._client.delete(
            f"/api/v2/tools/interactions/{quote(interaction_id, safe='')}/recordings/"
            f"{quote(recording_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()

    def create_transcript(
        self,
        interaction_id: str,
        recording_id: str,
        *,
        primary_language: str = "zh-CN",
        async_: bool = False,
        is_dictation: bool = False,
        spoken_punctuation: Optional[bool] = None,
        automatic_punctuation: Optional[bool] = None,
        is_multichannel: bool = False,
        diarize: bool = False,
        participants: Optional[list[dict[str, Any]]] = None,
        replacements: Optional[list[dict[str, str]]] = None,
        keyterms: Optional[dict[str, list[dict[str, str]]]] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> HttpResult[dict[str, Any]]:
        if not primary_language.lower().startswith("zh"):
            raise ValueError("the verified STT runtime currently supports Chinese audio only")
        if diarize:
            raise ValueError("diarize is not supported by the verified STT runtime")
        participant_values = participants or []
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("channel"), int)
            or isinstance(item.get("channel"), bool)
            or item.get("role") not in {"doctor", "patient", "multiple"}
            for item in participant_values
        ):
            raise ValueError("participants require an integer channel and a supported role")
        if is_multichannel:
            channels = sorted(item["channel"] for item in participant_values)
            if len(participant_values) != 2 or channels != [0, 1]:
                raise ValueError(
                    "multichannel transcription requires participants for channels 0 and 1"
                )
        elif len(participant_values) > 1:
            raise ValueError("the verified STT runtime supports at most one participant mapping")
        if replacements and len(replacements) > 1000:
            raise ValueError("replacements cannot exceed 1000 items")
        if keyterms is not None and not isinstance(keyterms, dict):
            raise ValueError("keyterms must be an object containing terms")
        terms = (keyterms or {}).get("terms", [])
        if not isinstance(terms, list) or len(terms) > 1000:
            raise ValueError("keyterms cannot exceed 1000 items")
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("term"), str)
            or not 1 <= len(item["term"]) <= 50
            for item in terms
        ):
            raise ValueError("each keyterm must contain 1 to 50 characters")
        response = self._client.post(
            f"/api/v2/tools/interactions/{quote(interaction_id, safe='')}/transcripts",
            json={
                "recordingId": recording_id,
                "primaryLanguage": primary_language,
                "async": async_,
                "isDictation": is_dictation,
                "spokenPunctuation": spoken_punctuation,
                "automaticPunctuation": automatic_punctuation,
                "isMultichannel": is_multichannel,
                "diarize": diarize,
                "participants": participants,
                "replacements": replacements,
                "keyterms": keyterms,
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return HttpResult(
            data=response.json(),
            status_code=response.status_code,
            location=response.headers.get("Location"),
        )

    def list_transcripts(
        self,
        interaction_id: str,
        *,
        full: bool = False,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/v2/tools/interactions/{quote(interaction_id, safe='')}/transcripts",
            params={"full": str(full).lower()},
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def get_transcript(
        self,
        interaction_id: str,
        transcript_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/v2/tools/interactions/{quote(interaction_id, safe='')}/transcripts/"
            f"{quote(transcript_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def get_transcript_status(
        self,
        interaction_id: str,
        transcript_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/v2/tools/interactions/{quote(interaction_id, safe='')}/transcripts/"
            f"{quote(transcript_id, safe='')}/status",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def delete_transcript(
        self,
        interaction_id: str,
        transcript_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        response = self._client.delete(
            f"/api/v2/tools/interactions/{quote(interaction_id, safe='')}/transcripts/"
            f"{quote(transcript_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()
