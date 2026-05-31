"""iCoDer Python SDK — Medical AI Agent Platform for Chinese Hospitals."""

from .client import iCoDerClient, iCoDerConfig
from .resources.facts import FactsResource
from .resources.agents import AgentsResource, ExpertsResource
from .resources.reviews import ReviewsResource
from .resources.speech_to_text import SpeechToTextResource
from .resources.textgen import TextGenResource
from .resources.billing import BillingResource, UsageResource
from .resources.oauth import OAuthResource
from .types import (
    FactExtractionResult, FactExtractResponse,
    FactDiagnosis, FactProcedure, Review, Expert, AgentTemplate,
    TokenResponse, UsageSummary, User,
)

__version__ = "1.0.0b1"
__all__ = [
    "iCoDerClient", "iCoDerConfig",
    "FactsResource", "AgentsResource", "ExpertsResource",
    "ReviewsResource", "SpeechToTextResource", "TextGenResource",
    "BillingResource", "UsageResource", "OAuthResource",
]
