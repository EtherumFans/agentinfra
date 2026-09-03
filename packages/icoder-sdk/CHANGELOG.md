# Changelog

- `1.0.0-beta.50` adds tenant-scoped, secret-free operational readiness for
  governed Memory, Experts/MCP and Speech-to-Text. The readiness contracts
  disclose current production blockers instead of treating configuration as
  live verification; MCP server listing now enforces organization ownership.
- `1.0.0-beta.49` adds metadata-only dead-letter discovery, idempotent governed
  replay, persistent aggregate alert-state discovery, and dead-letter health
  counts for the database-authoritative clinical shadow queue.
- `1.0.0-beta.48` adds governed queued/running job cancellation, stale-worker
  fencing after cancellation, tenant-safe aggregate queue health and explicit
  development maintenance sweeps without emitting job or patient identifiers.
- `1.0.0-beta.47` adds development-only, idempotent clinical shadow evaluation
  jobs with fenced leases, crash recovery, bounded attempts and single audited
  rollback. Jobs remain repository-fixture-only and expose aggregate metadata.
- `1.0.0-beta.46` adds development-only aggregate clinical-model shadow
  observations, explicit pass/stop gates, controlled fault injection and audited
  automatic rollback without patient input, prediction output or Runtime routing.
- `1.0.0-beta.45` adds development-only signed synthetic clinical-model bundle
  verification, bounded content scanning, CycloneDX inventory validation,
  isolated aggregate probes, metadata-only attestations and optimistic
  shadow-only binding/rollback. The contract cannot accept patient data, emit
  predictions or enable production Runtime loading.
- `1.0.0-beta.44` adds an organization-scoped, metadata-only clinical model
  package registry across JavaScript, Python and .NET. Immutable versions,
  four-eyes decisions, optimistic activation and explicit rollback are
  exposed without accepting model binaries, training rows, patient text or
  credentials; external clinical, licence and deployment gates fail closed.
- `1.0.0-beta.43` adds a Corti-parity `.NET Standard 2.0` package asset and
  compile gates for direct `netstandard2.0` and .NET Framework 4.6.2 consumers,
  while retaining native .NET 8 and .NET 10 runtime tests. JavaScript and Python
  metadata advance in lockstep with the repository-wide public SDK release
  contract; their API surfaces are unchanged in this version.
- `1.0.0-beta.42` adds Corti-declared prerecorded audio MIME types for encoded
  multichannel decoding and preserves provider-grounded phrase timestamps.
- `1.0.0-beta.41` adds verified prerecorded stereo PCM WAV transcription.
  Channels 0 and 1 are split without native decoders, recognized separately,
  retained as encrypted structured transcript rows, and returned with exact
  participant/channel attribution across synchronous, asynchronous, restart
  recovery, list, and get paths. Diarization and encoded multichannel formats
  remain fail-closed until governed adapters are qualified.

- `1.0.0-beta.40` adds Corti-shaped file-transcript `keyterms` across
  synchronous, asynchronous, and restart-recovered jobs. Up to 1,000 ordered,
  case-sensitive written forms of at most 50 characters are forwarded to the
  governed FunASR hotword boundary (or Whisper initial prompt), retained only
  in encrypted job state, and excluded from logs and telemetry. All three SDKs
  validate and serialize the same contract before transport.

- `1.0.0-beta.39` aligns file-based transcript creation with Corti's current
  `spokenPunctuation` precedence and deprecated `isDictation` fallback. The
  verified Chinese runtime deterministically converts explicit spoken
  punctuation words only when requested, and preserves the same semantics
  across synchronous, asynchronous, and restart-recovered jobs. JavaScript,
  Python, and .NET expose both current and compatibility options before transport.

- `1.0.0-beta.38` follows the current Corti Streams contract by emitting
  `diarize` while accepting legacy `isDiarization`, and accepts up to 1,000
  ordered, case-sensitive keyterms of at most 50 characters. Keyterms are
  forwarded to the governed FunASR hotword parameter without entering logs or
  telemetry; invalid lists fail before transport in all three SDKs.

