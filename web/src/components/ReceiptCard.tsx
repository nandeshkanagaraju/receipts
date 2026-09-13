import { useState } from "react";
import type { Copy } from "../i18n";
import type { Receipt } from "../api/types";
import { STATUS_STYLE } from "./StatusBadge";

/** The one bold element (SDD §22). Everything else on the screen is Ink on
 *  Panel with one rule weight; this is the only thing that is *printed*.
 *
 *  Mono throughout, and nowhere else in the app: every value here is an
 *  identifier -- a receipt id, a hash, a date, a metric name -- and a
 *  proportional face invites misreading them. The face change is also the
 *  strongest signal that this is a different kind of object from the narration
 *  beside it. */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-0.5">
      <dt className="w-20 shrink-0 text-[10px] uppercase tracking-wider text-ink/65">{label}</dt>
      <dd className="min-w-0 flex-1 break-words text-[12px] leading-relaxed text-ink/85">
        {children}
      </dd>
    </div>
  );
}

function Hash({ label, value, copy }: { label: string; value: string; copy: Copy }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      title={value}
      onClick={() => {
        void navigator.clipboard?.writeText(value);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      }}
      className="rounded px-1 py-0.5 text-left text-[11px] text-ink/70 hover:bg-ink/5"
    >
      <span className="text-[10px] uppercase tracking-wider text-ink/65">{label} </span>
      {copied ? copy.copied : `${value.slice(0, 8)}…`}
    </button>
  );
}

export function ReceiptCard({
  receipt,
  copy,
  onOpenDrawer,
}: {
  receipt: Receipt;
  copy: Copy;
  onOpenDrawer: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const style = STATUS_STYLE[receipt.status];
  const definition = receipt.definition ?? "";
  const isLong = definition.length > 150;

  return (
    <article
      data-testid="receipt-card"
      data-receipt-id={receipt.receipt_id}
      aria-label={`${copy.receipt} ${receipt.receipt_id}`}
      className="perforated bg-panel px-5 py-6 font-mono shadow-[0_1px_2px_rgba(22,35,58,0.06)]"
    >
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.2em] text-ink/70">
          {copy.receipt}
        </h3>
        <span className="truncate text-[11px] text-ink/65" title={receipt.receipt_id}>
          {receipt.receipt_id}
        </span>
      </header>

      {/* The stamp. Outlined, not filled -- a filled block would need white text
          on the status colour, which three of the five tokens cannot carry at
          AA. Rotation is decorative; the accessible name stays upright. */}
      <div className="my-5 flex justify-center">
        <span
          data-testid="receipt-stamp"
          className={`-rotate-[4deg] rounded-sm border-[1.5px] px-4 py-2 text-[19px] font-semibold uppercase tracking-[0.2em] ${style.border} ${style.text}`}
        >
          <span className="sr-only">{copy.statusOf(receipt.status)}</span>
          <span aria-hidden="true">{receipt.status}</span>
        </span>
      </div>

      {/* The definition is the most important line on the card: it is the
          sentence that makes the number checkable. Prose, not a key/value row. */}
      <section className="mb-4">
        <h4 className="text-[10px] uppercase tracking-wider text-ink/65">{copy.metric}</h4>
        {receipt.metric ? (
          <p className="text-[13px] font-semibold text-ink">{receipt.metric}</p>
        ) : null}
        {definition ? (
          <p className="mt-1 text-[12px] leading-relaxed text-ink/80">
            {isLong && !expanded ? `${definition.slice(0, 150).trimEnd()}…` : definition}
            {isLong ? (
              <button
                type="button"
                onClick={() => setExpanded((open) => !open)}
                className="ml-1 whitespace-nowrap text-clarify underline underline-offset-2"
              >
                {expanded ? copy.less : copy.more} ›
              </button>
            ) : null}
          </p>
        ) : null}
      </section>

      <dl className="border-t border-dashed border-rule pt-3">
        <Row label={copy.window}>{receipt.window_text || "—"}</Row>
        <Row label={copy.scope}>{receipt.scope_text}</Row>
        {/* base_count is null on some paths. Omitted rather than shown as a
            dash: an empty value invites reading it as a count of zero. */}
        {receipt.base_count !== null ? (
          <Row label="Base">{receipt.base_count.toLocaleString("en-IN")}</Row>
        ) : null}
        {receipt.fresh_through ? <Row label={copy.fresh}>{receipt.fresh_through}</Row> : null}
        <Row label={copy.source}>{receipt.source}</Row>
      </dl>

      {receipt.excludes.length > 0 ? (
        <section className="mt-3 border-t border-dashed border-rule pt-3">
          <h4 className="text-[10px] uppercase tracking-wider text-ink/65">{copy.excludes}</h4>
          <ul className="mt-1 space-y-0.5">
            {receipt.excludes.map((item) => (
              <li key={item} className="flex gap-2 text-[12px] leading-relaxed text-ink/80">
                <span aria-hidden="true" className="text-ink/65">
                  −
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* The card's conscience. Rendered verbatim, never re-worded here, and
          never hidden behind "more": this is where the reporting-currency
          decision is disclosed, and a receipt that describes a decision the
          system did not make is worse than no receipt at all. */}
      {receipt.defaults_applied.length > 0 ? (
        <section
          data-testid="receipt-defaults"
          className="mt-3 border-t border-dashed border-rule pt-3"
        >
          <h4 className="text-[10px] uppercase tracking-wider text-ink/65">{copy.defaults}</h4>
          <ul className="mt-1 space-y-1">
            {receipt.defaults_applied.map((item) => (
              <li key={item} className="flex gap-2 text-[12px] leading-relaxed text-ink/80">
                <span aria-hidden="true" className="text-ink/65">
                  →
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {receipt.plan_hash || receipt.sql_hash ? (
        <div className="mt-3 flex flex-wrap gap-x-3 border-t border-dashed border-rule pt-3">
          {receipt.plan_hash ? (
            <Hash label={copy.plan} value={receipt.plan_hash} copy={copy} />
          ) : null}
          {receipt.sql_hash ? <Hash label={copy.sql} value={receipt.sql_hash} copy={copy} /> : null}
        </div>
      ) : null}

      <button
        type="button"
        data-testid="open-receipt-drawer"
        onClick={onOpenDrawer}
        className="mt-4 w-full rounded border border-rule px-3 py-2 text-[12px] font-semibold text-ink/80 hover:bg-surface"
      >
        {copy.showSql} →
      </button>
    </article>
  );
}

/** Three of the five statuses carry no receipt. The rail says why rather than
 *  going blank: blank reads as broken, and the reason is the answer. */
export function NoReceipt({ copy, reason }: { copy: Copy; reason: string | null }) {
  return (
    <aside
      data-testid="no-receipt"
      className="rounded border border-dashed border-rule bg-panel/60 px-4 py-5"
    >
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.2em] text-ink/70">
        {copy.noReceipt}
      </h3>
      <p className="mt-2 text-[13px] leading-relaxed text-ink/70">{copy.noReceiptBody}</p>
      {reason ? <p className="mt-2 text-[13px] leading-relaxed text-ink/85">{reason}</p> : null}
    </aside>
  );
}
