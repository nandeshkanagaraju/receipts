import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartSpec, Lang, ResultTable, Unit } from "../api/types";
import { DAYS_SUFFIX, formatCell } from "../api/format";
import type { Copy } from "../i18n";

/** Every chart has a table view (SDD §22 quality floor), and the table is not
 *  a fallback: it is the same data, one tab away, always present. A chart with
 *  no table is a number nobody can check. */
export function ChartView({
  table,
  chart,
  language,
  copy,
}: {
  table: ResultTable;
  chart: ChartSpec | null;
  language: Lang;
  copy: Copy;
}) {
  // `chart` is null on the free-form path while the table is present. Defaulting
  // to the table view is the honest reading: nothing chose a chart.
  const [view, setView] = useState<"chart" | "table">(chart ? "chart" : "table");
  const valueColumn = table.columns.find((column) => column.kind === "value");
  const labelColumn = table.columns.find((column) => column.kind !== "value");
  const unit: Unit = valueColumn?.unit ?? chart?.unit ?? "count";
  const currency = valueColumn?.currency ?? chart?.currency ?? null;
  const scalar = chart?.type === "number" || (table.rows.length === 1 && table.columns.length === 1);

  const chartable = chart && !scalar && labelColumn && valueColumn;

  return (
    <section className="mt-5" aria-label={copy.chart}>
      {scalar ? null : (
        <div role="tablist" aria-label={copy.chart} className="mb-3 flex gap-1">
          {(["chart", "table"] as const).map((name) => {
            const disabled = name === "chart" && !chartable;
            return (
              <button
                key={name}
                type="button"
                role="tab"
                aria-selected={view === name}
                disabled={disabled}
                data-testid={`view-${name}`}
                onClick={() => setView(name)}
                className={`rounded border px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40 ${
                  view === name
                    ? "border-ink/25 bg-panel text-ink"
                    : "border-transparent text-ink/70 hover:bg-panel"
                }`}
              >
                {name === "chart" ? copy.chart : copy.table}
              </button>
            );
          })}
        </div>
      )}

      {scalar ? (
        <BigNumber table={table} unit={unit} currency={currency} language={language} />
      ) : view === "chart" && chartable ? (
        <Plot
          table={table}
          chart={chart}
          labelName={labelColumn.name}
          valueName={valueColumn.name}
          unit={unit}
          currency={currency}
          language={language}
        />
      ) : (
        <DataTable table={table} language={language} copy={copy} />
      )}
    </section>
  );
}

function BigNumber({
  table,
  unit,
  currency,
  language,
}: {
  table: ResultTable;
  unit: Unit;
  currency: string | null;
  language: Lang;
}) {
  const cell = table.rows[0]?.[table.columns.findIndex((column) => column.kind === "value")] ?? null;
  const shown = formatCell(cell ?? table.rows[0]?.[0] ?? null, unit, currency, language);
  return (
    <p data-testid="big-number" className="py-2 text-4xl font-semibold tabular-nums text-ink">
      {shown}
      {unit === "days" ? (
        <span className="ml-2 text-base font-normal text-ink/70">
          {DAYS_SUFFIX[language] ?? DAYS_SUFFIX["en"]}
        </span>
      ) : null}
    </p>
  );
}

function Plot({
  table,
  chart,
  labelName,
  valueName,
  unit,
  currency,
  language,
}: {
  table: ResultTable;
  chart: ChartSpec;
  labelName: string;
  valueName: string;
  unit: Unit;
  currency: string | null;
  language: Lang;
}) {
  const labelIndex = table.columns.findIndex((column) => column.name === labelName);
  const valueIndex = table.columns.findIndex((column) => column.name === valueName);
  const data = table.rows.map((row) => ({
    label: String(row[labelIndex] ?? ""),
    value: Number(row[valueIndex] ?? 0),
  }));
  const tick = (value: number) => formatCell(value, unit, currency, language);
  // Bars are read by area, so their axis starts at zero. Recharts would
  // otherwise fit the domain to the data and make 1107 vs 983 look like a
  // landslide -- an honest number presented dishonestly is still a wrong answer.
  const horizontal = chart.type === "hbar";

  return (
    <div className="h-72 w-full" data-testid="chart-plot">
      <ResponsiveContainer width="100%" height="100%">
        {chart.type === "line" ? (
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 8 }}>
            <CartesianGrid stroke="#D9DEE5" strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#16233A" }} />
            <YAxis tickFormatter={tick} tick={{ fontSize: 11, fill: "#16233A" }} width={72} />
            <Tooltip formatter={(value: number) => tick(value)} />
            <Line dataKey="value" stroke="#2E5AAC" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        ) : (
          <BarChart
            data={data}
            layout={horizontal ? "vertical" : "horizontal"}
            margin={{ top: 8, right: 12, bottom: 8, left: 8 }}
          >
            <CartesianGrid stroke="#D9DEE5" strokeDasharray="2 4" vertical={horizontal} horizontal={!horizontal} />
            {horizontal ? (
              <>
                <XAxis
                  type="number"
                  domain={[0, "auto"]}
                  tickFormatter={tick}
                  tick={{ fontSize: 11, fill: "#16233A" }}
                />
                <YAxis type="category" dataKey="label" width={120} tick={{ fontSize: 11, fill: "#16233A" }} />
              </>
            ) : (
              <>
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#16233A" }} />
                <YAxis
                  domain={[0, "auto"]}
                  tickFormatter={tick}
                  tick={{ fontSize: 11, fill: "#16233A" }}
                  width={72}
                />
              </>
            )}
            <Tooltip formatter={(value: number) => tick(value)} />
            <Bar dataKey="value" fill="#2E5AAC" isAnimationActive={false} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

export function DataTable({
  table,
  language,
  copy,
}: {
  table: ResultTable;
  language: Lang;
  copy: Copy;
}) {
  return (
    <div>
      {/* Wide tables scroll inside their own container; the page never scrolls
          sideways, which is most of what "works at 375px" means in practice. */}
      <div className="overflow-x-auto rounded border border-rule">
        <table data-testid="data-table" className="w-full min-w-full text-left text-[13px]">
          <thead className="bg-surface">
            <tr>
              {table.columns.map((column) => (
                <th
                  key={column.name}
                  scope="col"
                  className="whitespace-nowrap px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-ink/70"
                >
                  {column.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-t border-rule">
                {row.map((cell, cellIndex) => {
                  const column = table.columns[cellIndex];
                  return (
                    <td
                      key={cellIndex}
                      className={`px-3 py-2 ${column?.kind === "value" ? "tabular-nums" : ""}`}
                    >
                      {column
                        ? formatCell(cell, column.unit, column.currency, language)
                        : String(cell ?? "—")}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-ink/65">
        {copy.rows(table.rows.length)}
        {table.truncated ? ` · ${copy.truncated}` : ""}
      </p>
    </div>
  );
}
