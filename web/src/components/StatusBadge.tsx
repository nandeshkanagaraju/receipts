import type { Status } from "../api/types";

/** Status as text on a tinted chip, never white on colour.
 *
 *  Measured against the §22 tokens rather than assumed: on Panel, `verified`
 *  is 5.25:1, `clarify` 6.62, `denied` 6.57, `abstain` 5.89 -- but
 *  `unverified` (#A86A12) is **4.43:1**, which misses AA for normal-size text
 *  by a hair, and the tint under it lowers it further to ~4.14.
 *
 *  The token is frozen and the quality floor is not negotiable, so the two are
 *  reconciled by SIZE rather than by changing either. Here, at 12px, the label
 *  is Ink and the token colours the dot and the border -- the word itself still
 *  says which status it is, so nothing is carried by colour alone. On the
 *  receipt stamp the token *is* the text, at 19px/600, where WCAG's large-text
 *  threshold is 3:1 and all five tokens clear it.
 *
 *  Recorded in LIMITATIONS.md beside the "Ask why" deviation. */
export const STATUS_STYLE: Record<Status, { text: string; chip: string; border: string }> = {
  VERIFIED: { text: "text-verified", chip: "bg-verified/[0.08]", border: "border-verified/40" },
  CLARIFY: { text: "text-clarify", chip: "bg-clarify/[0.08]", border: "border-clarify/40" },
  UNVERIFIED: {
    text: "text-unverified",
    chip: "bg-unverified/[0.08]",
    border: "border-unverified/40",
  },
  ABSTAIN: { text: "text-abstain", chip: "bg-abstain/[0.08]", border: "border-abstain/40" },
  DENIED: { text: "text-denied", chip: "bg-denied/[0.08]", border: "border-denied/40" },
  ERROR: { text: "text-denied", chip: "bg-denied/[0.08]", border: "border-denied/40" },
};

export function StatusBadge({ status, label }: { status: Status; label: string }) {
  const style = STATUS_STYLE[status];
  return (
    <span
      data-testid="status-badge"
      data-status={status}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide text-ink/85 ${style.chip} ${style.border}`}
    >
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full bg-current ${style.text}`} />
      <span className="sr-only">{label}</span>
      <span aria-hidden="true">{status}</span>
    </span>
  );
}