- `1.0.0-beta.37` adds governed 16 kHz signed 16-bit PCM multichannel
  Streams. Declared channels are frame-aligned, deinterleaved without native
  libraries, independently transcribed, and returned with exact participant
  channel attribution. It also adds the documented approximate `fast_init`
  Facts cadence. Diarization remains fail-closed without a qualified adapter.

- `1.0.0-beta.36` adds explicit retained Streams checkpoint recovery. A
  server-confirmed `resumed` response restores durable audio, transcript, and
  Facts counters; `resume()` fails closed when the checkpoint is missing or
  retention is disabled. Only audio covered by a received `flushed` response
  is considered safely resumable, so unconfirmed audio is never replayed.

- `1.0.0-beta.35` adds the governed Corti-recommended raw PCM profile
  (`audio/pcm`, 16 kHz, signed 16-bit little-endian mono) across the server and
  all three SDKs. PCM frame alignment, fixed decoder arguments, WAV wrapping
  for the local ASR adapter, four typed audio-health transitions, content-free
  audit records, and a real tenant WebSocket end-to-end path are covered.
  Other PCM profiles and audio events on compressed formats fail closed.

- `1.0.0-beta.34` documents bounded decoder admission and cancellation safety.
  Each API worker caps concurrent ffmpeg children and queue wait; saturation
  fails closed as `AUDIO_VALIDATION_BUSY`, cancellation kills and reaps the
  child, and content-free health counters expose capacity without paths or
  audio. A deterministic real-ffmpeg soak covers five encoded formats, five
  plausible malformed headers, and ninety mutations.

- `1.0.0-beta.33` documents the server-side isolated decoder gate for Streams.
  A bounded ffmpeg subprocess must decode one audio frame before ASR or
  retention; malformed media, decoder timeout, and missing decoder capability
  fail closed with stable, content-free error codes. E2E covers both generated
  silent Ogg/Opus and a plausible but undecodable Ogg/Opus header.

- `1.0.0-beta.32` validates the declared Streams MIME type against a bounded
  encoded-container probe and rejects WAV, raw audio, unknown parameters, and
  MIME/container mismatches before clinical processing. JavaScript, Python,
  and .NET reject unsupported declarations before transport; loopback E2E now
  sends generated silent Ogg/Opus instead of arbitrary non-audio bytes.

- `1.0.0-beta.31` adds a typed Corti-compatible Streams client, current
  CONFIG_ACCEPTED/flush/usage/end event handling, 64,000-byte chunk and 32 MiB
  session bounds, and fail-closed handling for unavailable clinical features
  and post-audio disconnects. Tenant-authenticated three-SDK WebSocket E2E
  coverage verifies isolated retention without using a real model key.

- `1.0.0-beta.30` negotiates `icoder.stt-resume.v1` for real-time STT,
  frames audio with monotonic sequence numbers, enforces the advertised
  in-memory byte bound, validates acknowledgements, and replays cached audio
  plus the end command after a bounded reconnect. Legacy servers remain
  fail-closed after audio is sent.

- `1.0.0-beta.29` synchronizes the three SDK release candidates: Python adds
  Compliance, Runtime, and Patient Context resources while .NET exposes the
  same bounded request options on every public HTTP method.

- `1.0.0-beta.28` adds authenticated tenant-bound Agent Hub readiness with
  secret-free model-selection evidence, expiring connectivity proof, and
  strict rejection of duplicate, malformed, or internally inconsistent
  readiness items. Public Hub browsing remains fail closed until this tenant
  response is fetched.

- `1.0.0-beta.27` adds the Agent Hub schema 1.3 runtime-readiness axes,
  rejects cards that enable structurally or currently unavailable Agents, and
  separates the A2A v0.3 discovery-card type from the Hub card type.

- `1.0.0-beta.26` replaces the Adapter's structural A2A facade with the
  official `@a2a-js/sdk@1.0.1` `ClientFactory`, ProtoJSON codecs, JSON-RPC
  request-ID validation and SSE parser. The Adapter now exposes the current
  Corti 0.4.0 generic UI types and official `SendMessageRequest`,
  `StreamResponse` and `TaskStatus` contracts. A live isolated test drives the
  official package through iCoDer Agent Card discovery, blocking send,
  persistent streaming and Vercel UI conversion. Same-origin authentication,
  credential minimization and safe error projection remain fail-closed.

