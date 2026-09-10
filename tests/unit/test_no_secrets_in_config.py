"""SDD §26 — secrets come only from the environment; config files hold none.

Config may *name* an environment variable (`dsn_env: RECEIPTS_POSTGRES_DSN`);
it may never hold the value.
"""

from __future__ import annotations

import re
from pathlib import Path

from receipts.config import CONFIG_DIR

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai-style key", re.compile(r"sk-[A-Za-z0-9_\-]{16,}")),
    ("anthropic-style key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}")),
    ("github token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws access key id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("long hex secret", re.compile(r"\b[0-9a-fA-F]{40,}\b")),
    ("bearer literal", re.compile(r"[Bb]earer\s+[A-Za-z0-9._\-]{20,}")),
    ("inline password", re.compile(r"(?i)\b(password|passwd|secret|api_key|token)\s*:\s*\S+")),
)

ENV_REFERENCE = re.compile(r"(?i)\b\w*_env\s*:\s*[A-Z0-9_]+\s*$")


def scan(path: Path) -> list[str]:
    """Sorted findings for one file; empty means clean."""
    findings: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or ENV_REFERENCE.search(stripped):
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(f"{path.name}:{lineno} {label}: {stripped[:60]}")
    return sorted(findings)


def config_files(config_dir: Path = CONFIG_DIR) -> list[Path]:
    """Every file under config/, at any depth and whatever its extension.

    Not `glob("*.yaml")`: the rule is "no secrets in config", not "no secrets in
    files ending .yaml". A `.yml`, a `.env`, or anything under `config/env/`
    would have been scanned by nobody, and would have passed silently.
    """
    return sorted(p for p in config_dir.rglob("*") if p.is_file())


def test_no_secrets_in_config() -> None:
    files = config_files()
    assert files, "precondition: no config files found to scan"
    findings = [f for p in files for f in scan(p)]
    print(
        f"\nscanned {len(files)} config files for {len(SECRET_PATTERNS)} secret shapes: "
        f"{', '.join(p.name for p in files)}"
    )
    assert not findings, "secret-like strings in config:\n" + "\n".join(findings)


def test_the_scan_covers_the_directory_not_one_extension(tmp_path: Path) -> None:
    """INJECTION: a secret in a config file the old `*.yaml` glob would not see.

    Two shapes at once — an extension nobody listed, and a subdirectory.
    """
    (tmp_path / "settings.yaml").write_text("some_key: fine\n", encoding="utf-8")
    (tmp_path / "extra.yml").write_text("api_key: sk-abcdefghijklmnopqrstuvwxyz012345\n", "utf-8")
    (tmp_path / "env").mkdir()
    (tmp_path / "env" / "prod.conf").write_text("key: AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8")

    seen = config_files(tmp_path)
    findings = [f for p in seen for f in scan(p)]
    print(f"\nscanned {len(seen)} file(s): {[p.name for p in seen]}")
    for f in findings:
        print(f"  {f}")
    assert len(seen) == 3, f"the scan missed a file: {[str(p) for p in seen]}"
    # Assert which files were caught, not how many findings: one planted line
    # legitimately matches two patterns (openai-style key and inline password),
    # so a count is brittle in a way the property is not.
    caught = {f.split(":")[0] for f in findings}
    assert caught == {"extra.yml", "prod.conf"}, f"planted files caught: {sorted(caught)}"

    # META: the old, extension-scoped discovery misses both.
    old_style = sorted(tmp_path.glob("*.yaml"))
    print(
        f'meta (old `glob("*.yaml")`): {[p.name for p in old_style]} '
        f"-> {len([f for p in old_style for f in scan(p)])} finding(s)"
    )
    assert not [f for p in old_style for f in scan(p)], "the old glob would have caught it"


def test_env_references_are_not_flagged() -> None:
    """Naming an env var is fine; only values are secrets."""
    assert not scan(CONFIG_DIR / "settings.yaml")
    assert "dsn_env" in (CONFIG_DIR / "settings.yaml").read_text(encoding="utf-8")


def test_planted_secret_is_detected(tmp_path: Path) -> None:
    """INJECTION: each secret shape must be caught."""
    cases = {
        "openai": "api_key: sk-abcdefghijklmnopqrstuvwxyz012345",
        "hex": "digest: " + "a" * 40,
        "aws": "key: AKIAIOSFODNN7EXAMPLE",
        "bearer": "auth: Bearer abcdefghijklmnopqrstuvwxyz",
        "inline": "password: hunter2hunter2hunter2",
    }
    for name, line in cases.items():
        p = tmp_path / f"{name}.yaml"
        p.write_text(f"some_key: fine\n{line}\n", encoding="utf-8")
        findings = scan(p)
        print(f"  injection {name}: {len(findings)} finding(s)")
        assert findings, f"secret shape {name!r} was NOT detected"
