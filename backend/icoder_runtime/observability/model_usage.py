"""Request-local gateway usage accounting. Never captures prompts or outputs."""
from contextvars import ContextVar
from functools import wraps
import math
import re
import inspect

_usage = ContextVar('model_usage', default=None)


def collect_model_usage(fn):
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        token = _usage.set([])
        try:
            return await fn(*args, **kwargs)
        finally:
            _usage.reset(token)
    wrapped.__signature__ = inspect.signature(fn, eval_str=True)
    return wrapped


def _count(value):
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100_000_000:
        return value
    return None


def record_model_usage(provider, result):
    records = _usage.get()
    if records is None:
        return
    result = result if isinstance(result, dict) else {}
    # Mock responses have no actual provider usage; never count fabricated tokens.
    if provider == 'mock':
        return
    usage = result.get('usage') if isinstance(result.get('usage'), dict) else {}
    def identifier(value):
        return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9._:/-]{1,128}', value) else 'unknown'
    amount = result.get('cost_usd')
    amount = float(amount) if isinstance(amount, (int, float)) and not isinstance(amount, bool) else None
    if amount is not None and (not math.isfinite(amount) or not 0 <= amount <= 100000):
        amount = None
    input_tokens = _count(usage.get('input_tokens'))
    output_tokens = _count(usage.get('output_tokens'))
    # A fallback's synthetic zero cost cannot establish free external execution.
    if result.get('degraded') or result.get('is_mock'):
        input_tokens = output_tokens = None
        amount = None
    elif input_tokens is None and output_tokens is None:
        amount = None
    records.append({'provider': identifier(provider), 'model': identifier(result.get('model')),
                    'input_tokens': input_tokens, 'output_tokens': output_tokens,
                    'estimated_cost_usd': amount})


def model_usage_snapshot():
    records = _usage.get()
    if not records:
        return None
    def sum_known(items, field):
        values = [item[field] for item in items if item[field] is not None]
        return sum(values) if values else None
    grouped = {}
    for item in records:
        grouped.setdefault((item['provider'], item['model']), []).append(item)
    def summarize(items):
        return {'calls': len(items), 'input_tokens': sum_known(items, 'input_tokens'),
                'output_tokens': sum_known(items, 'output_tokens'),
                'estimated_cost_usd': sum_known(items, 'estimated_cost_usd'),
                'usage_complete': all(i['input_tokens'] is not None and i['output_tokens'] is not None for i in items),
                'cost_complete': all(i['estimated_cost_usd'] is not None for i in items)}
    return {**summarize(records), 'models': [dict(provider=p, model=m, **summarize(items))
             for (p,m), items in sorted(grouped.items())]}
