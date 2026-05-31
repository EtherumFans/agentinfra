"""Speech To Text resource."""

import json
from ..client import iCoDerClient


class SpeechToTextResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    async def create_session_async(self, language: str = "zh-CN",
                                   punctuation: str = "auto",
                                   interim_results: bool = True):
        """Create a WebSocket STT session (async). Requires websockets library."""
        try:
            import websockets
        except ImportError:
            raise ImportError("websockets library required. Install: pip install websockets")

        ws_url = self._client.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws = await websockets.connect(f"{ws_url}/ws/speech-to-text")
        await ws.send(json.dumps({"type": "start", "mimeType": "audio/webm;codecs=opus"}))
        return ws

    def punctuate(self, text: str) -> dict:
        """Refine punctuation in transcribed text."""
        resp = self._client.post("/api/experts/stt/punctuate", json={"text": text})
        resp.raise_for_status()
        return resp.json()
