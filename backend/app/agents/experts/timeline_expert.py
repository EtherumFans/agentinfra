# iCoDer — Clinical Timeline Reconstruction Expert
import re
import time
import logging
from datetime import datetime

from app.agents.base import BaseExpert

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert clinical timeline reconstruction system for Chinese inpatient medical records.

Your task: reconstruct a chronological timeline of ALL clinical events from the patient's medical documents.

## Extraction Rules

1. **Event Types** — classify each event into one of:
   - symptom_onset: initial symptom appearance
   - diagnosis: diagnosis confirmed or suspected
   - surgery: surgical procedure performed
   - chemotherapy: chemotherapy cycle or infusion
   - radiotherapy: radiation therapy session
   - lab_test: significant lab result reported
   - imaging: imaging study (CT, MRI, ultrasound, X-ray) and findings
   - pathology: pathology report results including IHC
   - admission: hospital admission
   - discharge: hospital discharge
   - medication: significant medication start/change
   - complication: adverse events or complications
   - consultation: specialist consultation
   - transfer: transfer between departments
   - other: other notable clinical events

2. **Temporal Extraction** — for each event, extract:
   - Absolute date if present (YYYY-MM-DD format, even if only YYYY-MM)
   - Relative time expression (e.g. "术后3月余", "入院第2天", "4月前", "5年前")
   - Which anchor point it relates to (admission, surgery, chemotherapy_start, etc.)

3. **Anchor Points** — identify key temporal anchors:
   - admission_date: the admission date for THIS encounter
   - discharge_date: discharge date if mentioned
   - surgery_date: most recent surgery date
   - diagnosis_confirmed_date: when the definitive diagnosis was made
   - other_anchors: any other significant dates (e.g. chemotherapy dates, prior surgery dates)

4. **Chronological Order** — order ALL events chronologically from earliest to latest.
   Include pre-admission events (prior surgeries, prior chemo cycles, symptom onset) BEFORE admission.

5. **Cross-document Dedup** — if the same event appears in multiple documents, merge into one event
   citing the most authoritative source (手术记录 > 出院小结 > 现病史 > 主诉).

6. **Confidence** — assign confidence 0–1:
   - 0.9–1.0: explicit date + clear event description
   - 0.7–0.9: relative time clearly anchored
   - 0.5–0.7: inferred from context
   - 0.3–0.5: ambiguous temporal reference

