# Corti JavaScript SDK — Install + First Request

Source: Corti Console > Developer Quickstart
URL: https://console.corti.app/project/b8f8129a-c31d-407f-b723-6ecc592d31e4/developer-quickstart
Use case selected: Build a medical coding app
SDK tab: JavaScript SDK

## Install

```bash
npm install @corti/sdk dotenv
```

## Sample code (creates an Interaction)

```javascript
import { CortiClient } from "@corti/sdk";
import "dotenv/config";

const client = new CortiClient({
    environment: process.env.CORTI_ENVIRONMENT,
    auth: {
        clientId: process.env.CORTI_CLIENT_ID,
        clientSecret: process.env.CORTI_CLIENT_SECRET
    },
    tenantName: process.env.CORTI_TENANT_NAME
});

const { interactionId } = await client.interactions.create({
    encounter: {
        identifier: crypto.randomUUID(), // Replace with your own identifier
        status: "planned",
        type: "first_consultation"
    }
});
```

## Env vars required

```
CORTI_ENVIRONMENT=<eu|us>
CORTI_CLIENT_ID=<from API Clients page>
CORTI_CLIENT_SECRET=<from API Clients page — masked in UI as tFV5••••••••••••••••>
CORTI_TENANT_NAME=<from API Clients page>
```

## Observations

- `CortiClient` constructor takes `environment` + `auth.clientId` + `auth.clientSecret` + `tenantName`
- Auth flow = OAuth2 Client Credentials (per API Clients page; "Authentication method: Client credentials")
- `client.interactions.create()` creates an "Interaction" with an "Encounter" (status: planned, type: first_consultation)
- No streaming in this sample (one-shot REST round-trip)
- No explicit Run ID / Trace ID surfaced in the JS code (returned object is `{interactionId}` — implies IDs are managed server-side)

## Missing from JS sample

- `client.agents.create(...)` and `client.agents.messageSend(...)` are NOT in the Quickstart — they are visible only via the per-Agent Code tab (per §7 audit). The Quickstart focuses on `interactions.create()` which is the first-party Encounter creation, not the Agent SDK.
- No `cortiClient.agents.messageSend(agentId, {message: {...}})` sample in the Quickstart.
- The Agent SDK surface (per §7 audit) is at `cortiClient.agents.create({name, experts, description, systemPrompt})` + `cortiClient.agents.messageSend(agentId, {message: {role, parts, messageId, kind}})`.
