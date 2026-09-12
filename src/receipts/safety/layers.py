"""receipts.safety.layers — [P] pure: which safety layers are on, for tests only.

D8 says read-only holds at **three independent layers** — the database
connection, the AST guard, and the adapter — and that each is tested *with the
other two disabled*. A layer that has never been the only thing standing there
has never actually been tested, so there has to be a way to switch the other two
off.

Which is obviously dangerous, so:

**The switches refuse to move outside pytest.** Not "are ignored" — refuse, with
an exception, at the moment something tries. A flag that silently stayed on in
production would be worse than no flag, because the test that proves the layer
works would still pass and nothing would be protecting anything.

**They are on by default and reset between tests.** `disabled()` is a context
manager, so a test cannot leave a layer off for the next one. The fixture that
resets them is autouse.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

LAYERS = ("guard", "connection", "adapter")


class LayerControlRefused(RuntimeError):
    """Something tried to disable a safety layer outside a test run."""


def _under_pytest() -> bool:
    return "pytest" in sys.modules


@dataclass
class _State:
    guard: bool = True
    connection: bool = True
    adapter: bool = True

    def reset(self) -> None:
        self.guard = self.connection = self.adapter = True


STATE = _State()


def enabled(layer: str) -> bool:
    if layer not in LAYERS:
        raise ValueError(f"unknown safety layer {layer!r}; known: {LAYERS}")
    return bool(getattr(STATE, layer))


@contextmanager
def disabled(*layers: str) -> Iterator[None]:
    """Turn layers off for the duration of a block. Test-only, and enforced.

    The refusal is checked when the switch is *thrown*, not when it is read. A
    check at read time would let production code enter the block, do the unsafe
    thing, and only fail on the way out.
    """
    if not _under_pytest():
        raise LayerControlRefused(
            f"refusing to disable safety layer(s) {layers}: this hook exists so D8's "
            "'each layer tested with the others off' can be written, and it is only "
            "available under pytest"
        )
    unknown = [layer for layer in layers if layer not in LAYERS]
    if unknown:
        raise ValueError(f"unknown safety layer(s) {unknown}; known: {LAYERS}")
    previous = {layer: getattr(STATE, layer) for layer in layers}
    try:
        for layer in layers:
            setattr(STATE, layer, False)
        yield
    finally:
        for layer, was in previous.items():
            setattr(STATE, layer, was)
