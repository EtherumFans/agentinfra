# Timeline Reconstruction Expert — unit tests
import pytest
from app.agents.experts.timeline_expert import TimelineReconstructionExpert
from app.schemas.timeline import ClinicalTimeline, ClinicalEvent, AnchorPoints


class TestTimelineFallback:
    """Test regex-based fallback extraction (no LLM required)."""

    def setup_method(self):
        self.expert = TimelineReconstructionExpert()

    def test_extracts_dates_from_chinese_text(self):
        text = "患者2025年1月15日行直肠前切除术。术后于2025年2月18日行奥沙利铂化疗。"
        result = self.expert._fallback_extraction(text, "TEST-001")
        events = result["events"]
        assert len(events) >= 2
        dates_found = [e["timestamp"] for e in events]
        assert "2025-01-15" in dates_found or "2025-02-18" in dates_found

    def test_extracts_surgery_as_anchor(self):
        text = "2025年1月15日行直肠前切除术+结肠造口术。"
        result = self.expert._fallback_extraction(text, "TEST-001")
        assert "surgery_date" in result["anchor_points"]

    def test_extracts_admission_as_anchor(self):
        text = "患者2025年3月10日入院。主诉：腹痛。"
        result = self.expert._fallback_extraction(text, "TEST-001")
        assert "admission_date" in result["anchor_points"]

    def test_empty_text(self):
        result = self.expert._fallback_extraction("", "TEST-001")
        assert result["events"] == []
        assert result["anchor_points"] == {}

    def test_dedup_identical_events(self):
        text = "2025年1月15日行直肠前切除术。2025年1月15日行直肠前切除术。"
        result = self.expert._fallback_extraction(text, "TEST-001")
        # Should not have duplicate events
        descriptions = [e["description"] for e in result["events"]]
        unique = set(d[:40] for d in descriptions)
        assert len(unique) == len(result["events"])

    def test_relative_time_not_crashed(self):
        text = "术后3月余，为行辅助化疗入院。患者3月前因左乳腺肿物就诊。"
        result = self.expert._fallback_extraction(text, "TEST-001")
        assert isinstance(result["events"], list)

    def test_no_dates_returns_empty_events(self):
        text = "患者一般情况良好，生命体征平稳。"
        result = self.expert._fallback_extraction(text, "TEST-001")
        assert result["events"] == []

    def test_mixed_date_formats(self):
        text = "2025-01-15手术。2025年2月18日化疗。2025年3月复查。"
        result = self.expert._fallback_extraction(text, "TEST-001")
        assert len(result["events"]) >= 1

    def test_demo_case_002_has_events(self):
        """DEMO-002 (骨科 腰痛) — fallback extracts date-anchored events only."""
        text = ("腰痛4月余。患者2025年1月10日无明显诱因出现腰部疼痛，伴双下肢放射痛。"
                "2025年1月15日MRI示腰椎多发压迫性改变，L3/4、L4/5椎间盘突出。"
                "2025年1月20日入院行手术治疗。5年前因腰椎间盘突出行保守治疗。")
        result = self.expert._fallback_extraction(text, "TEST-002")
        assert len(result["events"]) >= 1


