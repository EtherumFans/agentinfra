-- Phase 1 Context tables (SPEC §4.3)
-- Source of truth: backend/alembic/versions/005_context_tables.py
-- This file is documentation; migrate via `alembic upgrade head`.

CREATE TABLE contexts (
    id TEXT PRIMARY KEY,                          -- contextId (UUID v4)
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,                -- created_at + TTL
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,                         -- active / completed / failed / expired
    metadata_json TEXT NOT NULL,                  -- ContextMetadata JSON
    redacted_input_hash TEXT NOT NULL DEFAULT '',
    original_input_ref TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_contexts_expires_at ON contexts (expires_at);
CREATE INDEX idx_contexts_agent_id ON contexts (agent_id);
CREATE INDEX idx_contexts_status ON contexts (status);

CREATE TABLE context_messages (
    context_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    role TEXT NOT NULL,
    parts_json TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    redacted BOOLEAN NOT NULL DEFAULT 1,           -- G5: hard invariant
    metadata_json TEXT NOT NULL DEFAULT '{}',

    PRIMARY KEY (context_id, message_id),
    FOREIGN KEY (context_id) REFERENCES contexts(id) ON DELETE CASCADE
);

CREATE TABLE context_task_refs (
    context_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    state TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,

    PRIMARY KEY (context_id, task_id),
    FOREIGN KEY (context_id) REFERENCES contexts(id) ON DELETE CASCADE
);

CREATE TABLE context_artifact_refs (
    context_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    url TEXT NOT NULL,

    PRIMARY KEY (context_id, artifact_id),
    FOREIGN KEY (context_id) REFERENCES contexts(id) ON DELETE CASCADE
);

-- 原文审计 (独立于 Context 生命周期, 独立 retention)
CREATE TABLE original_input_audit (
    id TEXT PRIMARY KEY,
    context_id TEXT NOT NULL,
    original_input TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    retention_until TIMESTAMP NOT NULL
);

CREATE INDEX idx_original_input_audit_context_id ON original_input_audit (context_id);
CREATE INDEX idx_original_input_audit_retention ON original_input_audit (retention_until);