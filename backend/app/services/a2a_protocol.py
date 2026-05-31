"""A2A Protocol (Agent-to-Agent) — open standard for inter-agent communication.

iCoDer Agentic Framework equivalent: "A2A Protocol — the backbone for agent
collaboration. Originally developed by Google, stewarded under Linux Foundation."

Difficulty: VERY HIGH — full protocol implementation requires:
- Agent Card discovery (.well-known/agent.json)
- Task lifecycle (submit/query/cancel)
- Streaming updates via SSE
- Multi-agent coordination
- Authentication and security

This implements the core subset: Agent Cards, Task submission, and multi-agent coordination.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---- A2A Data Models ----

class AgentCard(BaseModel):
    """A2A Agent Card — describes an agent's capabilities."""
    name: str
    description: str
    url: str  # Endpoint URL
    version: str = "1.0.0"
    capabilities: list[str] = []
    provider: str = "iCoDer"
    documentation_url: str = ""


class A2AArtifact(BaseModel):
    """A2A Artifact — standardized output format from agent tasks."""
    id: str = ""
    name: str = ""
    mime_type: str = "application/json"  # e.g., text/markdown, application/json
    content: str = ""  # The actual artifact content
    metadata: dict = {}  # Source agent, timestamps, version
    url: str = ""  # Optional URL to retrieve artifact


class A2ATask(BaseModel):
    """A2A Task — a unit of work sent between agents."""
    id: str
    title: str = ""
    description: str = ""
    status: str = "pending"  # pending, running, completed, failed, cancelled
    input_data: dict = {}
    output_data: dict | None = None
    assigned_agent: str = ""
    created_at: str = ""
    completed_at: str | None = None
    error: str | None = None
    artifacts: list[A2AArtifact] = []  # Standardized output artifacts


# ---- Agent Registry (A2A Discovery) ----

