# JavaScript SDK
npm install @icoder/sdk

import iCoDer from '@icoder/sdk';
const client = new iCoDer({ baseURL: 'http://localhost:8000', clientId: '...', clientSecret: '...' });

// Facts
const result = await client.facts.extract({ text: '病历文本...' });
// Runtime
const agents = await client.runtime.listAgents('certified');
const run = await client.runtime.runAgent('agent-ref', '病历文本');
// Marketplace
const packages = await client.marketplace.list('', '编码');
