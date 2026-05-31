"""Text Generation resource."""

from ..client import iCoDerClient


class TextGenResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def templates(self) -> dict:
        resp = self._client.get("/api/text-gen/templates")
        resp.raise_for_status()
        return resp.json()

    def generate(self, input_text: str, template: str = "", output_language: str = "zh-CN",
                 doc_name: str = "", max_tokens: int = 2000, temperature: float = 0.3) -> dict:
        resp = self._client.post("/api/text-gen/generate", json={
            "input": input_text, "template": template,
            "output_language": output_language, "doc_name": doc_name,
            "max_tokens": max_tokens, "temperature": temperature,
        })
        resp.raise_for_status()
        return resp.json()
