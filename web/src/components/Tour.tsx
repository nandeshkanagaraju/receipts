import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Copy } from "../i18n";

/** A first-visit guided tour. This is what a demo video would have been.
 *
 *  **Spotlight by four dim panels, not an SVG mask and not a raised element.**
 *  Raising the target with z-index means changing its position or stacking, and
 *  a tour that relaid out the page to point at it would be pointing at
 *  something the visitor never had. Four rectangles around the target leave it
 *  untouched and lit; an outline ring is drawn beside it, not on it.
 *
 *  **No animation anywhere.** `prefers-reduced-motion` asks for no animated
 *  transitions; the simplest way to honour that is to have none to suppress.
 *  The spotlight moves instantly, which also makes it testable.
 */
export const TOUR_SEEN_KEY = "receipts.tour.v1";

/** Each step names its anchor by test id. A list, tried in order, because the
 *  step trace is a live element when a question has run and an idle placeholder
 *  before one has — the tour must point at whichever is on screen rather than
 *  at nothing. */
const ANCHORS: readonly (readonly string[])[] = [
  ["narration", "answer-canvas"],
  ["receipt-card", "no-receipt"],
  ["status-badge"],
  ["step-trace", "step-trace-idle"],
  ["catalog-panel"],
  ["role-switcher"],
  ["language-toggle"],
];

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

function find(step: number): HTMLElement | null {
  for (const id of ANCHORS[step] ?? []) {
    const found = document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
    if (found) return found;
  }
  return null;
}

export function hasSeenTour(): boolean {
  try {
    return window.localStorage.getItem(TOUR_SEEN_KEY) === "1";
  } catch {
    // Private browsing, or storage disabled. A tour that cannot remember is
    // better than a page that will not load.
    return true;
  }
}

export function markTourSeen(): void {
  try {
    window.localStorage.setItem(TOUR_SEEN_KEY, "1");
  } catch {
    /* nothing to do; the tour simply runs again next time */
  }
}

