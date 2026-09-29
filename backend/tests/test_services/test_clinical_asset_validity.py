from datetime import date
import pytest
from app.services import clinical_asset_governance as gate

@pytest.fixture
def asset(monkeypatch):
    item = {'asset_id':'test', 'version':'1', 'authority_status':'authoritative_verified',
            'license_status':'verified', 'effective_from':'2026-01-01', 'effective_to':'2026-12-31',
            'jurisdiction':'CN-TEST', 'billing_authoritative':True}
    monkeypatch.setattr(gate, 'select_asset', lambda *a, **k: item)
    return item

@pytest.mark.parametrize('today', [date(2025,12,31), date(2027,1,1)])
@pytest.mark.parametrize('usage', ['settlement', 'risk_review'])
def test_outside_validity_rejected(asset, today, usage):
    with pytest.raises(gate.ClinicalAssetGovernanceError):
        gate.assert_asset_use_allowed('test', deployment_mode='local', usage=usage, verify_integrity=False, jurisdiction='CN-TEST', as_of=today)

@pytest.mark.parametrize('jurisdiction', [None, 'CN-OTHER'])
def test_missing_or_wrong_jurisdiction_rejected(asset, jurisdiction):
    with pytest.raises(gate.ClinicalAssetGovernanceError, match='jurisdiction'):
        gate.assert_asset_use_allowed('test', deployment_mode='cloud', usage='risk_review', verify_integrity=False, jurisdiction=jurisdiction, as_of=date(2026,6,1))

def test_effective_boundary_and_exact_jurisdiction_allowed(asset):
    assert gate.assert_asset_use_allowed('test', deployment_mode='cloud', usage='settlement', verify_integrity=False, jurisdiction='CN-TEST', as_of=date(2026,12,31)) == asset

def test_invalid_date_fails_closed(asset):
    asset['effective_from'] = 'invalid'
    with pytest.raises(gate.ClinicalAssetGovernanceError):
        gate.assert_asset_use_allowed('test', deployment_mode='cloud', usage='risk_review', verify_integrity=False, jurisdiction='CN-TEST')