class TestTimelineSchema:
    """Test Pydantic schema validation."""

    def test_valid_event(self):
        event = ClinicalEvent(
            event_type="surgery",
            description="直肠前切除术",
            timestamp="2025-01-15T00:00:00",
            relative_time="入院前2月",
            source_document="现病史",
            source_text="2025年1月15日行直肠前切除术",
            confidence=0.9,
            anchor="surgery_date",
        )
        assert event.event_type == "surgery"
        assert event.confidence == 0.9

    def test_valid_timeline(self):
        tl = ClinicalTimeline(
            encounter_id="DEMO-001",
            anchor_points=AnchorPoints(admission_date="2025-03-01T00:00:00"),
            events=[
                ClinicalEvent(
                    event_type="admission",
                    description="入院",
                    source_document="主诉",
                    source_text="入院",
                    confidence=0.9,
                )
            ],
            timeline_summary="患者入院接受化疗。",
        )
        assert tl.encounter_id == "DEMO-001"
        assert len(tl.events) == 1
        assert tl.timeline_summary == "患者入院接受化疗。"

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            ClinicalEvent(
                event_type="other",
                description="test",
                source_document="test",
                source_text="test",
                confidence=1.5,
            )
        with pytest.raises(Exception):
            ClinicalEvent(
                event_type="other",
                description="test",
                source_document="test",
                source_text="test",
                confidence=-0.1,
            )

    def test_json_roundtrip(self):
        tl = ClinicalTimeline(
            encounter_id="DEMO-001",
            events=[
                ClinicalEvent(
                    event_type="surgery",
                    description="直肠前切除术",
                    timestamp="2025-01-15T00:00:00",
                    source_document="现病史",
                    source_text="2025年1月15日行直肠前切除术",
                    confidence=0.9,
                ),
                ClinicalEvent(
                    event_type="chemotherapy",
                    description="奥沙利铂+卡培他滨方案化疗",
                    timestamp="2025-02-18T00:00:00",
                    source_document="现病史",
                    source_text="2025年2月18日行奥沙利铂+卡培他滨方案化疗1周期",
                    confidence=0.85,
                ),
            ],
            timeline_summary="直肠癌术后辅助化疗。",
        )
        json_str = tl.model_dump_json()
        rehydrated = ClinicalTimeline.model_validate_json(json_str)
        assert rehydrated.encounter_id == "DEMO-001"
        assert len(rehydrated.events) == 2
        # Events should be in the order we specified
        assert rehydrated.events[0].description == "直肠前切除术"
        assert rehydrated.events[1].description == "奥沙利铂+卡培他滨方案化疗"


class TestTimelineExpertAsyncRun:
    """Test the full async run() method."""

    @pytest.mark.asyncio
    async def test_run_with_demo_documents(self):
        expert = TimelineReconstructionExpert()
        context = {
            "encounter_id": "DEMO-002",
            "documents": [
                {
                    "doc_type": "主诉",
                    "title": "主诉",
                    "content": "腰痛4月余。患者4月前无明显诱因出现腰部疼痛，伴双下肢放射痛，活动时加重，平卧休息时缓解。MRI示腰椎间盘突出，L3/4、L4/5椎管狭窄。"
                },
                {
                    "doc_type": "现病史",
                    "title": "现病史",
                    "content": "患者4月前出现腰部疼痛。MRI：腰椎多发压迫性改变。5年前因腰椎间盘突出行保守治疗。"
                },
            ],
        }
        result = await expert.run(context)
        assert result["expert"] == "Timeline Reconstruction Expert"
        timeline = result.get("timeline", {})
        assert timeline["encounter_id"] == "DEMO-002"
        assert isinstance(timeline.get("events", []), list)
        assert isinstance(timeline.get("unresolved_events", []), list)
        assert "event_count" in result
        assert "doc_count" in result
        assert result["doc_count"] == 2

    @pytest.mark.asyncio
    async def test_run_with_empty_documents(self):
        expert = TimelineReconstructionExpert()
        context = {
            "encounter_id": "EMPTY-001",
            "documents": [],
        }
        result = await expert.run(context)
        assert result["expert"] == "Timeline Reconstruction Expert"
        assert result["doc_count"] == 0
        assert result["event_count"] == 0


@pytest.mark.asyncio
@pytest.mark.xfail(reason="LLM response varies between runs")
async def test_timeline_in_pipeline_result(auth_client):
    """Full pipeline should include 'timeline' key in response (requires seeded data)."""
    resp = await auth_client.post("/api/reviews", json={
        "encounter_id": "DEMO-002",
        "async_mode": False,
    })
    if resp.status_code == 404:
        pytest.skip("DEMO-002 not seeded — run 'python -m app.seed' first")
    assert resp.status_code == 200
    data = resp.json()
    assert "timeline" in data, f"Timeline key missing from response. Keys: {list(data.keys())}"
    timeline = data["timeline"]
    assert "events" in timeline
    assert "encounter_id" in timeline
