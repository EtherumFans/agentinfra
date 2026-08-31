import json

import httpx
import pytest

from icoder_sdk import iCoDerClient, iCoDerConfig


def test_medical_coding_predict_and_pricing_contract():
    captured = []

    def handler(request):
        captured.append(request)
        if request.url.path.endswith("/pricing"):
            return httpx.Response(200, json={
                "input_chars": 600,
                "runtime_mode": "corti_like_fast",
                "currency": "CNY",
                "estimated_cost_min": 0.0001,
                "estimated_cost_max": 0.0009,
                "billing_authoritative": False,
            })
        return httpx.Response(200, json={"codes": [], "summary": "ok", "error": False})

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        estimate = client.medical_coding.estimate_cost(600)
        prediction = client.medical_coding.predict(
            "去标识病历",
            coding_systems=["icd10cn", "icd9cm3"],
            include_codes=[" E11 ", "e11"],
            exclude_codes=["E11.0"],
            expand_categories=False,
        )
    finally:
        client.close()

    assert captured[0].url.path == "/api/v1/coding/pricing"
    assert dict(captured[0].url.params) == {
        "input_chars": "600",
        "mode": "corti_like_fast",
    }
    assert captured[0].headers["Authorization"] == "Bearer token"
    assert estimate["billing_authoritative"] is False
    assert captured[1].url.path == "/api/v1/coding/predict"
    body = json.loads(captured[1].content)
    assert body["text"] == "去标识病历"
    assert body["coding_systems"] == ["icd10cn", "icd9cm3"]
    assert body["filter"] == {
        "include": ["E11"],
        "exclude": ["E11.0"],
        "expand": False,
    }
    assert prediction["summary"] == "ok"


def test_medical_coding_rejects_invalid_input_before_transport():
    client = iCoDerClient(iCoDerConfig(base_url="https://api.cn.icoder.cloud"))
    try:
        with pytest.raises(ValueError, match="between 0 and 16000"):
            client.medical_coding.estimate_cost(16001)
        with pytest.raises(ValueError, match="between 1 and 16000"):
            client.medical_coding.predict("")
        with pytest.raises(ValueError, match="between 1 and 64 printable"):
            client.medical_coding.predict("去标识病历", include_codes=[""])
        with pytest.raises(ValueError, match="coding_system"):
            client.medical_coding.predict("去标识病历", coding_system="unknown")
        with pytest.raises(ValueError, match="duplicates"):
            client.medical_coding.predict(
                "去标识病历",
                coding_systems=["icd10cn", "icd10cn"],
            )
    finally:
        client.close()