- `1.0.0-beta.25` adds the `@icoder/sdk/ai-sdk-adapter` entry point with
  Corti-compatible `convertToParams`, `toUIMessageStream`, authenticated A2A
  client factory, and same-origin fetch implementation. A2A v1 Task typing and
  send/stream now carry `taskId` for resumable `input-required` interactions
  and expose `auth-required` and `rejected` states. Credential parts are
  bounded, first-turn-only, and never copied into message metadata.

- `1.0.0-beta.24` removes the managed Artifact credential from the URL query.
  The clean URL carries only an opaque grant locator; download now requires the
  same authenticated tenant actor that created the grant. SDK download methods
  preserve the client Bearer header and still never retry a one-time grant.

- `1.0.0-beta.23` adds Task/Artifact-owned managed object upload, quarantine
  status, malware/DLP results, one-time short-lived download authorization,
  exact byte download, and hard-delete lifecycle methods. The client never
  retries a consumed download URL.

- `1.0.0-beta.22` adds typed MCP/A2A Connector transport controls for
  same-origin redirects and response bounds. The server now wires a governed
  runtime with DNS-to-socket IP pinning, MCP Streamable HTTP sessions, A2A
  v1.0 JSON-RPC/HTTP+JSON, OAuth2 client credentials, exact regional egress,
  and default-deny PHI policy.

- `1.0.0-beta.21` adds authenticated A2A 1.0 Agent Card discovery and typed
  Connector Graph conditions plus bounded parallel execution across the
  JavaScript, Python, and .NET SDK source contracts.

- `1.0.0-beta.20` adds Corti alpha-v2-compatible `workflow`, `parallel`,
  `stateGraph`, `agentNode`, and `END` composition primitives, plus the current
  daily per-Agent usage contract. Composition is deterministic and local;
  remote Agent invocations still use authenticated Agent handles.

- `1.0.0-beta.19` adds current Corti-compatible Context trace export and
  caller-owned Task/message feedback, including opaque pagination and
  minimum-necessary Chinese medical trace projection.

- `1.0.0-beta.18` adds A2A v1 durable asynchronous Task send, polling,
  listing, cancellation, terminal waiting, and resumable SSE subscription.
  Protocol errors retain only stable reason codes and never raw clinical
  response details.
- `1.0.0-beta.17` adds the authenticated China DRG/DIP development risk-review
  surface. It fails closed on authoritative, payment-bearing or no-review
  responses and does not expose the candidate lookup as an official grouper.
  It also adds the explicitly acknowledged, fixed-payload Models connectivity
  canary; caller text is forbidden and completion text is never returned.
- `1.0.0-beta.16` adds versioned tenant model deployment selection with
  owner/admin authorization, audit attribution, exact routing and fail-closed
  behavior when a pinned deployment is unavailable.
- `1.0.0-beta.15` adds the authenticated, secret-free Models catalog for
  operator configuration and regional egress readiness. It deliberately does
  not represent configuration as live provider health.
- `1.0.0-beta.14` adds versioned multi-document Agent Run inputs,
  object-style evidence offsets, and typed cross-Agent consistency relations.

- `1.0.0-beta.13` adds typed set-level output relations and exact
  source-text evidence bindings for declared quote/span pairs.

- `1.0.0-beta.12` adds typed per-array-item output relations (`for_each`),
  membership predicates, and bounded numeric comparisons.

All notable changes to `@icoder/sdk` are documented here. The package follows
Semantic Versioning; breaking changes remain possible before `1.0.0` stable.

## [Unreleased]

- Adds a managed real-time STT lifecycle with typed events, ready handshake,
  token refresh, bounded pre-audio reconnection, and terminal fail-closed
  behavior after audio because the current server has no resumable audio
  cursor. Server error free text and credential-bearing URLs are discarded.

