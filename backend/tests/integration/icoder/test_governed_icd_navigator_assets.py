from __future__ import annotations

import pytest

from app.services.clinical_asset_governance import (
    ClinicalAssetGovernanceError,
    assert_asset_use_allowed,
)
from official_agents.icd10_navigator.agent import ASSET_ID, verify_navigator_health


def test_real_development_asset_has_exact_catalog_and_term_index_counts() -> None:
    health = verify_navigator_health()

    assert health["integrity_verified"] is True
    assert health["catalog_count"] == 37897
    assert health["term_index_count"] == 56424
    assert health["asset"]["asset_id"] == ASSET_ID
    assert health["asset"]["authority_status"] == "source_unverified"
    assert health["asset"]["license_status"] == "external_review_required"
    assert health["asset"]["billing_authoritative"] is False


def test_unverified_index_asset_is_rejected_in_cloud() -> None:
    with pytest.raises(ClinicalAssetGovernanceError, match="not verified for cloud"):
        assert_asset_use_allowed(
            ASSET_ID,
            deployment_mode="cloud",
            usage="catalog_navigation",
            verify_integrity=True,
        )
