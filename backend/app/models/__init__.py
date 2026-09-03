# iCoDer - Database Models Package
from app.models.base import TimestampMixin
from app.models.user import User, UserRole
from app.models.encounter import Encounter, Document
from app.models.evidence import ClinicalEvidence
from app.models.code_candidate import CodeCandidate
from app.models.review import CodingReview, ReviewJudgment
from app.models.gold_case import GoldCase
from app.models.audit_log import AuditLog
from app.models.audit_archive import AuditIntegrityArchive
from app.models.billing import Transaction
from app.models.billing_run_settlement import BillingRunSettlement
from app.models.api_key import ApiKey
from app.models.team import TeamMember, TeamInvite, TeamRole
from app.models.expert import Expert, McpServer
from app.models.memory import ConversationMemory, MemoryConsent
from app.models.agent import Agent
from app.models.oauth import OAuthClient, OAuthToken
from app.models.runtime_persistence import RuntimeSession, RuntimeTransition, RuntimeAuditRecord, DUCDecision
from app.models.code_table import CodeTable, CodeMapping
from app.models.coding_review_run import CodingReviewRun
from app.models.customer import Customer, CustomerRegion
from app.models.organization import (
    Organization,
    OrganizationMember,
    OrganizationInvite,
    OrganizationInviteDelivery,
    OrgRole,
)
from app.models.run_trace import RunTraceEventModel
from app.models.run_history import RunHistoryModel
from app.models.template import (
    Template, TemplateVersion, TemplateCategory, TemplateLanguage, TemplateScope,
)
from app.models.ticket import Ticket, TicketStatus, TicketPriority
from app.models.cdi_case import (
    CDICaseModel,
    DocumentationGapModel,
    ProviderQueryModel,
    ClinicianResponseModel,
    DocumentVersionModel,
    CDINotificationSubscriptionModel,
)
from app.models.idempotency_record import IdempotencyRecord
from app.models.preview_session import PreviewSession
from app.models.patient_context import (
    PatientContext,
    VISIT_TYPE_VALUES,
    PURPOSE_OF_USE_VALUES,
    CONSENT_LEGAL_BASIS_VALUES,
    CONTEXT_STATUS_VALUES,
)
from app.models.stt_artifact import (
    STTInteraction,
    STTRecording,
    STTStreamCheckpoint,
    STTStreamCheckpointChunk,
    STTStreamLease,
    STTTranscript,
)
from app.models.clinical_fact import ClinicalFactRecord
from app.models.guided_document import GuidedDocumentRecord, GuidedSectionRecord
from app.models.agent_connector import (
    AgentConnector,
    ConnectorCredential,
    ConnectorExecutionAudit,
    CONNECTOR_TYPE_VALUES,
)
from app.models.agent_feedback import AgentTaskFeedback, FeedbackTrainingAuthorization
from app.models.clinical_model_package import (
    ClinicalModelActivation,
    ClinicalModelArtifactAttestation,
    ClinicalModelPackage,
    ClinicalModelShadowBinding,
    ClinicalModelShadowEvaluation,
    ClinicalModelShadowEvaluationJob,
    ClinicalModelShadowDeadLetter,
    ClinicalModelShadowAlertState,
    ClinicalModelShadowSchedulerLease,
)
# A2A Context ORM rows live with the runtime implementation, but they still
# share the application's declarative Base. Import them here so init_db() sees
# the Context and durable A2A tables on a fresh development/test deployment.
# Without this
# registration, only Alembic-created databases could execute A2A requests.
from app.icoder.agent_runtime.context.db_models import (
    ContextRow,
    ContextMessageRow,
    ContextTaskRefRow,
    ContextArtifactRefRow,
    A2ATaskArtifactRow,
    A2ATaskEventRow,
    A2ATaskExecutionRow,
    OriginalInputAuditRow,
)

__all__ = [
    "TimestampMixin",
    "User", "UserRole",
    "Encounter", "Document",
    "ClinicalEvidence",
    "CodeCandidate",
    "CodingReview", "ReviewJudgment",
    "GoldCase",
    "AuditLog", "AuditIntegrityArchive",
    "Transaction",
    "BillingRunSettlement",
    "ApiKey",
    "TeamMember", "TeamInvite", "TeamRole",
    "Expert", "McpServer",
    "ConversationMemory", "MemoryConsent",
    "Agent",
    "OAuthClient", "OAuthToken",
    "RuntimeSession", "RuntimeTransition", "RuntimeAuditRecord", "DUCDecision",
    "CodeTable", "CodeMapping",
    "CodingReviewRun",
    "Customer", "CustomerRegion",
    "Organization", "OrganizationMember", "OrganizationInvite", "OrganizationInviteDelivery", "OrgRole",
    "RunTraceEventModel",
    "RunHistoryModel",
    "Template", "TemplateVersion", "TemplateCategory", "TemplateLanguage", "TemplateScope",
    "Ticket", "TicketStatus", "TicketPriority",
    "CDICaseModel", "DocumentationGapModel", "ProviderQueryModel",
    "ClinicianResponseModel", "DocumentVersionModel",
    "CDINotificationSubscriptionModel",
    "IdempotencyRecord",
    "PreviewSession",
    "PatientContext", "VISIT_TYPE_VALUES", "PURPOSE_OF_USE_VALUES",
    "CONSENT_LEGAL_BASIS_VALUES", "CONTEXT_STATUS_VALUES",
    "STTInteraction", "STTRecording", "STTTranscript", "STTStreamLease",
    "STTStreamCheckpoint", "STTStreamCheckpointChunk",
    "ClinicalFactRecord",
    "AgentConnector", "ConnectorCredential", "ConnectorExecutionAudit",
    "CONNECTOR_TYPE_VALUES",
    "AgentTaskFeedback", "FeedbackTrainingAuthorization",
    "ClinicalModelActivation", "ClinicalModelArtifactAttestation",
    "ClinicalModelPackage", "ClinicalModelShadowBinding",
    "ClinicalModelShadowEvaluation",
    "ClinicalModelShadowEvaluationJob",
    "ClinicalModelShadowDeadLetter", "ClinicalModelShadowAlertState",
    "ClinicalModelShadowSchedulerLease",
    "ContextRow", "ContextMessageRow", "ContextTaskRefRow",
    "ContextArtifactRefRow", "OriginalInputAuditRow",
]