- Adds an owner/admin-only, time-bounded and snapshot-bound feedback training
  authorization contract across JavaScript, Python and .NET. It authorizes
  only feedback metadata for `quality_improvement`; Task/Message/model content
  and feedback reasons remain out of scope, and feedback mutation revokes the
  grant.

- `1.0.0-beta.11` exposes the bounded `field_relations` contract used to
  discover conditional and cross-field Agent output invariants.
- `1.0.0-beta.10` adds a PHI-safe, non-retryable
  `RunEventRetentionError` for expired Run trace/cursor HTTP 410 responses and
  exposes the server trace-retention window on Run lifecycle types.

- Run lifecycle SSE now emits stable persisted IDs and accepts standard
  `Last-Event-ID` resume cursors; the SDK can reconnect without replaying
  already acknowledged trace events.
- Agent Run now exposes authoritative status polling, honest cancellation
  outcomes, and signed lifecycle SSE streaming instead of claiming the backend
  stream is unimplemented.
- Medical Coding now accepts one or both China systems in `coding_systems`,
  preserves the legacy single `coding_system` input, rejects ambiguous or
  duplicate selections, and reports `coding_systems_applied`.
- Medical Coding `predict()` now supports Corti-style `filter.include`,
  `filter.exclude`, and `filter.expand`, normalizes duplicate terms, and rejects
  invalid text, modes, Chinese coding systems, or unbounded filters before
  transport.
- OAuth client-credentials exchange and OAuth client creation now send the
  form-encoded bodies required by the public FastAPI contract instead of JSON.
- Client-credentials token typing now reflects the real response, where
  refresh token and Console user fields are absent.
- Real-time STT session creation now waits for the authenticated server
  `ready` acknowledgement and fails closed on setup error, close, or timeout.
- The real-service smoke now verifies `start -> ready -> close` against the
  same temporary tenant-scoped backend used by the .NET and Python SDKs.
- Added Corti-compatible `documents` generation/preview/list/get/update/delete,
  including explicit zero-retention acknowledgement enforcement.
- Added Guided Template/Section discovery and tenant Section lifecycle methods.
- Added typed global-sequential and facts-only routed-parallel request shapes.
- Verified TypeScript declarations and `npm pack --dry-run` include the new
  Documents and Templates resource surfaces.
- Formal registry publication, signing and hosted-cloud external consumer
  verification remain gated on production infrastructure and release access.

## [1.0.0-beta.4] — 2026-08-10

### Added

- A2A v0.3 `message/send`, persistent Context history and Context deletion.
- First-turn server Context creation and validated multi-turn continuation.
- PHI-safe protocol and transport exceptions that never retain Axios
  request/response objects, bearer tokens, or server details.

### Verified

- TypeScript compilation succeeds with zero diagnostics.
- The JavaScript consumer completes send/continue/get/delete against a real
  temporary authenticated uvicorn service without loading Torch/BGE.

## [1.0.0-beta.3] — 2026-08-10

### Added

- Corti-style launch-candidate Agent Hub listing and card retrieval.
- Persistent v2 recording and transcript lifecycle, including async HTTP
  status and `Location` metadata.
- A real-service smoke consumer covering Hub discovery, Agent Run
  failure-closed behavior with trace metadata, and recording lifecycle.

### Verified

- TypeScript compilation succeeds with zero diagnostics.
- The JavaScript consumer passes against the same temporary authenticated
  uvicorn service as the Python and .NET SDK consumers.
- `npm pack --dry-run` contains only the declared README, compiled `dist`
  surface and package manifest.

### Notes

- Registry publication remains deferred; this version is not a clinical
  readiness approval.

## [1.0.0-beta.2] — 2026-07-14

### Added

- Unified `runs.runText` Agent Run entry with trace and cost metadata.
- Run history and trace timeline resource families.
- A2A envelope types reserved for future direct A2A consumption.

### Changed

- `agentRun` was renamed to `runs`, with a transitional compatibility alias.
- Monetary result shape was unified around CNY.

## [1.0.0-beta.1] — 2026-06-20

### Added

- Initial TypeScript SDK with facts, agents, experts, reviews, STT, text
  generation, billing, usage and OAuth resources.
- Axios-based bearer and refresh-token handling.
