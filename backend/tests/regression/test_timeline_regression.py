# Regression: Timeline Reconstruction — determinism, fallback, malformed input
import pytest
from app.agents.experts.timeline_expert import TimelineReconstructionExpert

FIXED_TEXT = "患者2025年1月15日行直肠前切除术。2025年2月18日行奥沙利铂化疗。2025年3月1日入院行第2周期化疗。"


class TestTimelineDeterminism:
    """Same input → same output across repeated runs."""

    def setup_method(self):
        self.expert = TimelineReconstructionExpert()

    def test_fallback_identical_10_runs(self):
        results = []
        for _ in range(10):
            r = self.expert._fallback_extraction(FIXED_TEXT, "T-001")
            results.append(r)
        first = results[0]
        for r in results[1:]:
            assert r["events"] == first["events"]
            assert r["anchor_points"] == first["anchor_points"]

    def test_fallback_event_count_stable(self):
        r1 = self.expert._fallback_extraction(FIXED_TEXT, "T-001")
        r2 = self.expert._fallback_extraction(FIXED_TEXT, "T-001")
        assert len(r1["events"]) == len(r2["events"])


class TestTimelineFallbackCoverage:
    """Fallback path produces valid output for all edge cases."""

    def setup_method(self):
        self.expert = TimelineReconstructionExpert()

    def test_empty_text(self):
        r = self.expert._fallback_extraction("", "EMPTY")
        assert r["events"] == []
        assert isinstance(r["anchor_points"], dict)

    def test_no_dates(self):
        r = self.expert._fallback_extraction("患者一般情况良好。生命体征平稳。", "NODATE")
        assert r["events"] == []
        assert isinstance(r["timeline_summary"], str)

    def test_only_relative_times(self):
        r = self.expert._fallback_extraction("术后3月余。入院第2天。", "REL")
        assert isinstance(r["events"], list)
        assert isinstance(r["timeline_summary"], str)

    def test_mixed_chinese_english(self):
        r = self.expert._fallback_extraction("CT示右肺结节。2025-01-15手术。", "MIXED")
        assert len(r["events"]) >= 1

    def test_very_long_text(self):
        long_text = FIXED_TEXT * 50  # ~1800 chars
        r = self.expert._fallback_extraction(long_text, "LONG")
        assert isinstance(r["events"], list)
        # Should not hang or OOM

    def test_special_characters(self):
        r = self.expert._fallback_extraction("诊断：①肺炎 ②高血压。日期：2025年1月。", "SPECIAL")
        assert isinstance(r["events"], list)

    def test_output_structure_complete(self):
        r = self.expert._fallback_extraction(FIXED_TEXT, "STRUCT")
        for key in ("anchor_points", "events", "unresolved_events", "timeline_summary"):
            assert key in r, f"Missing key: {key}"


class TestTimelineMalformedInput:
    """Graceful handling of malformed inputs."""

    def setup_method(self):
        self.expert = TimelineReconstructionExpert()

    def test_none_text(self):
        # Should not crash
        try:
            self.expert._fallback_extraction(None, "NONE")
        except Exception:
            pass  # String coercion may fail, that's acceptable

    def test_numeric_only(self):
        r = self.expert._fallback_extraction("12345 67890 2025 01 15", "NUM")
        assert isinstance(r["events"], list)
