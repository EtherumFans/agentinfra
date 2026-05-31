"""Reviews (medical coding) resource."""

from __future__ import annotations
from ..client import iCoDerClient
from ..types import Review


class ReviewsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def create(self, encounter_id: str, coding_systems: list[str] | None = None,
               async_mode: bool = False) -> Review:
        params = {"async": "true"} if async_mode else {}
        resp = self._client.post("/api/reviews", json={
            "encounter_id": encounter_id,
            "coding_systems": coding_systems,
        }, params=params)
        resp.raise_for_status()
        data = resp.json()
        return Review(**{k: v for k, v in data.items() if k in Review.__dataclass_fields__})

    def get(self, review_id: str) -> dict:
        resp = self._client.get(f"/api/reviews/{review_id}")
        resp.raise_for_status()
        return resp.json()

    def list(self, page: int = 1, page_size: int = 20) -> dict:
        resp = self._client.get("/api/reviews", params={"page": page, "page_size": page_size})
        resp.raise_for_status()
        return resp.json()

    def review_candidate(self, review_id: str, candidate_id: str, decision: str,
                         reason: str, modified_code: str = "", modified_name: str = "") -> dict:
        resp = self._client.put(f"/api/reviews/{review_id}/candidates/{candidate_id}/review", json={
            "candidate_id": candidate_id, "decision": decision, "reason": reason,
            "modified_code": modified_code, "modified_name": modified_name,
        })
        resp.raise_for_status()
        return resp.json()

    def complete(self, review_id: str, notes: str = "") -> dict:
        resp = self._client.put(f"/api/reviews/{review_id}/complete", json={
            "reviewer_notes": notes, "human_review_status": "completed",
        })
        resp.raise_for_status()
        return resp.json()