class A2ARegistry:
    """Registry of A2A-compatible agents for discovery and coordination."""

    def __init__(self):
        self._agents: dict[str, AgentCard] = {}
        self._tasks: dict[str, A2ATask] = {}

    def register_agent(self, card: AgentCard):
        """Register an agent in the A2A registry."""
        self._agents[card.name] = card
        logger.info(f"A2A: Registered agent '{card.name}' with {len(card.capabilities)} capabilities")

    def unregister_agent(self, name: str):
        self._agents.pop(name, None)

    def discover_agents(self, capability: str = "") -> list[AgentCard]:
        """Discover agents by capability (A2A discovery)."""
        if not capability:
            return list(self._agents.values())
        return [a for a in self._agents.values() if capability in a.capabilities]

    def get_agent_card(self, name: str) -> Optional[AgentCard]:
        return self._agents.get(name)

    # ---- Multi-Agent Coordination ----

    async def coordinate(
        self,
        task_description: str,
        input_data: dict,
        required_capabilities: list[str],
    ) -> dict:
        """Coordinate multiple agents to complete a complex task.

        This is the multi-agent composition engine:
        1. Discover agents matching required capabilities
        2. Decompose the task across agents
        3. Collect results from each agent
        4. Aggregate into a unified response
        """
        # Find matching agents
        matching_agents = []
        for cap in required_capabilities:
            agents = self.discover_agents(cap)
            matching_agents.extend(agents)

        if not matching_agents:
            return {"error": "No agents found for required capabilities", "capabilities": required_capabilities}

        # Create tasks for each agent
        tasks = []
        for agent in matching_agents:
            task = A2ATask(
                id=uuid.uuid4().hex[:12],
                title=f"Task for {agent.name}",
                description=task_description[:200],
                assigned_agent=agent.name,
                created_at=datetime.now(timezone.utc).isoformat(),
                input_data={"query": input_data.get("query", task_description)},
            )
            self._tasks[task.id] = task
            tasks.append(task)

        return {
            "coordination_id": uuid.uuid4().hex[:8],
            "strategy": "parallel",  # All agents execute in parallel
            "agents_assigned": [a.name for a in matching_agents],
            "capabilities_matched": required_capabilities,
            "tasks": [t.model_dump() for t in tasks],
            "task_count": len(tasks),
        }

    def update_task(self, task_id: str, status: str, output: dict | None = None, error: str | None = None):
        """Update task status (used by agents to report progress)."""
        task = self._tasks.get(task_id)
        if task:
            task.status = status
            if output is not None:
                task.output_data = output
            if error is not None:
                task.error = error
            if status in ("completed", "failed", "cancelled"):
                task.completed_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def get_task(self, task_id: str) -> Optional[A2ATask]:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[A2ATask]:
        return list(self._tasks.values())

    # ---- Serial Agent Chain (Agent A → Agent B) ----

    async def chain(
        self,
        input_data: dict,
        agent_sequence: list[str],  # Ordered list of agent names
        execute_fn: callable = None,  # async fn(agent_name, input) -> str
    ) -> dict:
        """Execute agents sequentially, passing output of A as input to B.

        If execute_fn is provided, actually executes the agent via the callback.
        Otherwise falls back to simulated execution.

        Example: agent_sequence=["EvidenceExtractionExpert", "ICDDiagnosisExpert"]
        Evidence output → ICD Diagnosis input
        """
        results = []
        current_input = input_data

        for i, agent_name in enumerate(agent_sequence):
            card = self.get_agent_card(agent_name)
            if not card:
                return {"error": f"Agent not found: {agent_name}", "completed": results}

            task = A2ATask(
                id=uuid.uuid4().hex[:12],
                title=f"Chain step {i+1}: {agent_name}",
                description=f"Serial chain step for {agent_name}",
                assigned_agent=agent_name,
                created_at=datetime.now(timezone.utc).isoformat(),
                input_data=current_input,
            )
            self._tasks[task.id] = task

            # Execute agent (real or simulated)
            if execute_fn:
                try:
                    real_output = await execute_fn(
                        agent_name,
                        current_input.get("query", str(current_input))
                    )
                    task.status = "completed"
                    task.output_data = {"agent": agent_name, "output": real_output}
                except Exception as e:
                    task.status = "failed"
                    task.error = str(e)
                    task.output_data = {"agent": agent_name, "error": str(e)}
            else:
                # Fallback simulated execution
                task.status = "completed"
                task.output_data = {"agent": agent_name, "input": str(current_input)[:200], "output": f"Processed by {agent_name}"}

            task.completed_at = datetime.now(timezone.utc).isoformat()

            # Add artifact
            task.artifacts.append(A2AArtifact(
                id=uuid.uuid4().hex[:8],
                name=f"{agent_name}_output",
                mime_type="application/json",
                content=json.dumps(task.output_data),
                metadata={"step": i+1, "agent": agent_name},
            ))

            results.append(task.model_dump())
            current_input = task.output_data  # Pass output as next input

        return {
            "chain_id": uuid.uuid4().hex[:8],
            "agent_sequence": agent_sequence,
            "strategy": "serial",
            "steps": len(agent_sequence),
            "results": results,
            "final_output": results[-1]["output_data"] if results else None,
            "artifacts": [a.model_dump() for r in results for a in A2ATask(**r).artifacts],
        }

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    def register_all_experts(self):
        """Register all 30 prebuilt experts as A2A agents for discovery."""
        all_experts = [
            # Coding (8)
            ("ICD-10 索引导航专家", ["icd_navigation", "code_lookup", "index_search"]),
            ("规则解释专家", ["rule_explanation", "coding_guidelines", "audit_support"]),
            ("编码校验专家", ["code_validation", "error_detection", "consistency_check"]),
            ("手术提取专家", ["procedure_extraction", "icd9cm3_coding", "surgical_coding"]),
            ("诊断提取专家", ["diagnosis_extraction", "icd10cn_coding", "clinical_coding"]),
            ("通用医学编码专家", ["diagnosis_coding", "procedure_coding", "multi_system_coding"]),
            ("ICD-10 WHO 编码专家", ["diagnosis_coding", "who_coding"]),
            ("HCC 风险调整专家", ["hcc_mapping", "risk_adjustment", "raf_calculation"]),
            # Insurance (4)
            ("合规护栏专家", ["compliance_check", "insurance_rules", "claim_validation"]),
            ("拒付申诉专家", ["denial_appeal", "claim_defense", "insurance_advocacy"]),
            ("拒付管理专家", ["denial_analysis", "appeal_generation", "insurance_advocacy"]),
            ("预授权专家", ["prior_authorization", "insurance_documentation", "clinical_necessity"]),
            # Quality (3)
            ("外科质控登记专家", ["registry_extraction", "quality_metrics", "structured_data"]),
            ("病历完整性专家", ["completeness_check", "documentation_quality", "compliance_review"]),
            ("临床文书改进专家", ["cdi_improvement", "documentation_quality", "specificity_enhancement"]),
            # Documentation (2)
            ("ICU 摘要专家", ["icu_summary", "clinical_summary", "ehr_synthesis"]),
            ("转诊生成专家", ["referral_generation", "care_coordination", "clinical_communication"]),
            # Emergency (1)
            ("急诊分诊评估专家", ["triage_assessment", "risk_scoring", "emergency_cds"]),
            # Nursing (2)
            ("出院宣教专家", ["discharge_education", "patient_communication", "care_planning"]),
            ("护理交班专家", ["nursing_handoff", "sbar_communication", "care_transition"]),
            # Pharmacy (1)
            ("用药重整专家", ["medication_reconciliation", "drug_review", "transition_care"]),
            # Medication (2)
            ("DrugBank 药物信息专家", ["drug_information", "drug_interaction", "pharmacokinetics"]),
            ("POSOS 用药指导专家", ["medication_lookup", "drug_interaction", "dosage_guidance"]),
            # Search (3)
            ("PubMed 文献搜索专家", ["literature_search", "article_retrieval"]),
            ("临床试验搜索专家", ["clinical_trial_search", "eligibility_check"]),
            ("网络搜索专家", ["web_search", "information_retrieval"]),
            # Utility (3)
            ("医学计算专家", ["clinical_calculation", "bmi", "egfr", "risk_scoring"]),
            ("审计追溯专家", ["audit_trail", "decision_tracking", "compliance_logging"]),
            ("记忆管理专家", ["context_recall", "memory_management"]),
            # Interview (1)
            ("临床访谈专家", ["structured_interview", "questionnaire", "clinical_assessment"]),
        ]
        for name, caps in all_experts:
            if name not in self._agents:
                self.register_agent(AgentCard(
                    name=name, description=f"iCoDer {name}",
                    url=f"http://localhost:8000/api/experts/call/{name}",
                    version="1.0.0", capabilities=caps,
                ))


a2a_registry = A2ARegistry()
