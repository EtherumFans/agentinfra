"""Phase 5 Track B-2 — Fixtures Quality Gate

Validates the 12 synthetic fixtures per PDF §4 data gating requirements:
1. All fixtures present (12 total)
2. Required fields present (14 fields per fixture)
3. All tagged as SYNTHETIC_FIXTURE
4. input_text length ≤ 4000 chars
5. gold_codes follow ICD-10-CN format (when present)
6. not_for_quality_scoring fixtures flagged (3 expected: 10/11/12)
7. Negation word distribution in fixture 10
8. Conflict documentation in fixture 11
9. Missing information in fixture 12

Run: pytest backend/tests/test_api/test_phase5_b2_fixtures_quality.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "phase5_track_b2"
QUALITY_REPORT = (
    Path(__file__).resolve().parents[3]
    / "outputs"
    / "phase5_track_b2"
    / "fixture_quality_report.json"
)

EXPECTED_FIXTURE_IDS = [
    "01_orthopedics",
    "02_cardiology",
    "03_respiratory",
    "04_gastroenterology",
    "05_oncology",
    "06_obstetrics",
    "07_pediatrics",
    "08_general_surgery",
    "09_complex_comorbidity",
    "10_negation_and_history",
    "11_conflicting_documentation",
    "12_incomplete_documentation",
]

NOT_SCORING_IDS = {
    "10_negation_and_history",
    "11_conflicting_documentation",
    "12_incomplete_documentation",
}

REQUIRED_FIELDS = {
    "fixture_id",
    "tag",
    "department",
    "intended_agents",
    "input_text",
    "structured_context",
    "known_facts",
    "negated_facts",
    "historical_facts",
    "missing_information",
    "expected_risks",
    "gold_codes",
    "not_for_quality_scoring",
    "notes",
}

MAX_INPUT_LEN = 4000


def _load_fixture(fixture_id: str) -> dict:
    path = FIXTURES_DIR / f"{fixture_id}.json"
    if not path.exists():
        pytest.fail(f"Missing fixture file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def all_fixtures() -> dict[str, dict]:
    return {fid: _load_fixture(fid) for fid in EXPECTED_FIXTURE_IDS}


@pytest.fixture(scope="module")
def quality_report() -> dict:
    if not QUALITY_REPORT.exists():
        pytest.fail(f"Missing quality report: {QUALITY_REPORT}")
    return json.loads(QUALITY_REPORT.read_text(encoding="utf-8"))


class TestFixturesPresent:
    """All 12 fixtures must exist on disk."""

    def test_all_12_fixtures_present(self, all_fixtures):
        missing = set(EXPECTED_FIXTURE_IDS) - set(all_fixtures.keys())
        assert not missing, f"Missing fixtures: {missing}"

    def test_fixtures_directory_exists(self):
        assert FIXTURES_DIR.exists(), f"Fixtures dir missing: {FIXTURES_DIR}"
        files = list(FIXTURES_DIR.glob("*.json"))
        assert len(files) == 12, f"Expected 12 fixture files, found {len(files)}"


class TestRequiredFields:
    """All fixtures must have the 14 required fields."""

    @pytest.mark.parametrize("fixture_id", EXPECTED_FIXTURE_IDS)
    def test_required_fields_present(self, all_fixtures, fixture_id):
        fx = all_fixtures[fixture_id]
        missing = REQUIRED_FIELDS - set(fx.keys())
        assert not missing, f"{fixture_id} missing fields: {missing}"

    @pytest.mark.parametrize("fixture_id", EXPECTED_FIXTURE_IDS)
    def test_fixture_id_matches_filename(self, all_fixtures, fixture_id):
        fx = all_fixtures[fixture_id]
        assert fx["fixture_id"] == fixture_id


class TestSyntheticTag:
    """All fixtures must be tagged as SYNTHETIC_FIXTURE."""

    @pytest.mark.parametrize("fixture_id", EXPECTED_FIXTURE_IDS)
    def test_synthetic_tag(self, all_fixtures, fixture_id):
        fx = all_fixtures[fixture_id]
        assert fx["tag"] == "SYNTHETIC_FIXTURE", (
            f"{fixture_id} tag is '{fx['tag']}', expected 'SYNTHETIC_FIXTURE'"
        )


class TestInputLength:
    """input_text must be ≤ 4000 chars (PDF §4)."""

    @pytest.mark.parametrize("fixture_id", EXPECTED_FIXTURE_IDS)
    def test_input_under_max_length(self, all_fixtures, fixture_id):
        fx = all_fixtures[fixture_id]
        text_len = len(fx["input_text"])
        assert text_len <= MAX_INPUT_LEN, (
            f"{fixture_id} input_text too long: {text_len} > {MAX_INPUT_LEN}"
        )

    @pytest.mark.parametrize("fixture_id", EXPECTED_FIXTURE_IDS)
    def test_input_not_empty(self, all_fixtures, fixture_id):
        fx = all_fixtures[fixture_id]
        assert fx["input_text"].strip(), f"{fixture_id} input_text is empty"


class TestGoldCodesFormat:
    """Gold codes (when present) must follow ICD-10-CN format."""

    @pytest.mark.parametrize("fixture_id", EXPECTED_FIXTURE_IDS)
    def test_gold_codes_format(self, all_fixtures, fixture_id):
        fx = all_fixtures[fixture_id]
        for code in fx["gold_codes"]:
            assert len(code) >= 4, f"{fixture_id} code too short: {code}"
            assert code[0].isalpha(), f"{fixture_id} code must start with letter: {code}"
            assert code[1:3].isdigit(), f"{fixture_id} code[1:3] must be digits: {code}"


class TestQualityScoringFlag:
    """not_for_quality_scoring must be true for fixtures 10/11/12."""

    @pytest.mark.parametrize("fixture_id", EXPECTED_FIXTURE_IDS)
    def test_scoring_flag(self, all_fixtures, fixture_id):
        fx = all_fixtures[fixture_id]
        expected = fixture_id in NOT_SCORING_IDS
        assert fx["not_for_quality_scoring"] == expected, (
            f"{fixture_id} not_for_quality_scoring should be {expected}"
        )

    def test_nine_scoring_eligible(self, quality_report):
        assert quality_report["scoring_eligible_count"] == 9

    def test_three_not_scoring(self, quality_report):
        assert quality_report["not_scoring_count"] == 3


class TestNegationDistribution:
    """Fixture 10 must contain 5+ negation words (否认/排除/既往/已治愈/家族史/疑似/待排/无)."""

    def test_fixture_10_negation_density(self, all_fixtures):
        fx = all_fixtures["10_negation_and_history"]
        neg_words = ["否认", "排除", "既往", "已治愈", "家族史", "疑似", "待排", "无"]
        count = sum(1 for w in neg_words if w in fx["input_text"])
        assert count >= 5, (
            f"Fixture 10 negation density insufficient: {count}/8 negation words present"
        )

    def test_fixture_10_negated_facts_populated(self, all_fixtures):
        fx = all_fixtures["10_negation_and_history"]
        assert len(fx["negated_facts"]) >= 5


class TestConflictFixture:
    """Fixture 11 must contain both 左 and 右 in input_text (left/right conflict)."""

    def test_fixture_11_has_conflict(self, all_fixtures):
        fx = all_fixtures["11_conflicting_documentation"]
        assert "左" in fx["input_text"], "Fixture 11 missing 左 side mention"
        assert "右" in fx["input_text"], "Fixture 11 missing 右 side mention"

    def test_fixture_11_known_facts_include_admission_and_discharge(
        self, all_fixtures
    ):
        fx = all_fixtures["11_conflicting_documentation"]
        facts_text = " ".join(fx["known_facts"])
        assert "左侧" in facts_text, "Missing admission LEFT fact"
        assert "右侧" in facts_text, "Missing discharge RIGHT fact"


class TestIncompleteFixture:
    """Fixture 12 must have 8+ missing_information items."""

    def test_fixture_12_missing_info_count(self, all_fixtures):
        fx = all_fixtures["12_incomplete_documentation"]
        assert len(fx["missing_information"]) >= 8, (
            f"Fixture 12 missing_information insufficient: {len(fx['missing_information'])}"
        )

    def test_fixture_12_no_gold_codes(self, all_fixtures):
        fx = all_fixtures["12_incomplete_documentation"]
        assert fx["gold_codes"] == [], "Fixture 12 should not have gold codes"


class TestDepartmentCoverage:
    """Verify department diversity across fixtures."""

    def test_department_diversity(self, quality_report):
        depts = quality_report["department_distribution"]
        assert len(depts) >= 8, (
            f"Department diversity insufficient: {len(depts)} unique departments"
        )

    def test_no_empty_department(self, all_fixtures):
        for fid, fx in all_fixtures.items():
            assert fx["department"], f"{fid} has empty department"


class TestQualityReport:
    """The generated quality report must show 0 issues."""

    def test_zero_issues(self, quality_report):
        assert quality_report["total_issues"] == 0, (
            f"Quality report has issues: {quality_report['issues']}"
        )

    def test_total_fixtures_12(self, quality_report):
        assert quality_report["total_fixtures"] == 12

    def test_all_synthetic_tagged(self, quality_report):
        assert quality_report["all_synthetic_tagged"] is True

    def test_all_required_fields_present(self, quality_report):
        assert quality_report["all_required_fields_present"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
