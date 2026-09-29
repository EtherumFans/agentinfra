"""Bounded deterministic checks over actual Agent runs; not clinical approval."""
from typing import Literal
import hashlib
import json
from pydantic import BaseModel, Field, model_validator, ConfigDict

EvaluationPurpose = Literal['treatment','payment','healthcare_operations','quality_improvement','research','public_health']

class EvaluationCase(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id: str=Field(min_length=1,max_length=80)
    text: str=Field(min_length=1,max_length=16000)
    contains: list[str]=Field(default_factory=list,max_length=20)
    excludes: list[str]=Field(default_factory=list,max_length=20)
    expected_fields: dict=Field(default_factory=dict,max_length=20)
    expected_json: dict | None=Field(default=None,max_length=20)

    @model_validator(mode='after')
    def meaningful(self):
        if not (self.contains or self.excludes or self.expected_fields or self.expected_json):
            raise ValueError('Each case needs explicit expected checks')
        if any(not value.strip() or len(value)>500 for value in self.contains+self.excludes):
            raise ValueError('Expected phrases must contain 1-500 characters')
        if len(json.dumps([self.expected_fields,self.expected_json]))>4000:
            raise ValueError('Expected fields exceed size limit')
        return self

class EvaluationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    baseline_version: str | None=Field(default=None,min_length=1,max_length=64)
    purpose_of_use: EvaluationPurpose='quality_improvement'
    candidate_version: str=Field(default='draft',min_length=1,max_length=64)
    cases: list[EvaluationCase]=Field(default_factory=list,max_length=10)
    business_suite: Literal['documentation-v1','coding-v1','quality-v1'] | None = None
    @model_validator(mode='after')
    def unique_cases(self):
        if self.business_suite:
            if self.cases:
                raise ValueError('Built-in suites cannot override fixed cases')
            from app.services.business_evaluation import suite_cases
            self.cases = [EvaluationCase(**case) for case in suite_cases(self.business_suite)]
        if not self.cases:
            raise ValueError('At least one case is required')
        if len({c.id for c in self.cases})!=len(self.cases):
            raise ValueError('Duplicate case IDs')
        if self.candidate_version==self.baseline_version:
            raise ValueError('Choose distinct versions')
        return self

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def check_result(case, response):
    payload=response.result or {}
    rendered=json.dumps(payload,ensure_ascii=False,sort_keys=True)
    checks=[]
    checks.append({'kind':'execution','passed':not response.error,'reason':'ok' if not response.error else 'execution_failed'})
    for phrase in case.contains:
        checks.append({'kind':'contains','passed':phrase in rendered})
    for phrase in case.excludes:
        checks.append({'kind':'excludes','passed':phrase not in rendered})
    missing=object()
    for path,expected in case.expected_fields.items():
        actual=payload
        for segment in path.split('.'):
            actual=actual.get(segment,missing) if isinstance(actual,dict) else missing
        checks.append({'kind':'field_equals','path':path,'passed':actual==expected})
        from app.services.coding_difference import comparison
        detail = comparison(path, expected, actual, actual is not missing)
        if detail is not None:
            checks[-1]['coding_comparison'] = detail
    if case.expected_json is not None:
        import re
        raw = str(payload.get('markdown') or '').strip()
        raw = re.sub(r'^```(?:json)?\s*\n?(.*?)\n?```$', r'\1', raw, flags=re.DOTALL)
        def unique_object(pairs):
            if len({k for k,v in pairs}) != len(pairs):
                raise ValueError('duplicate_json_key')
            return dict(pairs)
        def invalid_constant(value):
            raise ValueError('invalid_json_constant')
        try:
            parsed = json.loads(raw,object_pairs_hook=unique_object,parse_constant=invalid_constant)
            valid = isinstance(parsed,dict)
        except (ValueError,TypeError):
            parsed = {}; valid = False
        checks.append({'kind':'json_object','passed':valid,'reason':'ok' if valid else 'invalid_json'})
        for field, expected in case.expected_json.items():
            actual = parsed.get(field,missing) if valid else missing
            equal = actual is not missing and digest(actual) == digest(expected)
            checks.append({'kind':'json_field_equals','path':field,'passed':equal,
                           'reason':'ok' if equal else 'missing_field' if actual is missing else 'value_mismatch'})
            from app.services.coding_difference import comparison
            detail = comparison(field, expected, actual, actual is not missing)
            if detail is not None:
                checks[-1]['coding_comparison'] = detail
        extra = valid and bool(set(parsed)-set(case.expected_json))
        checks.append({'kind':'no_extra_fields','passed':valid and not extra,
                       'reason':'unexpected_fields' if extra else 'ok' if valid else 'invalid_json'})
    from app.services.coding_difference import annotate_roles
    annotate_roles(checks)
    return {'run_id':response.run_id,'executed_version':response.executed_agent_version,
        'runtime_mode':response.runtime_mode,'latency_ms':response.latency_ms,
        'manual_review_required':response.manual_review_required,
        'execution_ok':not response.error,'checks':checks,
        'passed':not response.error and all(c['passed'] for c in checks),
        'output_digest':digest(payload)}


async def draft_fingerprint(db, agent):
    """Bind evidence to the actual resolved configuration, not just the prompt."""
    from app.services.agent_releases import definition
    from app.services.agent_dependencies import draft_locks
    from app.services.agent_runtime_pack import pack_from_tenant_agent
    from app.models.agent import Agent
    detached = Agent(**definition(agent))
    detached.version = 'draft'
    detached.status = 'published'
    detached.is_published = True
    detached.is_prebuilt = False
    pack = await pack_from_tenant_agent(detached, agent.organization_id, db)
    from app.services.business_evaluation import model_binding
    return digest({'definition': definition(agent), 'runtime_pack': pack,
                   'model_binding': await model_binding(db, agent.organization_id),
                   'dependencies': await draft_locks(db, agent)})


def validate_release_policy(config):
    from app.services.coding_catalog_assistance import profile
    profile(config)
    from app.services.business_evaluation import SUITES
    if (config or {}).get('release_business_suite') not in (None, '', *SUITES):
        raise ValueError('Unsupported business evaluation suite')
    policy=(config or {}).get('release_evaluation_required_for', [])
    allowed={'*','treatment','payment','healthcare_operations','quality_improvement','research','public_health'}
    if not isinstance(policy,list) or len(policy)>7 or any(not isinstance(p,str) or p not in allowed for p in policy):
        raise ValueError('release_evaluation_required_for must list supported purposes or *')
    return config


async def publication_gate(db, agent, purpose='quality_improvement'):
    from sqlalchemy import select
    from app.models.agent_evaluation import AgentEvaluation
    fingerprint = await draft_fingerprint(db, agent)
    business_suite = (agent.config or {}).get('release_business_suite') or None
    query = select(AgentEvaluation).where(
        AgentEvaluation.organization_id == agent.organization_id,
        AgentEvaluation.agent_id == agent.id,
        AgentEvaluation.report['draft_digest'].as_string() == fingerprint,
        AgentEvaluation.report['candidate_version'].as_string() == 'draft',
        AgentEvaluation.report['purpose_of_use'].as_string() == purpose,
        AgentEvaluation.report['batch_context'].as_string().is_(None),
    ).order_by(AgentEvaluation.created_at.desc(), AgentEvaluation.id.desc()).limit(1)
    if business_suite:
        query = query.where(AgentEvaluation.report['business_suite'].as_string() == business_suite)
    row = (await db.execute(query)).scalar_one_or_none()
    passed = bool(row and row.report.get('consistent') and row.report.get('checks_passed'))
    review = None
    if business_suite:
        from app.services.business_evaluation import suite_cases
        passed = bool(passed and row.report.get('suite_digest') == digest([
            EvaluationCase(**case).model_dump() for case in suite_cases(business_suite)]))
        if row:
            reviews = await review_summaries(db, agent.organization_id, [row.id])
            review = reviews.get(row.id)
        passed = passed and bool(review and review['decision'] == 'approved')
    from fastapi import HTTPException
    try:validate_release_policy(agent.config)
    except ValueError:raise HTTPException(422, detail={'error':'invalid_release_evaluation_policy'})
    policy = (agent.config or {}).get('release_evaluation_required_for', [])
    required = bool(business_suite) or purpose in policy or '*' in policy
    return {'required': required, 'passed': passed, 'can_publish': not required or passed,
            'purpose_of_use': purpose, 'draft_digest': fingerprint,
            'evaluation_id': row.id if row else None,
            'business_suite':business_suite, 'review_required':bool(business_suite), 'review':review,
            'reason': 'passed' if passed else 'failed' if row else 'missing_or_stale'}


async def review_summaries(db, organization_id, evaluation_ids):
    from sqlalchemy import select, func
    from app.models.agent_evaluation_review import AgentEvaluationReview as Review
    if not evaluation_ids:
        return {}
    ranked = select(Review, func.row_number().over(partition_by=Review.evaluation_id,
        order_by=(Review.created_at.desc(),Review.id.desc())).label('position')).where(
        Review.organization_id==organization_id,Review.evaluation_id.in_(evaluation_ids)).subquery()
    rows = (await db.execute(select(ranked).where(ranked.c.position==1))).mappings().all()
    return {r['evaluation_id']:{k:(r[k].isoformat() if k=='created_at' else r[k])
            for k in ('id','decision','note','created_by','created_at')} for r in rows}