Output ONLY valid JSON. Do not add explanations outside the JSON."""

SCHEMA_HINT = """{
  "anchor_points": {
    "admission_date": "YYYY-MM-DD or null",
    "discharge_date": "YYYY-MM-DD or null",
    "surgery_date": "YYYY-MM-DD or null",
    "diagnosis_confirmed_date": "YYYY-MM-DD or null",
    "other_anchors": {"chemotherapy_cycle1": "YYYY-MM-DD", "prior_surgery": "YYYY-MM-DD"}
  },
  "events": [
    {
      "event_type": "symptom_onset|diagnosis|surgery|chemotherapy|radiotherapy|lab_test|imaging|pathology|admission|discharge|medication|complication|consultation|transfer|other",
      "description": "中文事件描述",
      "timestamp": "YYYY-MM-DD or null",
      "relative_time": "术后3月余 or 4月前 or null",
      "source_document": "主诉|现病史|既往史|体格检查|出院小结|手术记录",
      "source_text": "原文中的确切片段",
      "confidence": 0.9,
      "anchor": "surgery_date or admission_date or null"
    }
  ],
  "unresolved_events": [
    {
      "event_type": "...",
      "description": "...",
      "timestamp": null,
      "relative_time": "...",
      "source_document": "...",
      "source_text": "...",
      "confidence": 0.3,
      "anchor": null
    }
  ],
  "timeline_summary": "自然语言总结该病例的临床经过，2-4句话"
}"""


class TimelineReconstructionExpert(BaseExpert):
    name = "Timeline Reconstruction Expert"
    description = "Reconstructs chronological clinical timeline from encounter documents — extracts temporal events, resolves anchors, sequences events"

    async def run(self, context: dict) -> dict:
        start = time.time()
        encounter_id = context.get("encounter_id", "unknown")
        self._log_step("reconstructing timeline", context)

        documents = context.get("documents", [])
        combined_text = self._build_combined_text(documents)

        if not combined_text.strip():
            return self._timed_result(start, self._empty_result(encounter_id))

        try:
            result = await self.llm.extract_json(
                "Reconstruct the complete clinical timeline from these Chinese medical documents. "
                "Extract all events with temporal information and order them chronologically. "
                "Include pre-admission events (prior surgeries, prior treatments, symptom onset). "
                "Output valid JSON only.",
                combined_text,
                SCHEMA_HINT,
            )
        except Exception as e:
            self._log_step(f"LLM timeline extraction failed, using fallback: {e}", context)
            result = self._fallback_extraction(combined_text, encounter_id)

        return self._timed_result(start, {
            "expert": self.name,
            "timeline": {
                "encounter_id": encounter_id,
                "anchor_points": result.get("anchor_points", {}),
                "events": result.get("events", []),
                "unresolved_events": result.get("unresolved_events", []),
                "timeline_summary": result.get("timeline_summary", ""),
            },
            "event_count": len(result.get("events", [])),
            "unresolved_count": len(result.get("unresolved_events", [])),
            "doc_count": len(documents),
        })

    def _build_combined_text(self, documents: list[dict]) -> str:
        parts = []
        for i, doc in enumerate(documents):
            doc_type = doc.get("doc_type", "unknown")
            title = doc.get("title", "")
            content = doc.get("content", "")
            parts.append(f"--- Document {i+1}: {doc_type} {title} ---\n{content}")
        return "\n\n".join(parts)

    def _empty_result(self, encounter_id: str) -> dict:
        return {
            "expert": self.name,
            "timeline": {
                "encounter_id": encounter_id,
                "anchor_points": {},
                "events": [],
                "unresolved_events": [],
                "timeline_summary": "",
            },
            "event_count": 0,
            "unresolved_count": 0,
            "doc_count": 0,
        }

    def _fallback_extraction(self, text: str, encounter_id: str) -> dict:
        """Regex-based fallback when LLM is unavailable. Extracts dates and event descriptions."""
        events = []
        anchor_points = {}

        # Extract explicit dates: YYYY年M月D日, YYYY年M月, YYYY-MM-DD
        date_patterns = [
            (r"(\d{4})年(\d{1,2})月(\d{1,2})日", lambda m: (f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", m.group(0))),
            (r"(\d{4})年(\d{1,2})月", lambda m: (f"{m.group(1)}-{int(m.group(2)):02d}", m.group(0))),
            (r"(\d{4})-(\d{2})-(\d{2})", lambda m: (f"{m.group(1)}-{m.group(2)}-{m.group(3)}", m.group(0))),
        ]

        found_dates = []
        for pattern, fmt_fn in date_patterns:
            for m in re.finditer(pattern, text):
                formatted, original = fmt_fn(m)
                found_dates.append((m.start(), m.end(), formatted, original))

        # Extract event-like sentences that contain dates
        sentences = re.split(r"[。！；\n]", text)
        date_events = []
        for sent in sentences:
            sent = sent.strip()
            if not sent or len(sent) < 6:
                continue
            for start, end, date_str, original in found_dates:
                # Check either formatted or original text appears in sentence
                if date_str in sent or original in sent:
                    date_events.append({
                        "event_type": "other",
                        "description": sent[:120],
                        "timestamp": date_str,
                        "relative_time": None,
                        "source_document": "unknown",
                        "source_text": sent[:200],
                        "confidence": 0.3,
                        "anchor": None,
                    })
                    break

        # Identify anchor dates — check original text near date match positions
        def _near_text(pos: int, span: int = 20) -> str:
            return text[max(0, pos - span):pos + span]

        surgery_dates = [d for d in found_dates if any(kw in _near_text(d[0]) for kw in ["手术", "切除术", "成形术", "根治术", "活检"])]
        admission_dates = [d for d in found_dates if any(kw in _near_text(d[0]) for kw in ["入院", "收入院"])]

        if admission_dates:
            anchor_points["admission_date"] = admission_dates[0][2]
        if surgery_dates:
            anchor_points["surgery_date"] = surgery_dates[0][2]

        # Deduplicate by description
        seen = set()
        unique_events = []
        for e in date_events:
            key = e["description"][:40]
            if key not in seen:
                seen.add(key)
                unique_events.append(e)

        return {
            "anchor_points": anchor_points,
            "events": unique_events,
            "unresolved_events": [],
            "timeline_summary": f"Fallback extraction: {len(unique_events)} events found via regex.",
        }
