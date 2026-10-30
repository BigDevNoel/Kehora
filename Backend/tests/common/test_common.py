import json
import logging
from datetime import timedelta

import pytest
import structlog

from kehora_common.clock import utcnow
from kehora_common.flags import Flag, is_enabled
from kehora_common.ids import new_id
from kehora_common.logging import configure_logging, get_logger
from kehora_common.settings import Settings, require


def test_new_id_is_uuid_v7_and_time_ordered() -> None:
    ids = [new_id() for _ in range(50)]
    assert all(i.version == 7 for i in ids)
    assert ids == sorted(ids)


def test_utcnow_is_timezone_aware_utc() -> None:
    now = utcnow()
    assert now.utcoffset() == timedelta(0)


def test_flag_defaults_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FEATURE_CREDITS_ENFORCED", raising=False)
    assert is_enabled(Flag.CREDITS_ENFORCED) is False
    monkeypatch.setenv("FEATURE_CREDITS_ENFORCED", "true")
    assert is_enabled(Flag.CREDITS_ENFORCED) is True


def test_require_names_missing_env_var() -> None:
    with pytest.raises(RuntimeError, match="CLERK_ISSUER"):
        require(None, "CLERK_ISSUER")
    assert require("x", "ANY") == "x"


def test_settings_read_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", '["http://localhost:5173"]')
    s = Settings(_env_file=None)
    assert s.env == "test"
    assert s.clerk_authorized_parties == ["http://localhost:5173"]


def test_json_logging_includes_bound_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")
    structlog.contextvars.bind_contextvars(run_id="r-1")
    try:
        get_logger("test").info("hello", step=2)
    finally:
        structlog.contextvars.clear_contextvars()
    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["event"] == "hello"
    assert record["run_id"] == "r-1"
    assert record["step"] == 2
    assert record["level"] == "info"
    logging.getLogger().handlers.clear()
