"""Text Generation resource."""

from typing import Optional

from ..client import iCoDerClient
from ..request_options import RequestOptions


class TextGenResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def templates(self, request_options: Optional[RequestOptions] = None) -> dict:
        resp = self._client.get(
            "/api/v2/tools/templates/", request_options=request_options,
        )
        resp.raise_for_status()
        return {"templates": [{
            "key": item["id"],
            "name": item["name"],
            "desc": item.get("description", ""),
            "category": ", ".join(item.get("specialties", [])) or "Guided Documents",
            "sample": "",
        } for item in resp.json()]}

    def generate(
        self,
        input_text: str,
        template: str = "",
        output_language: str = "zh-CN",
        doc_name: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.3,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        if not input_text.strip():
            raise ValueError("input_text must not be empty")
        if doc_name.strip() or max_tokens != 2000 or temperature != 0.3:
            raise ValueError(
                "doc_name, max_tokens, and temperature are not supported by Guided Documents"
            )
        name = template.strip() or "Clinical document"
        resp = self._client.post(
            "/api/v2/tools/guided-documents",
            json={
                "outputLanguage": output_language,
                "context": [{"type": "text", "text": input_text}],
                "dynamicTemplate": {
                    "name": name,
                    "generation": {
                        "instructions": {
                            "prompt": (
                                f"Generate {name} from the supplied clinical context. "
                                "Do not invent undocumented facts."
                            )
                        },
                        "sections": [{
                            "heading": name,
                            "instructions": {
                                "contentPrompt": (
                                    f"Write the {name} using only the supplied clinical context."
                                )
                            },
                            "outputSchema": {"type": "string"},
                        }],
                    },
                },
            },
            headers={"X-Corti-Retention-Policy": "none"},
            request_options=request_options,
        )
        resp.raise_for_status()
        if resp.headers.get("X-Corti-Retention-Policy") != "acknowledged":
            raise RuntimeError("server did not acknowledge the zero-retention policy")
        data = resp.json()
        return {
            "output": "\n\n".join(data["document"]["stringDocument"].values()),
            "credits_consumed": data["usageInfo"]["creditsConsumed"],
        }
