# Python SDK
pip install icoder-sdk

from icoder_sdk import iCoDerClient, iCoDerConfig
client = iCoDerClient(iCoDerConfig(base_url='http://localhost:8000', client_id='...', client_secret='...'))

# Facts, Agents, Runtime, Marketplace
result = client.facts.extract('病历文本...')
agents = client.runtime.list_agents('certified')
packages = client.marketplace.list(category='编码')
