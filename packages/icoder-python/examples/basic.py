"""iCoDer Python SDK — Basic Usage Example"""

from icoder_sdk import iCoDerClient, iCoDerConfig
from icoder_sdk.resources.facts import FactsResource
from icoder_sdk.resources.agents import AgentsResource, ExpertsResource
from icoder_sdk.resources.reviews import ReviewsResource
from icoder_sdk.resources.billing import BillingResource, UsageResource
from icoder_sdk.resources.oauth import OAuthResource

# 1. Create client
config = iCoDerConfig(
    base_url="http://localhost:8000",
    access_token="<your-access-token>",
    refresh_token="<your-refresh-token>",
)
client = iCoDerClient(config)

# 2. Use resources
facts = FactsResource(client)
agents = AgentsResource(client)
experts = ExpertsResource(client)
reviews = ReviewsResource(client)
billing = BillingResource(client)
usage = UsageResource(client)
oauth = OAuthResource(client)

# 3. Extract facts
result = facts.extract(
    "患者因腰痛伴左下肢放射痛3月就诊。腰椎MRI示L4/5椎间盘突出。",
    output_language="zh-CN",
)
for diag in result.facts.diagnosis_facts:
    print(f"  {diag.diagnosis} ({diag.icd10cm_code})")

# 4. List agents
agent_list = agents.list()
print(f"Agents: {len(agent_list.get('agents', []))}")

# 5. Check usage
usage_data = usage.summary(30)
print(f"Credits used: {usage_data.credits_used}")

# 6. Clean up
client.close()
