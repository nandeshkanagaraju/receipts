"""SDD §26 — config is strict: unknown keys, wrong types and gaps all raise."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from receipts.config import CONFIG_DIR, load_settings


def _settings_dict() -> dict:
    return yaml.safe_load((CONFIG_DIR / "settings.yaml").read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "settings.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return p


def test_real_settings_load() -> None:
    s = load_settings()
    print(f"\nsettings load OK: as_of={s.as_of}, row_limit={s.row_limit}, llm.mode={s.llm.mode}")
    assert s.llm.temperature == 0, "SDD §16: temperature 0 everywhere"


def test_unknown_key_raises(tmp_path: Path) -> None:
    data = _settings_dict()
    data["not_a_real_setting"] = True
    with pytest.raises(ValidationError) as exc:
        load_settings(_write(tmp_path, data))
    print(f"\nunknown key rejected: {exc.value.errors()[0]['type']}")
    assert "extra_forbidden" in str(exc.value)


def test_unknown_nested_key_raises(tmp_path: Path) -> None:
    data = _settings_dict()
    data["llm"]["temperature_c"] = 3
    with pytest.raises(ValidationError):
        load_settings(_write(tmp_path, data))


def test_wrong_type_raises(tmp_path: Path) -> None:
    data = _settings_dict()
    data["row_limit"] = "five hundred"  # string where an int is expected
    with pytest.raises(ValidationError) as exc:
        load_settings(_write(tmp_path, data))
    print(f"wrong type rejected: {exc.value.errors()[0]['type']}")


def test_no_silent_coercion_of_numeric_string(tmp_path: Path) -> None:
    """strict=True: '500' is a string, not an int. Coercion would hide typos."""
    data = _settings_dict()
    data["row_limit"] = "500"
    with pytest.raises(ValidationError):
        load_settings(_write(tmp_path, data))


def test_missing_required_key_raises(tmp_path: Path) -> None:
    data = _settings_dict()
    del data["as_of"]
    with pytest.raises(ValidationError) as exc:
        load_settings(_write(tmp_path, data))
    print(f"missing key rejected: {exc.value.errors()[0]['type']}")
    assert "missing" in str(exc.value)


def test_missing_file_fails_rather_than_defaults(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "nope.yaml")
