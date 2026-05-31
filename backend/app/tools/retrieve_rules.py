# iCoDer - retrieve_rules Tool (PRD Section 11.3)
from app.services.rule_engine import rule_engine_service

async def retrieve_rules_tool(topic: str, rule_sets: list[str] | None = None) -> dict:
    """Retrieve coding rules relevant to a topic."""
    results = await rule_engine_service.retrieve_rules(topic, rule_sets, top_k=5)
    return {"results": results}
