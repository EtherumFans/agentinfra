import pytest
from app.icoder.agent_runtime.orchestrator.coding_compliance_orchestrator import CodingComplianceOrchestrator, STAGE_ORDER, REVIEW_BLOCKED

@pytest.mark.parametrize('stage', STAGE_ORDER)
@pytest.mark.parametrize('failure', ['rejected', 'timeout', 'cancelled'])
def test_any_stage_failure_cannot_be_auto_pass(stage, failure):
    def runner(current, text, context):
        if current == stage:
            if failure == 'timeout': raise TimeoutError('test timeout')
            return {'status':failure, 'error':True}
        return {'structured_sections':{'summary':'synthetic'}, 'codes':[{'code':'TEST'}]}
    result = CodingComplianceOrchestrator(runner).run(input_text='合成文档')
    assert result.review_gate_status == REVIEW_BLOCKED
    assert result.stage_errors[stage]
    assert result.completion.status == 'INCOMPLETE'
    assert result.completion.review_required is True