export function Tour({ copy, onClose }: { copy: Copy; onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const caption = useRef<HTMLDivElement>(null);
  const total = copy.tour.length;
  const last = step === total - 1;

  const finish = useCallback(() => {
    markTourSeen();
    onClose();
  }, [onClose]);

  const next = useCallback(() => {
    if (last) finish();
    else setStep((current) => current + 1);
  }, [last, finish]);

  // Measure after the DOM is laid out, and after scrolling the anchor into
  // view: the catalog sits well below the fold at 375px, and a spotlight on an
  // off-screen element is a dimmed page with nothing lit.
  useLayoutEffect(() => {
    const target = find(step);
    if (!target) {
      setRect(null);
      return;
    }
    // Only scroll when the target is not already fully on screen. Scrolling
    // unconditionally moved the page on every step, including steps whose
    // target is the header and already visible.
    const first = target.getBoundingClientRect();
    if (first.top < 0 || first.bottom > window.innerHeight) {
      target.scrollIntoView({ block: "center", behavior: "auto" });
    }

    // Bail out when nothing moved. Without this, the scroll listener set state
    // with an identical rect, React re-rendered, and the caption never held
    // still -- which reads to a person as a flicker and to Playwright as an
    // element that is never stable enough to click.
    const measure = () => {
      const box = target.getBoundingClientRect();
      setRect((current) =>
        current &&
        current.top === box.top &&
        current.left === box.left &&
        current.width === box.width &&
        current.height === box.height
          ? current
          : { top: box.top, left: box.left, width: box.width, height: box.height },
      );
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [step]);

  // Focus follows the highlighted step, so a keyboard or screen-reader user is
  // moved along with the spotlight rather than left behind it.
  useEffect(() => {
    caption.current?.focus();
  }, [step]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        finish();
      } else if (event.key === "Enter" || event.key === "ArrowRight") {
        event.preventDefault();
        next();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [next, finish]);

  const entry = copy.tour[step];
  if (!entry) return null;

  const pad = 6;
  const dim = "fixed bg-ink/60";
  const box = rect
    ? {
        top: Math.max(0, rect.top - pad),
        left: Math.max(0, rect.left - pad),
        width: rect.width + pad * 2,
        height: rect.height + pad * 2,
      }
    : null;

  // Where the caption goes. It must never cover the thing it is describing --
  // the receipt is nearly full-height, so "below, or above if there is no room"
  // put the caption on top of the metric name and definition the caption was
  // pointing at. Beside is the third option and for tall targets it is the only
  // one.
  const captionWidth = Math.min(352, window.innerWidth - 32);
  const CAPTION_H = 210;
  const GAP = 12;

  function place(): { top: number; left: number } {
    if (!box) return { top: Math.max(16, window.innerHeight / 2 - CAPTION_H / 2), left: 16 };
    const clampLeft = (value: number) =>
      Math.min(Math.max(16, value), Math.max(16, window.innerWidth - captionWidth - 16));
    const clampTop = (value: number) =>
      Math.min(Math.max(16, value), Math.max(16, window.innerHeight - CAPTION_H - 16));

    if (window.innerHeight - (box.top + box.height + GAP) >= CAPTION_H) {
      return { top: box.top + box.height + GAP, left: clampLeft(box.left) };
    }
    if (box.top - GAP >= CAPTION_H) {
      return { top: box.top - GAP - CAPTION_H, left: clampLeft(box.left) };
    }
    // Beside: to the left when the target is in the right half, else to the
    // right. At 375px neither side fits, so it falls back to overlaying at the
    // bottom -- which is the least bad of three bad options on a phone.
    const leftSide = box.left - GAP - captionWidth;
    if (leftSide >= 16) return { top: clampTop(box.top), left: leftSide };
    const rightSide = box.left + box.width + GAP;
    if (rightSide + captionWidth <= window.innerWidth - 16) {
      return { top: clampTop(box.top), left: rightSide };
    }
    return { top: clampTop(window.innerHeight - CAPTION_H - 16), left: clampLeft(box.left) };
  }

  const at = place();

  return (
    <div data-testid="tour" className="fixed inset-0 z-50">
      {/* Four panels around the target. Clicking any of them skips, which is
          the "clicking outside" gesture. */}
      {box ? (
        <>
          <div className={dim} style={{ top: 0, left: 0, right: 0, height: box.top }} onClick={finish} />
          <div className={dim} style={{ top: box.top + box.height, left: 0, right: 0, bottom: 0 }} onClick={finish} />
          <div className={dim} style={{ top: box.top, left: 0, width: box.left, height: box.height }} onClick={finish} />
          <div className={dim} style={{ top: box.top, left: box.left + box.width, right: 0, height: box.height }} onClick={finish} />
          <div
            data-testid="tour-spotlight"
            aria-hidden="true"
            className="pointer-events-none fixed rounded border-2 border-clarify"
            style={{ top: box.top, left: box.left, width: box.width, height: box.height }}
          />
        </>
      ) : (
        <div className={`${dim} inset-0`} onClick={finish} />
      )}

      <div
        ref={caption}
        role="dialog"
        aria-modal="true"
        aria-label={entry.title}
        tabIndex={-1}
        data-testid="tour-caption"
        data-step={step + 1}
        className="fixed left-1/2 w-[min(22rem,calc(100vw-2rem))] -translate-x-1/2 rounded border border-rule bg-panel p-4 shadow-lg sm:left-auto"
        style={{ top: at.top, left: at.left, transform: "none" }}
      >
        <p className="text-[11px] uppercase tracking-wider text-ink/65">
          {copy.tourStepOf(step + 1, total)}
        </p>
        <h2 className="mt-1 text-sm font-semibold text-ink">{entry.title}</h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink/85">{entry.body}</p>
        <div className="mt-3 flex items-center justify-between gap-3">
          <button
            type="button"
            data-testid="tour-skip"
            onClick={finish}
            className="rounded px-2 py-1.5 text-sm text-ink/70 underline underline-offset-2 hover:bg-surface"
          >
            {copy.tourSkip}
          </button>
          <button
            type="button"
            data-testid="tour-next"
            onClick={next}
            className="rounded bg-ink px-4 py-1.5 text-sm font-semibold text-panel"
          >
            {last ? copy.tourDone : copy.tourNext}
          </button>
        </div>
      </div>
    </div>
  );
}
