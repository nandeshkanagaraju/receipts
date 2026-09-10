"""Fault injection for every charter guard, each paired with a meta-test.

Standing rule: a guard is not done until an injection makes it fire AND a
meta-test shows the same injection passes unnoticed when the guard is off.
The meta-test is what proves the guard — not the scan — is doing the catching.

Every injection plants a real file under the real scanned tree and removes it in
a finally block.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.charter import checks

REPO = checks.REPO


@contextlib.contextmanager
def planted(rel_path: str, source: str) -> Iterator[Path]:
    """Create a file under the scanned tree, guarantee its removal."""
    p = REPO / rel_path
    assert not p.exists(), f"injection target already exists: {rel_path}"
    p.write_text(source, encoding="utf-8")
    try:
        yield p
    finally:
        p.unlink(missing_ok=True)


@contextlib.contextmanager
def appended(rel_path: str, extra: str) -> Iterator[Path]:
    """Append to an existing file, restore its exact bytes afterwards."""
    p = REPO / rel_path
    original = p.read_bytes()
    p.write_text(p.read_text(encoding="utf-8") + extra, encoding="utf-8")
    try:
        yield p
    finally:
        p.write_bytes(original)


# --------------------------------------------------------------------------- #
# D2 — clock reads
# --------------------------------------------------------------------------- #
CLOCK_SRC = "from datetime import datetime\n\n\ndef stamp():\n    return datetime.now()\n"


def test_injection_d2_clock_read_is_caught() -> None:
    with planted("src/receipts/domain/_injected_clock.py", CLOCK_SRC):
        v = checks.find_clock_reads()
        print(f"\nD2 injection: {len(v)} violation(s)")
        for x in v:
            print(f"  {x}")
        assert v, "D2 guard did not fire on datetime.now()"
        assert any("_injected_clock" in x.path for x in v)


def test_meta_d2_injection_passes_with_guard_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks, "CLOCK_SUFFIXES", ())
    with planted("src/receipts/domain/_injected_clock.py", CLOCK_SRC):
        v = checks.find_clock_reads()
        print(f"\nD2 meta (guard off): {len(v)} violation(s) — expected 0")
        assert not v, "guard-off run still flagged; the injection proves nothing"


# --------------------------------------------------------------------------- #
# D2 in llm/ — the widened scope, and the time.sleep allowance
# --------------------------------------------------------------------------- #
LLM_CLOCK_SRC = "import time\n\n\ndef stamp():\n    return time.time()\n"
LLM_SLEEP_SRC = (
    "import time\n\n\ndef backoff(attempt):\n    time.sleep(0.5 * attempt)\n    return attempt\n"
)


def test_injection_d2_clock_read_in_llm_is_caught() -> None:
    """SDD 1.1 widened D2 to cover llm/. time.time() there must now fire."""
    assert "llm" in checks.ENGINE_PACKAGES, "precondition: llm/ is in D2 scope"
    with planted("src/receipts/llm/_injected_clock.py", LLM_CLOCK_SRC):
        v = checks.find_clock_reads()
        print(f"\nD2/llm injection: {len(v)} violation(s)")
        for x in v:
            print(f"  {x}")
        assert v, "D2 guard did not fire on time.time() in llm/"
        assert any("llm/_injected_clock" in x.path for x in v)


def test_injection_d2_clock_read_in_bridge_is_caught() -> None:
    assert "bridge" in checks.ENGINE_PACKAGES, "precondition: bridge/ is in D2 scope"
    with planted("src/receipts/bridge/_injected_clock.py", LLM_CLOCK_SRC):
        v = [x for x in checks.find_clock_reads() if "bridge/_injected_clock" in x.path]
        print(f"\nD2/bridge injection: {len(v)} violation(s)")
        assert v, "D2 guard did not fire on time.time() in bridge/"


def test_time_sleep_in_llm_is_not_caught() -> None:
    """D2 allows time.sleep for retry backoff: it yields, it does not read a clock."""
    with planted("src/receipts/llm/_injected_sleep.py", LLM_SLEEP_SRC):
        v = [x for x in checks.find_clock_reads() if "_injected_sleep" in x.path]
        print(f"\nD2 sleep allowance: {len(v)} violation(s) — expected 0")
        assert not v, f"time.sleep was wrongly flagged: {[str(x) for x in v]}"


def test_meta_d2_llm_injection_passes_with_guard_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks, "CLOCK_SUFFIXES", ())
    with planted("src/receipts/llm/_injected_clock.py", LLM_CLOCK_SRC):
        v = checks.find_clock_reads()
        print(f"\nD2/llm meta (guard off): {len(v)} violation(s) — expected 0")
        assert not v, "guard-off run still flagged; the injection proves nothing"


def test_d2_scope_matches_the_sdd() -> None:
    """The package list is a claim about SDD §1 D2; check it against the document."""
    sdd = (REPO / "docs" / "SDD.md").read_text(encoding="utf-8")
    row = next(ln for ln in sdd.splitlines() if ln.startswith("| **D2**"))
    banned = re.search(r"receipts/\{([a-z,_]+)\}", row).group(1).split(",")
    print(f"\nD2 scope in SDD: {banned}")
    print(f"D2 scope in code: {list(checks.ENGINE_PACKAGES)}")
    assert sorted(banned) == sorted(checks.ENGINE_PACKAGES), "charter scope drifted from SDD §1"
    assert "`time.sleep` for retry backoff is allowed" in row, "SDD no longer allows sleep"
    for pkg in checks.WALL_CLOCK_ALLOWED:
        assert f"`{pkg}/`" in row, f"SDD does not list {pkg}/ as wall-clock-allowed"


# --------------------------------------------------------------------------- #
# D3 — non-deterministic IDs
# --------------------------------------------------------------------------- #
UUID_SRC = "import uuid\n\n\ndef new_id():\n    return str(uuid.uuid4())\n"


def test_injection_d3_uuid4_is_caught() -> None:
    with planted("src/receipts/domain/_injected_ids.py", UUID_SRC):
        v = checks.find_nondeterministic_ids()
        print(f"\nD3 injection: {len(v)} violation(s)")
        for x in v:
            print(f"  {x}")
        assert v, "D3 guard did not fire on uuid4()"
        assert any("_injected_ids" in x.path for x in v)


def test_meta_d3_injection_passes_with_guard_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks, "UUID_CALLS", set())
    with planted("src/receipts/domain/_injected_ids.py", UUID_SRC):
        v = checks.find_nondeterministic_ids()
        print(f"\nD3 meta (guard off): {len(v)} violation(s) — expected 0")
        assert not v, "guard-off run still flagged; the injection proves nothing"


# --------------------------------------------------------------------------- #
# D10 — import isolation
# --------------------------------------------------------------------------- #
CROSS_IMPORT_SRC = (
    "import receipts.domain.types\n\n\ndef leak():\n    return receipts.domain.types\n"
)


def test_injection_d10_cross_import_is_caught() -> None:
    with planted("kestrel_gen/_injected_import.py", CROSS_IMPORT_SRC):
        v = checks.find_import_isolation_breaks()
        print(f"\nD10 injection: {len(v)} violation(s)")
        for x in v:
            print(f"  {x}")
        assert v, "D10 guard did not fire on kestrel_gen importing receipts"
        assert any("_injected_import" in x.path for x in v)


def test_meta_d10_injection_passes_with_guard_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks, "ENGINE_PKG", "")
    with planted("kestrel_gen/_injected_import.py", CROSS_IMPORT_SRC):
        v = checks.find_import_isolation_breaks()
        print(f"\nD10 meta (guard off): {len(v)} violation(s) — expected 0")
        assert not v, "guard-off run still flagged; the injection proves nothing"


# --------------------------------------------------------------------------- #
# D15 — inline prompts
# --------------------------------------------------------------------------- #
LONG_PROMPT = "You are a careful analyst. " * 15  # ~405 chars, not a docstring
PROMPT_SRC = f'SYSTEM = "{LONG_PROMPT}"\n'


def test_injection_d15_inline_prompt_is_caught() -> None:
    assert len(LONG_PROMPT) > checks.INLINE_PROMPT_LIMIT, "precondition: literal exceeds the limit"
    with planted("src/receipts/agent/_injected_prompt.py", PROMPT_SRC):
        v = checks.find_inline_prompts()
        print(f"\nD15 injection: {len(v)} violation(s)")
        for x in v:
            print(f"  {x}")
        assert v, "D15 guard did not fire on a 390-char inline literal"
        assert any("_injected_prompt" in x.path for x in v)


def test_meta_d15_injection_passes_with_guard_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks, "INLINE_PROMPT_LIMIT", 10_000)
    with planted("src/receipts/agent/_injected_prompt.py", PROMPT_SRC):
        v = checks.find_inline_prompts()
        print(f"\nD15 meta (guard off): {len(v)} violation(s) — expected 0")
        assert not v, "guard-off run still flagged; the injection proves nothing"


def test_d15_does_not_flag_long_docstrings() -> None:
    """A long module docstring is documentation, not a smuggled prompt."""
    src = f'"""{LONG_PROMPT}"""\n'
    with planted("src/receipts/agent/_injected_docstring.py", src):
        v = [x for x in checks.find_inline_prompts() if "_injected_docstring" in x.path]
        print(f"\nD15 docstring control: {len(v)} violation(s) — expected 0")
        assert not v, "a docstring was misread as an inline prompt"


# --------------------------------------------------------------------------- #
# Pure modules do no I/O — injected into a real [P] module
# --------------------------------------------------------------------------- #
PURE_TARGET = "src/receipts/domain/money.py"
IO_SRC = "\nimport os\n\n\ndef leak():\n    return open(os.devnull).read()\n"


def test_injection_pure_module_io_is_caught() -> None:
    assert PURE_TARGET in checks.pure_modules(), f"precondition: {PURE_TARGET} is declared [P]"
    with appended(PURE_TARGET, IO_SRC):
        v = checks.find_io_in_pure_modules()
        print(f"\n[P] injection: {len(v)} violation(s)")
        for x in v:
            print(f"  {x}")
        assert v, "pure-module guard did not fire on import os / open()"
        assert any(PURE_TARGET in x.path for x in v)


def test_meta_pure_module_injection_passes_with_guard_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks, "BANNED_IMPORTS_IN_PURE", set())
    monkeypatch.setattr(checks, "BANNED_CALLS_IN_PURE", set())
    with appended(PURE_TARGET, IO_SRC):
        v = checks.find_io_in_pure_modules()
        print(f"\n[P] meta (guard off): {len(v)} violation(s) — expected 0")
        assert not v, "guard-off run still flagged; the injection proves nothing"


def test_pure_target_restored_after_injection() -> None:
    """The appended-file helper must leave the tree byte-identical."""
    before = (REPO / PURE_TARGET).read_bytes()
    with appended(PURE_TARGET, IO_SRC):
        pass
    assert (REPO / PURE_TARGET).read_bytes() == before, "injection did not restore the file"


# --------------------------------------------------------------------------- #
# D9 — the socket guard itself
# --------------------------------------------------------------------------- #
def test_injection_d9_network_attempt_is_caught(network_error: type[Exception]) -> None:
    import socket

    with pytest.raises(network_error):
        socket.create_connection(("example.invalid", 443), timeout=0.01)
    print("\nD9 injection: outbound connection refused by the guard")


def test_meta_d9_without_guard_the_call_is_not_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the guard off the call is attempted, so it fails differently.

    Loopback only (localhost:1), so no packet leaves the machine. The point is
    that the failure must NOT be NetworkAccessAttempted: that exception *is* the
    guard, and its absence here is what proves the injection above meaningful.
    """
    import socket

    from tests.conftest import _REAL, NetworkAccessAttempted

    monkeypatch.setattr(socket, "create_connection", _REAL["create_connection"])
    monkeypatch.setattr(socket, "getaddrinfo", _REAL["getaddrinfo"])
    monkeypatch.setattr(socket.socket, "connect", _REAL["connect"])
    monkeypatch.setattr(socket.socket, "connect_ex", _REAL["connect_ex"])
    try:
        socket.create_connection(("localhost", 1), timeout=0.05)
    except NetworkAccessAttempted:  # pragma: no cover
        pytest.fail("guard still active after being disabled")
    except OSError as exc:
        print(f"\nD9 meta (guard off): real socket error, not the guard: {type(exc).__name__}")
