from types import SimpleNamespace
import pytest
from app.api.coding_compliance import _build_in_process_runner
from app.api import agent_run

def test_bridge_preserves_source_and_attested_candidates(monkeypatch):
    requests = []
    async def fake_run(**kwargs):
        requests.append(kwargs['body'].input)
        return {'run_id':f'run-{len(requests)}', 'trace_id':'trace', 'schema_ref':'schema',
                'result_attestation':'test-attestation', 'result':{'codes':[{'code':'TEST', 'evidence':{'start':0,'end':2}}]}, 'error':False}
    monkeypatch.setattr(agent_run, 'run_agent', fake_run)
    run = _build_in_process_runner(SimpleNamespace())
    first = run('first', 'formatted stage input', {'source_text':'合成原文'})
    second = run('second', 'different stage input', {'source_text':'合成原文'})
    assert first['codes'] == second['codes']
    assert requests[0].documents == requests[1].documents
    assert requests[1].documents[0].text == '合成原文'
    assert requests[1].upstream_results[0].result['codes'] == first['codes']
    assert requests[1].upstream_results[0].attestation == 'test-attestation'

def test_bridge_rejection_never_becomes_success(monkeypatch):
    async def fake_run(**kwargs): return {'error':True, 'error_reason':'provider_unavailable', 'result':{}}
    monkeypatch.setattr(agent_run, 'run_agent', fake_run)
    with pytest.raises(RuntimeError, match='provider_unavailable'):
        _build_in_process_runner(SimpleNamespace())('first', 'synthetic', {})
