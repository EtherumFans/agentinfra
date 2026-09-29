import pytest
from official_agents.note_completeness.agent import run_deterministic
from official_agents.note_completeness.agent_legacy import _has_meaningful_content

@pytest.mark.parametrize('text', ['未记录', '待补充。', '不详', '未明确', 'TBD', '未记录；待补'])
def test_placeholder_is_not_documented_content(text):
    assert not _has_meaningful_content(text)

@pytest.mark.parametrize('text', ['无过敏史', '否认手术史', '未记录体温，已联系医生补充', '无特殊', '无'])
def test_documented_negation_or_explanation_remains_content(text):
    assert _has_meaningful_content(text)

@pytest.mark.asyncio
async def test_audit_sample_cannot_score_full_completeness():
    result = await run_deterministic('主诉：咳嗽。现病史：咳嗽三天。既往史：无特殊。体格检查：未记录。辅助检查：未记录。诊断：未明确。治疗经过：观察。', run_id='audit-placeholder')
    assert result['review_conclusion'] != 'PASS'
    assert result['completeness_score'] < 1
    assert {v['section'] for v in result['incomplete_sections']} >= {'体格检查', '辅助检查', '诊断'}
    assert result['manual_review_required'] is True
