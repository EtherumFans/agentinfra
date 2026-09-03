> ## Documentation Index
> Fetch the complete documentation index at: https://docs.corti.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# System Architecture

> Learn about the Agentic Framework system architecture

The Corti Agentic Framework adopts a **multi-agent architecture** to power development of healthcare AI solutions. As compared to a monolithic LLM, the Corti Agentic Framework allows for improved specialization and protocol-based composition.

## Architecture Components

<Frame>
  <img src="https://mintcdn.com/corti/en_RPjQCFb1qJpbU/images/agents-main.svg?fit=max&auto=format&n=en_RPjQCFb1qJpbU&q=85&s=09b077584645b4c99b66b875e86e1974" alt="Diagram illustrating the Corti Agentic Framework architecture, showing the Orchestrator, Experts, and Memory components and how they interact." width="773" height="507" data-path="images/agents-main.svg" />
</Frame>

The architecture consists of three core components working together:

* **[Orchestrator](/agentic/orchestrator)** — The central coordinator that receives user requests and delegates tasks to specialized Experts via the A2A protocol.
* **[Experts](/agentic/experts)** — Specialized sub-agents that perform domain-specific work, potentially calling external services through MCP.
* **[Memory](/agentic/context-memory)** — Maintains persistent context and state, enabling the Orchestrator to make informed decisions and ensuring continuity across conversations.

Together, this architecture enables complex workflows through protocol-based composition while maintaining strict data isolation and stateless reasoning agents.

## Interaction mechanisms in Corti

The A2A Protocol supports various interaction patterns to accommodate different needs for responsiveness and persistence. Corti builds on these patterns so you can choose the right interaction model for your product:

* **Request/Response (Polling)**: Used for many synchronous Corti APIs where you send input and wait for a single response. For long‑running Corti tasks, your client can poll the task endpoint for status and results.
* **Streaming with Server-Sent Events (SSE)**: Used by Corti for real‑time experiences (for example, ambient notes or live guidance). Your client opens an SSE stream to receive incremental tokens, events, or status updates over an open HTTP connection.

<br />

<Note>Please [contact us](mailto:help@corti.ai) if you need more information about the Corti Agentic Framework.</Note>
