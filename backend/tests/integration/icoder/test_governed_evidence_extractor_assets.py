from __future__ import annotations

import pytest

from app.services.clinical_asset_governance import (
    ClinicalAssetGovernanceError,
    assert_asset_use_allowed,
)
from official_agents.evidence_extractor.agent import ASSET_ID, verify_extractor_health


def test_real_development_asset_has_exact_catalog_and_term_index_counts() -> None:
    health = verify_extractor_health()
    assert health["integrity_verified"] is True
    assert health["catalog_count"] == 37897
    assert health["term_index_count"] == 56424
    assert health["asset"]["asset_id"] == ASSET_ID
    assert health["asset"]["authority_status"] == "source_unverified"
    assert health["asset"]["license_status"] == "external_review_required"
    assert health["asset"]["billing_authoritative"] is False
    assert health["clinical_support_assessed"] is False


def test_unverified_catalog_asset_is_rejected_in_cloud() -> None:
    with pytest.raises(ClinicalAssetGovernanceError, match="not verified for cloud"):
        assert_asset_use_allowed(
            ASSET_ID,
            deployment_mode="cloud",
            usage="exact_evidence_mention_extraction",
            verify_integrity=True,
        )
