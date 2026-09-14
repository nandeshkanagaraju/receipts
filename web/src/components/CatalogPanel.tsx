import { useEffect, useState } from "react";
import { ApiError, metrics as fetchMetrics, schema as fetchSchema } from "../api/client";
import type { Lang, MetricSummary, SchemaTable } from "../api/types";
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
  const [tables, setTables] = useState<SchemaTable[]>([]);
  const [failure, setFailure] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [tab, setTab] = useState<"metrics" | "schema">("metrics");

  // Re-fetched per role, because the list ITSELF is scoped: a metric behind a
  // capability the role does not hold is absent, not greyed out. Switching role
  // and watching two metrics disappear is the RBAC story told in one click.
  useEffect(() => {
    if (!token) return;
    let live = true;
    Promise.all([fetchMetrics(token), fetchSchema(token)])
      .then(([loadedMetrics, loadedTables]) => {
        if (!live) return;
        setItems(loadedMetrics);
        setTables(loadedTables);
      })
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
        {/* Two views, and the order is the argument: the governed layer is what
            you can ask, the schema is what it sits on. Metrics is the default
            because a reviewer who sees the table list first has seen a
            database, which every project has. */}
        <div role="tablist" aria-label={copy.catalogTitle} className="flex gap-1">
          {(["metrics", "schema"] as const).map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={tab === name}
              data-testid={`catalog-tab-${name}`}
              onClick={() => {
                setTab(name);
                setOpen(null);
              }}
              className={`rounded px-2 py-1 text-[11px] font-semibold uppercase tracking-wider ${
                tab === name ? "bg-ink text-panel" : "text-ink/70 hover:bg-ink/5"
              }`}
            >
              {name === "metrics" ? copy.tabMetrics : copy.tabSchema}
              {/* No extra opacity: it compounds with the tab's own `text-ink/70` to
    about 0.52 effective and drops the count below WCAG AA. Caught by
    axe, invisible by eye. */}
              <span className="ml-1.5 font-normal">
                {name === "metrics" ? items.length || "" : tables.length || ""}
              </span>
            </button>
          ))}
        </div>
        {tab === "metrics" ? (
          <button
            type="button"
            data-testid="open-catalog"
            onClick={onOpenDrawer}
            className="rounded px-1.5 py-0.5 text-xs text-clarify underline underline-offset-2 hover:bg-clarify/[0.06]"
          >
            {copy.catalogRunOne} ›
          </button>
        ) : null}
      </div>
      <p className="mt-1 text-xs leading-relaxed text-ink/65">
        {tab === "metrics" ? copy.catalogBlurb : copy.schemaBlurb}
      </p>

      {failure ? <p className="mt-2 text-xs text-denied">{failure}</p> : null}

      {tab === "metrics" ? (
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
                  <span className="mt-0.5 flex flex-wrap items-baseline gap-x-2 text-[11px] text-ink/65">
                    <span>{metric.name}</span>
                    <span aria-hidden="true">·</span>
                    <span data-testid="catalog-owner">
                      {copy.ownedBy} {metric.owner}
                    </span>
                  </span>
                </button>
                {expanded ? (
                  <div className="border-t border-rule bg-surface px-3 py-2">
                    <p className="text-[12px] leading-relaxed text-ink/85">{metric.definition}</p>
                    <p className="mt-1.5 text-[11px] leading-relaxed text-ink/70">
                      <span className="uppercase tracking-wider text-ink/65">
                        {copy.breakDownBy}:{" "}
                      </span>
                      {metric.allowed_dimensions.join(", ")}
                    </p>
                    {metric.excludes.length > 0 ? (
                      <p className="mt-1.5 text-[11px] leading-relaxed text-ink/70">
                        <span className="uppercase tracking-wider text-ink/65">
                          {copy.excludes}:{" "}
                        </span>
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
      ) : (
        <ul
          data-testid="schema-list"
          className="mt-2 max-h-[46vh] divide-y divide-rule overflow-y-auto rounded border border-rule bg-panel"
        >
          {tables.map((table) => {
            const expanded = open === table.name;
            return (
              <li key={table.name}>
                <button
                  type="button"
                  data-testid="schema-table-row"
                  aria-expanded={expanded}
                  onClick={() => setOpen(expanded ? null : table.name)}
                  className="w-full px-3 py-2 text-left hover:bg-surface"
                >
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="text-[13px] font-medium text-ink">{table.name}</span>
                    <span className="shrink-0 text-[11px] text-ink/65">
                      {table.columns.length} cols
                    </span>
                  </span>
                  <span className="mt-0.5 flex flex-wrap items-baseline gap-x-2 text-[11px] text-ink/65">
                    <span>
                      {copy.primaryKey} {table.primary_key.join(", ") || "—"}
                    </span>
                    {table.reference ? (
                      <>
                        <span aria-hidden="true">·</span>
                        <span>{copy.referenceTable}</span>
                      </>
                    ) : null}
                  </span>
                </button>
                {expanded ? (
                  <div className="border-t border-rule bg-surface px-3 py-2">
                    <ul className="space-y-0.5">
                      {table.columns.map((column) => (
                        <li
                          key={column.name}
                          className="flex justify-between gap-3 text-[11px]"
                        >
                          <span className="text-ink/85">{column.name}</span>
                          <span className="shrink-0 text-ink/65">{column.type}</span>
                        </li>
                      ))}
                    </ul>
                    {table.scope_path.length > 0 ? (
                      <p className="mt-2 text-[11px] leading-relaxed text-ink/70">
                        <span className="uppercase tracking-wider text-ink/65">
                          {copy.joinPath}:{" "}
                        </span>
                        <span className="break-all">{table.scope_path.join(" → ")}</span>
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
