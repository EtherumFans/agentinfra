from __future__ import annotations

import hashlib

import pytest

from app.services.dedicated_project_policy import (
    DedicatedProjectPolicy,
    ProjectPolicyLLM,
    apply_project_policy,
    policy_from_runtime_pack,
)


def _pack(instructions: str, *, digest: str | None = None) -> dict:
    return {
        "project_runtime": {
            "dedicated_project_policy": instructions,
            "dedicated_project_policy_digest": (
                hashlib.sha256(instructions.encode("utf-8")).hexdigest()
                if digest is None
                else digest
            ),
            "project_expert_ids": ["expert-project-1"],
            "project_prompt_overridden": True,
            "dedicated_source_experts_fixed": True,
        }
    }


def test_policy_from_runtime_pack_verifies_digest_and_exposes_only_safe_metadata() -> None:
    sentinel = "PROJECT_POLICY_SECRET_SENTINEL"
    policy = policy_from_runtime_pack(_pack(sentinel))

    assert policy.instructions == sentinel
    assert policy.enabled is True
    assert policy.prompt_overridden is True
    assert policy.project_expert_ids == ("expert-project-1",)
    assert policy.digest == hashlib.sha256(sentinel.encode("utf-8")).hexdigest()
    assert sentinel not in str(policy.safe_metadata())


@pytest.mark.parametrize("digest", ["", "tampered"])
def test_policy_from_runtime_pack_rejects_missing_or_tampered_digest(
    digest: str,
) -> None:
    with pytest.raises(ValueError, match="digest|integrity"):
        policy_from_runtime_pack(_pack("project policy", digest=digest))


def test_apply_project_policy_is_additive_and_restates_immutable_boundary() -> None:
    source = "SOURCE_SAFETY_RULE: preserve evidence and schema."
    project = "PROJECT_SPECIALIZATION: prefer explicit principal diagnosis."

    effective = apply_project_policy(source, project, runtime_name="cdi")

    assert effective.startswith(source)
    assert effective.index(source) < effective.index(project)
    assert "IMMUTABLE_CDI_BOUNDARY" in effective
    assert effective.index(project) < effective.index("IMMUTABLE_CDI_BOUNDARY")
    assert "human review" in effective
    assert "production write-back" in effective
    assert apply_project_policy(source, "", runtime_name="cdi") == source


@pytest.mark.asyncio
async def test_project_policy_llm_governs_keyword_and_positional_system_prompts() -> None:
    class Delegate:
        def __init__(self) -> None:
            self.calls: list[tuple[tuple, dict]] = []

        async def chat(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"content": "safe result"}

    sentinel = "CDI_PROJECT_POLICY_SECRET_SENTINEL"
    policy = DedicatedProjectPolicy(
        instructions=sentinel,
        digest=hashlib.sha256(sentinel.encode("utf-8")).hexdigest(),
    )
    delegate = Delegate()
    proxy = ProjectPolicyLLM(delegate, policy)

    keyword_result = await proxy.chat(
        messages=[{"role": "user", "content": "synthetic chart"}],
        system_prompt="SOURCE CDI PROMPT",
    )
    positional_result = await proxy.chat(
        [{"role": "user", "content": "synthetic chart"}],
        "SOURCE CDI PROMPT",
    )

    assert keyword_result == {"content": "safe result"}
    assert positional_result == {"content": "safe result"}
    keyword_prompt = delegate.calls[0][1]["system_prompt"]
    positional_prompt = delegate.calls[1][0][1]
    for prompt in (keyword_prompt, positional_prompt):
        assert prompt.startswith("SOURCE CDI PROMPT")
        assert sentinel in prompt
        assert "IMMUTABLE_CDI_BOUNDARY" in prompt
    assert sentinel not in str(keyword_result)
