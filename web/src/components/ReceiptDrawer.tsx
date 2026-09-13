import type { Receipt, Stage } from "../api/types";
import type { Copy } from "../i18n";
import { Drawer } from "./Drawer";

/** SQL, plan and step trace for a receipt (SDD §22). Opened from the card or
 *  by `?receipt=<id>`. */
export function ReceiptDrawer({
  open,
  onClose,
  receipt,
  steps,
  copy,
}: {
  open: boolean;
  onClose: () => void;
  receipt: Receipt | null;
  steps: Stage[];
  copy: Copy;
}) {
  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={`${copy.receipt}${receipt ? ` · ${receipt.receipt_id}` : ""}`}
      closeLabel={copy.closeLabel}
      testId="receipt-drawer"
    >
      {receipt ? (
        <div className="space-y-6">
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink/70">
              {copy.metric}
            </h3>
            <p className="mt-1 font-mono text-sm text-ink">{receipt.metric ?? "—"}</p>
            {receipt.definition ? (
              <p className="mt-1 text-sm leading-relaxed text-ink/80">{receipt.definition}</p>
            ) : null}
            {receipt.siblings.length > 0 ? (
              <p className="mt-2 text-xs text-ink/70">
                {copy.siblings}: {receipt.siblings.join(", ")}
              </p>
            ) : null}
          </section>

          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink/70">
              {copy.trace}
            </h3>
            <ol className="mt-1 flex flex-wrap gap-x-2 gap-y-1 font-mono text-xs text-ink/70">
              {steps.length > 0 ? (
                steps.map((stage, index) => (
                  <li key={`${stage}-${index}`}>
                    {index > 0 ? <span aria-hidden="true">→ </span> : null}
                    {stage}
                  </li>
                ))
              ) : (
                <li>—</li>
              )}
            </ol>
          </section>

          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink/70">
              {copy.plan}
            </h3>
            <dl className="mt-1 space-y-1 font-mono text-xs text-ink/70">
              <div className="flex gap-2">
                <dt className="w-12 shrink-0 text-ink/65">plan</dt>
                <dd className="break-all">{receipt.plan_hash ?? "—"}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-12 shrink-0 text-ink/65">sql</dt>
                <dd className="break-all">{receipt.sql_hash ?? "—"}</dd>
              </div>
            </dl>
          </section>

          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink/70">
              {copy.sql}
            </h3>
            <pre
              data-testid="receipt-sql"
              className="mt-1 overflow-x-auto rounded border border-rule bg-surface p-3 font-mono text-[11px] leading-relaxed text-ink/85"
            >
              {receipt.sql ?? "—"}
            </pre>
          </section>
        </div>
      ) : (
        <p className="text-sm text-ink/70">{copy.noReceiptBody}</p>
      )}
    </Drawer>
  );
}
