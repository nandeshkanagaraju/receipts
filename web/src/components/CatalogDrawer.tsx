import { useEffect, useState } from "react";
import { catalogRun, metrics as fetchMetrics, ApiError } from "../api/client";
import type { CatalogRunResult } from "../api/client";
import type { Lang, MetricSummary } from "../api/types";
import type { Copy } from "../i18n";
import { Drawer } from "./Drawer";

/** Metric definitions and dimensions; in catalog mode it becomes the
 *  CatalogRunForm (SDD §22).
 *
 *  The form is not a degraded copy of the Ask screen. It runs
 *  validate → compile → guard → execute on a plan the caller hand-built, with
 *  no model anywhere in the path -- which is why a model outage leaves the
 *  product working (J7). */
export function CatalogDrawer({
  open,
  onClose,
  token,
  catalogMode,
  language,
  copy,
}: {
  open: boolean;
  onClose: () => void;
  token: string;
  catalogMode: boolean;
  language: Lang;
  copy: Copy;
}) {
  const [items, setItems] = useState<MetricSummary[]>([]);
  const [chosen, setChosen] = useState<string>("");
  const [result, setResult] = useState<CatalogRunResult | null>(null);
  const [failure, setFailure] = useState<string>("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !token) return;
    fetchMetrics(token)
      .then((loaded) => setItems(loaded))
      .catch((error: unknown) =>
        setFailure(error instanceof ApiError ? error.body.message : copy.errorFallback),
      );
  }, [open, token, copy.errorFallback]);

  const labelOf = (metric: MetricSummary): string =>
    typeof metric.label === "string" ? metric.label : (metric.label[language] ?? metric.name);

  async function run(): Promise<void> {
    if (!chosen) return;
    setBusy(true);
    setFailure("");
    setResult(null);
    try {
      setResult(await catalogRun(token, { metric: chosen, window: {}, grain: "NONE" }));
    } catch (error: unknown) {
      setFailure(error instanceof ApiError ? error.body.message : copy.errorFallback);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={copy.catalog}
      closeLabel={copy.closeLabel}
      testId="catalog-drawer"
    >
      <form
        data-testid="catalog-run-form"
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
        className="mb-6 rounded border border-rule bg-surface p-4"
      >
        <label htmlFor="catalog-metric" className="block text-xs font-semibold text-ink/70">
          {copy.metric}
        </label>
        <div className="mt-2 flex flex-wrap gap-2">
          <select
            id="catalog-metric"
            data-testid="catalog-metric"
            value={chosen}
            onChange={(event) => setChosen(event.target.value)}
            className="min-w-0 flex-1 rounded border border-rule bg-panel px-2 py-2 text-sm"
          >
            <option value="">{copy.noMetricChosen}</option>
            {items.map((metric) => (
              <option key={metric.name} value={metric.name}>
                {labelOf(metric)}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={!chosen || busy}
            data-testid="catalog-run"
            className="rounded bg-ink px-4 py-2 text-sm font-semibold text-panel disabled:opacity-40"
          >
            {copy.runIt}
          </button>
        </div>
        {catalogMode ? (
          <p className="mt-2 text-xs text-unverified">{copy.catalogModeBody}</p>
        ) : null}
        {failure ? (
          <p data-testid="catalog-error" className="mt-2 text-xs text-denied">
            {failure}
          </p>
        ) : null}
        {result ? (
          <div data-testid="catalog-result" className="mt-3 rounded border border-rule bg-panel p-3">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[13px]">
                <thead>
                  <tr>
                    {result.columns.map((name) => (
                      <th key={name} scope="col" className="px-2 py-1 text-xs text-ink/70">
                        {name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, index) => (
                    <tr key={index} className="border-t border-rule">
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex} className="px-2 py-1 tabular-nums">
                          {String(cell ?? "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-[11px] text-ink/70">
              {copy.receipt} {result.receipt_id}
            </p>
          </div>
        ) : null}
      </form>

      <ul className="space-y-4">
        {items.map((metric) => (
          <li key={metric.name} className="border-b border-rule pb-4 last:border-0">
            <h3 className="text-sm font-semibold text-ink">{metric.name}</h3>
            <p className="text-xs text-ink/70">{labelOf(metric)}</p>
            <p className="mt-1 text-sm leading-relaxed text-ink/80">{metric.definition}</p>
            <p className="mt-1 text-xs text-ink/70">
              {metric.allowed_dimensions.slice(0, 8).join(" · ")}
            </p>
          </li>
        ))}
      </ul>
    </Drawer>
  );
}
