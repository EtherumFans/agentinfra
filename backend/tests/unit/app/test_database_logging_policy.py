from __future__ import annotations

import logging

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import database
from app.config import Settings


def test_database_sql_echo_is_opt_in_and_parameters_are_always_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ICODER_DATABASE_SQL_ECHO", raising=False)
    local = Settings(_env_file=None)

    assert local.ICODER_DATABASE_SQL_ECHO is False
    assert database._engine_kwargs["echo"] is False
    assert database._engine_kwargs["hide_parameters"] is True


def test_local_statement_echo_requires_an_explicit_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ICODER_DATABASE_SQL_ECHO", "true")
    local = Settings(_env_file=None)

    assert local.ICODER_DATABASE_SQL_ECHO is True


@pytest.mark.asyncio
async def test_sqlalchemy_diagnostic_echo_never_logs_bound_clinical_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "PHI_SENTINEL_PATIENT_NOTE_13800138000"
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=True,
        hide_parameters=database._engine_kwargs["hide_parameters"],
    )
    try:
        with caplog.at_level(logging.INFO, logger="sqlalchemy.engine.Engine"):
            async with engine.connect() as connection:
                value = await connection.scalar(
                    text("SELECT :clinical_note"),
                    {"clinical_note": sentinel},
                )
        assert value == sentinel
        assert sentinel not in caplog.text
        assert "SQL parameters hidden due to hide_parameters=True" in caplog.text
    finally:
        await engine.dispose()
