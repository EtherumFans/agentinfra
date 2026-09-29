"""Diagnostic comparisons only; never change evaluation scores or persist free text."""
import re
from collections import Counter

FIELDS = {'primary_diagnosis_code', 'other_diagnosis_codes', 'primary_procedure_code', 'other_procedure_codes'}

def comparison(field, expected, actual, present=True):
    if field not in FIELDS:
        return None
    def codes(value):
        if value is None:
            return []
        values = value if isinstance(value, list) else [value]
        if len(values) > 100 or any(not isinstance(v, str) or len(v) > 80 or
                (v and (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+*/×†‡ -]*', v) or re.search(r'\d{7}', v))) for v in values):
            return None
        return values
    e, a = codes(expected), codes(actual) if present else []
    if e is None or a is None:
        return {'available': False, 'reason': 'unsupported_value'}
    missing = list((Counter(e) - Counter(a)).elements())
    extra = list((Counter(a) - Counter(e)).elements())
    same = type(expected) is type(actual) and expected == actual and present
    categories = []
    if not present:
        categories.append('missing_field')
    elif not same:
        if isinstance(expected, list) != isinstance(actual, list): categories.append('type_mismatch')
        if not missing and not extra and isinstance(expected, list) and isinstance(actual, list): categories.append('order_only')
        if missing: categories.append('missing_codes')
        if extra: categories.append('extra_codes')
        if any(x and y and x != y and (x.startswith(y) or y.startswith(x)) for x in missing for y in extra):
            categories.append('possible_extension')
    return {'available': True, 'expected': e, 'actual': a, 'actual_present': present,
            'missing': missing, 'extra': extra, 'categories': categories, 'exact_match': same}

def annotate_roles(checks):
    details = {c.get('path'): c['coding_comparison'] for c in checks if c.get('coding_comparison', {}).get('available')}
    for primary, other in [('primary_diagnosis_code', 'other_diagnosis_codes'), ('primary_procedure_code', 'other_procedure_codes')]:
        for field, peer in [(primary, other), (other, primary)]:
            d, p = details.get(field), details.get(peer)
            if d and p and any(code and code in p['actual'] for code in d['missing']):
                d['categories'].append('possible_role')
