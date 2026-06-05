"""iCoDer Official Agent Packs — pre-built, maintained Agent definitions.

These are NOT Runtime Core. They are reference Agent implementations
that run ON the Runtime, using the Runtime's infrastructure (LLMGateway,
AgentRunner, Registry, etc.).

Each official agent is a self-contained directory with:
  - schema.py: agent-specific output schema
  - agent_pack.json: .icoder-agent pack definition
  - provider/: LLM strategies specific to this agent
  - service.py: adapter that wires the agent to Runtime APIs
"""
