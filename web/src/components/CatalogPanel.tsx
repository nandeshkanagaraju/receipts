import { useEffect, useState } from "react";
import { ApiError, metrics as fetchMetrics } from "../api/client";
import type { Lang, MetricSummary } from "../api/types";
import type { Copy } from "../i18n";

/** The governed layer, on screen rather than behind a button.
 *
 *  This list is the project's argument in its most checkable form: every metric
 *  a question can reach, the sentence that defines it, the line in the glossary
 *  that sentence comes from, and the capability a role must hold to use it. It
 *  was a corner button, which asked a reviewer to go looking for the evidence.
 *
 *  It is also what fills the left column before a conversation exists. The
 *  alternative was white space.
 */
export function CatalogPanel({
  token,
  role,
  language,
  copy,
  onOpenDrawer,
}: {
  token: string;
  role: string;
  language: Lang;
  copy: Copy;
  onOpenDrawer: () => void;
}) {
  const [items, setItems] = useState<MetricSummary[]>([]);
  const [failure, setFailure] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  // Re-fetched per role, because the list ITSELF is scoped: a metric behind a
  // capability the role does not hold is absent, not greyed out. Switching role
  // and watching two metrics disappear is the RBAC story told in one click.
  useEffect(() => {
    if (!token) return;
    let live = true;
    fetchMetrics(token)
      .then((loaded) => live && setItems(loaded))
      .catch((error: unknown) =>
        live && setFailure(error instanceof ApiError ? error.body.message : copy.errorFallback),
      );
    return () => {
      live = false;
    };
  }, [token, role, copy.errorFallback]);

  const labelOf = (metric: MetricSummary): string =>
    typeof metric.label === "string" ? metric.label : (metric.label[language] ?? metric.name);

  return (
    <section data-testid="catalog-panel" className="mt-5 flex shrink-0 flex-col">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-ink/70">
          {copy.catalogTitle}
          {items.length > 0 ? (
            <span data-testid="catalog-count" className="ml-1.5 font-normal text-ink/65">
              {items.length}
            </span>
          ) : null}
        </h2>
        <button
          type="button"
          data-testid="open-catalog"
          onClick={onOpenDrawer}
          className="rounded px-1.5 py-0.5 text-xs text-clarify underline underline-offset-2 hover:bg-clarify/[0.06]"
        >
          {copy.catalogRunOne} ›
        </button>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-ink/65">{copy.catalogBlurb}</p>

      {failure ? <p className="mt-2 text-xs text-denied">{failure}</p> : null}

      <ul className="mt-2 max-h-[46vh] divide-y divide-rule overflow-y-auto rounded border border-rule bg-panel">
        {items.map((metric) => {
          const expanded = open === metric.name;
          return (
            <li key={metric.name}>
              <button
                type="button"
                data-testid="catalog-metric-row"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : metric.name)}
                className="w-full px-3 py-2 text-left hover:bg-surface"
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span className="text-[13px] font-medium text-ink">{labelOf(metric)}</span>
                  {metric.required_capability ? (
                    <span
                      data-testid="catalog-capability"
                      className="shrink-0 rounded-full border border-unverified/40 bg-unverified/[0.08] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink/85"
                    >
                      {metric.required_capability}
                    </span>
                  ) : null}
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-ink/65">{metric.name}</span>
              </button>
              {expanded ? (
                <div className="border-t border-rule bg-surface px-3 py-2">
                  <p className="text-[12px] leading-relaxed text-ink/85">{metric.definition}</p>
                  {metric.excludes.length > 0 ? (
                    <p className="mt-1.5 text-[11px] leading-relaxed text-ink/70">
                      <span className="uppercase tracking-wider text-ink/65">{copy.excludes}: </span>
                      {metric.excludes.join("; ")}
                    </p>
                  ) : null}
                  <p className="mt-1.5 text-[11px] text-ink/65">
                    {copy.definedIn} <span className="break-all">{metric.glossary_ref}</span>
                  </p>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
