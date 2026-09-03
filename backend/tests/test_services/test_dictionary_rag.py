"""Tests for the dictionary RAG helper (Phase 1 of F1 0.76 → 0.85+ plan).

The RAG helper extracts medical keywords from encounter text and looks up
top ICD-10 candidates from CodeDictionaryService. These tests verify the
extraction is selective, the lookup is correct, and the prompt block
formatting is stable.
"""
import pytest

from icoder_runtime.providers.medical_coding.dictionary_rag import (
    extract_keywords,
    format_candidates_block,
    _extract_user_text,
)


class TestExtractKeywords:
    def test_picks_clinical_terms_first(self):
        # 骨质疏松 + 椎体压缩骨折 are curated trigger terms; should appear first
        text = "患者因骨质疏松伴椎体压缩骨折入院，给予降钙素治疗"
        kws = extract_keywords(text)
        assert "骨质疏松" in kws
        assert "椎体压缩骨折" in kws

    def test_drops_stopwords(self):
        text = "患者因高血压入院，给予降压治疗，住院后症状好转"
        kws = extract_keywords(text)
        # Common stopwords should never appear
        for sw in ["患者", "因", "入院", "给予", "治疗", "后", "症状", "好转"]:
            assert sw not in kws, f"stopword {sw!r} leaked into keywords: {kws}"

    def test_limits_to_max_keywords(self):
        text = "高血压 糖尿病 冠心病 脑梗死 肺炎 骨折 关节炎 哮喘 肝硬化 胰腺炎"
        kws = extract_keywords(text, max_keywords=3)
        assert len(kws) <= 3

    def test_empty_text(self):
        assert extract_keywords("") == []

    def test_english_procedure_alias_maps_to_chinese_catalog_query(self):
        kws = extract_keywords(
            "Underwent laparoscopic appendectomy; surgery uneventful."
        )
        assert "腹腔镜下阑尾切除术" in kws

    def test_parallel_chinese_chart_uses_same_canonical_queries(self):
        kws = extract_keywords(
            "2 型糖尿病性酮症酸中毒，行腹腔镜阑尾切除术"
        )
        assert "2型糖尿病伴有酮症酸中毒" in kws
        assert "腹腔镜下阑尾切除术" in kws

    def test_no_clinical_terms_falls_back_to_ngrams(self):
        # No curated triggers, no obvious clinical terms — should still return
        # something (or empty) without crashing
        text = "天 气 很 好 我 们 出 去 玩"
        kws = extract_keywords(text, max_keywords=4)
        # Either returns a few n-gram tokens, or empty. Must not crash.
        assert isinstance(kws, list)
        for kw in kws:
            assert len(kw) >= 2  # minimum 2-char n-gram


class TestFormatCandidatesBlock:
    def test_empty_candidates_returns_empty_string(self):
        assert format_candidates_block([]) == ""

    def test_chinese_header_present(self):
        cands = [{"code": "M80.900", "name": "老年性骨质疏松", "score": 0.85, "chapter": "M"}]
        block = format_candidates_block(cands)
        assert "候选编码参考" in block
        assert "M80.900" in block
        assert "老年性骨质疏松" in block

    def test_catalog_boundary_message(self):
        cands = [{"code": "I50.9", "name": "心衰", "score": 0.8, "chapter": "I"}]
        block = format_candidates_block(cands)
        assert "病历证据为准" in block
        assert "不得缩写、扩写" in block

    def test_score_rounded_to_2dp(self):
        cands = [{"code": "I10", "name": "高血压", "score": 0.8765, "chapter": "I"}]
        block = format_candidates_block(cands)
        # The format spec is f"{score:.2f}"
        assert "0.88" in block


class TestExtractUserText:
    def test_last_user_message_wins(self):
        msgs = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "first user msg"},
            {"role": "assistant", "content": "first reply"},
            {"role": "user", "content": "second user msg"},
        ]
        assert _extract_user_text(msgs) == "second user msg"

    def test_no_user_message(self):
        assert _extract_user_text([{"role": "system", "content": "x"}]) == ""

    def test_empty_messages(self):
        assert _extract_user_text([]) == ""
        assert _extract_user_text(None) == ""


@pytest.mark.asyncio
class TestLookupCandidateCodes:
    async def test_returns_catalog_osteoporosis_code_without_inferred_pathology(self):
        from icoder_runtime.providers.medical_coding.dictionary_rag import lookup_candidate_codes
        text = "重度骨质疏松伴椎体压缩骨折，高龄女性"
        cands = await lookup_candidate_codes(text, max_total=5)
        assert len(cands) > 0
        # The chart documents osteoporosis but does not explicitly call the
        # fracture pathological. Retrieval must surface M81.900 rather than
        # manufacturing an M80 causal linkage.
        codes = [c["code"] for c in cands]
        assert "M81.900" in codes

    async def test_returns_I50_for_heart_failure(self):
        from icoder_runtime.providers.medical_coding.dictionary_rag import lookup_candidate_codes
        text = "充血性心力衰竭 NYHA III级"
        cands = await lookup_candidate_codes(text, max_total=5)
        codes = [c["code"] for c in cands]
        assert any(c.startswith("I50") for c in codes), f"no I50 in {codes}"

    async def test_deduplicates_codes(self):
        from icoder_runtime.providers.medical_coding.dictionary_rag import lookup_candidate_codes
        # Multiple keywords that may map to the same code
        text = "高血压 高血压性心脏病 高血压病"
        cands = await lookup_candidate_codes(text, max_total=10)
        codes = [c["code"] for c in cands]
        assert len(codes) == len(set(codes)), f"duplicates in {codes}"

    async def test_empty_text_returns_empty(self):
        from icoder_runtime.providers.medical_coding.dictionary_rag import lookup_candidate_codes
        assert await lookup_candidate_codes("") == []

    async def test_combined_request_returns_governed_procedure_candidate(self):
        from icoder_runtime.providers.medical_coding.dictionary_rag import lookup_candidate_codes

        cands = await lookup_candidate_codes(
            "急性阑尾炎，行腹腔镜阑尾切除术。",
            max_total=12,
            coding_systems=("icd10cn", "icd9cm3"),
        )

        assert any(
            item["coding_system"] == "icd9cm3"
            and item["code"] == "47.0100"
            for item in cands
        )
