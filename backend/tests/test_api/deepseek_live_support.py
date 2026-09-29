"""Opt-in live acceptance helpers; never load credentials or call APIs at import."""
import json
import os


async def configure_live_gateway(monkeypatch):
    from app.main import app
    from icoder_runtime.backends import registry
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    from icoder_runtime.core.llm_gateway import DeepSeekProvider, LLMGateway

    assert os.environ.get('ICODER_LIVE_DEEPSEEK_ACCEPTANCE') == '1'
    assert os.environ.get('ICODER_CREDENTIAL_LLM', '').strip()
    assert os.environ.get('LLM_BASE_URL') == 'https://api.deepseek.com'
    assert os.environ.get('LLM_MODEL') == 'deepseek-v4-flash'
    evidence = {'calls': [], 'structured_output': False, 'native_stream': False}
    provider = DeepSeekProvider(
        api_key=os.environ['ICODER_CREDENTIAL_LLM'],
        base_url=os.environ['LLM_BASE_URL'], model=os.environ['LLM_MODEL'],
        max_tokens=2048, timeout=120,
    )
    gateway = LLMGateway(data_policy=RuntimeDataPolicy.from_env())
    gateway.register(provider, default=True)
    generate = gateway.generate

    def record(result, kind):
        assert not result.get('degraded'), result.get('degraded_reason')
        assert result.get('model') == os.environ['LLM_MODEL']
        assert result.get('content', '').strip(), 'Real model returned no final text'
        assert result.get('finish_reason') == 'stop'
        assert result.get('usage', {}).get('output_tokens', 0) > 0
        evidence['calls'].append({
            'kind': kind, 'model': result['model'], 'usage': result['usage'],
            'latency_ms': result.get('latency_ms'),
            'estimated_cost_usd': result.get('cost_usd'),
            'finish_reason': result['finish_reason'],
        })

    async def observed_generate(*args, **kwargs):
        assert len(evidence['calls']) < 5, 'Live acceptance call budget exceeded'
        result = await generate(*args, **kwargs)
        record(result, 'agent')
        return result

    monkeypatch.setattr(gateway, 'generate', observed_generate)
    monkeypatch.setattr(app.state, 'platform_gateway', gateway, raising=False)
    monkeypatch.setattr(registry, '_GATEWAY_LOOKUP', lambda: gateway)
    result = await gateway.generate(
        messages=[{'role': 'user', 'content': 'Synthetic document: discharge date is missing. Return only JSON: {"missing_fields":["discharge_date"]}.'}],
        response_schema={'type': 'object', 'properties': {'missing_fields': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['missing_fields']},
        context={'max_attempts': 1},
    )
    assert json.loads(result['content']) == {'missing_fields': ['discharge_date']}
    evidence['calls'][-1]['kind'] = 'structured_output'
    evidence['structured_output'] = True
    events = [event async for event in gateway.generate_stream(
        messages=[{'role': 'user', 'content': 'Synthetic connectivity test. Reply exactly ICODER_STREAM_OK.'}],
        context={'max_attempts': 1},
    )]
    terminal = [e for e in events if e.get('type') == 'completed']
    assert len(terminal) == 1 and terminal[0].get('native')
    record(terminal[0]['result'], 'native_stream')
    assert 'ICODER_STREAM_OK' in terminal[0]['result']['content']
    evidence['native_stream'] = True
    return evidence
