"""scripts/make_demo_gif.py — [IO] the README's demo loop, from captured frames.

    web/.gifcap  captures the frames (Playwright, replay mode)
    python scripts/make_demo_gif.py       # frames -> docs/screens/demo.gif

Silent and looping, because it sits in a README: a reader should get the whole
argument without a play button, sound, or a reason to leave the page.
"""

from __future__ import annotations

import glob
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gifwrite  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FRAMES = REPO / ".make" / "gifframes"
OUT = REPO / "docs" / "screens" / "demo.gif"
WIDTH = 920
TARGET_SECONDS = 20.0


def main() -> int:
    files = sorted(glob.glob(str(FRAMES / "*.png")))
    if not files:
        print(f"no frames in {FRAMES}; run the capture first", file=sys.stderr)
        return 1

    start = time.time()
    frames = []
    for i, path in enumerate(files):
        w, h, rgb = gifwrite.read_png(path)
        frames.append(gifwrite.scale(w, h, rgb, WIDTH))
        if i % 25 == 0:
            print(f"  decoded {i + 1}/{len(files)}")
    w, h = frames[0][0], frames[0][1]
    print(f"decoded {len(frames)} frames at {w}x{h} in {time.time() - start:.0f}s")

    # One delay for every frame, chosen so the loop runs for about as long as
    # the README promises rather than as long as the capture happened to take.
    per_frame = max(2, round(TARGET_SECONDS * 100 / len(frames)))
    delays = [per_frame] * len(frames)

    start = time.time()
    size = gifwrite.write_gif(frames, OUT, delays)
    print(
        f"wrote {OUT.relative_to(REPO)}: {size / 1024 / 1024:.2f} MB, "
        f"{len(frames) * per_frame / 100:.1f}s loop, in {time.time() - start:.0f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
