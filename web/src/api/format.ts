import type { Cell, Lang, Unit } from "./types";

/** The locale whose grouping the asker expects. `en-IN` gives ₹12,34,567 --
 *  the lakh/crore grouping, which is the point of naming it rather than using
 *  the browser's default (SDD §22). */
const LOCALES: Record<string, string> = {
  en: "en-IN",
  ta: "ta-IN",
  hi: "hi-IN",
  "ta-Latn": "ta-IN",
  "hi-Latn": "hi-IN",
};

export function localeFor(language: Lang | string): string {
  return LOCALES[language] ?? "en-IN";
}

/** Money arrives as integer MINOR units (D1). Dividing by 100 for display is
 *  the only place that number stops being an integer, and it never travels
 *  back: nothing is computed from this value, it is only shown. */
export function formatMoney(minor: number, currency: string, language: Lang | string): string {
  return new Intl.NumberFormat(localeFor(language), {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(minor / 100);
}

/** Ratios arrive as a Decimal rendered to a JSON string. `parseFloat` here is
 *  display-only and deliberate: the value is never fed back into arithmetic. */
export function formatRatio(value: number, language: Lang | string): string {
  return new Intl.NumberFormat(localeFor(language), {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatCount(value: number, language: Lang | string): string {
  return new Intl.NumberFormat(localeFor(language)).format(value);
}

export function formatDays(value: number, language: Lang | string): string {
  return new Intl.NumberFormat(localeFor(language), {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value);
}

function asNumber(cell: Cell): number | null {
  if (cell === null) return null;
  const value = typeof cell === "number" ? cell : Number(cell);
  return Number.isFinite(value) ? value : null;
}

/** One cell, formatted for its column's unit. A cell that is not a number --
 *  a dimension label, a date -- is shown as itself rather than coerced. */
export function formatCell(
  cell: Cell,
  unit: Unit,
  currency: string | null,
  language: Lang | string,
): string {
  if (cell === null) return "—";
  const value = asNumber(cell);
  if (value === null) return String(cell);
  switch (unit) {
    case "money":
      return currency ? formatMoney(value, currency, language) : formatCount(value, language);
    case "ratio":
      return formatRatio(value, language);
    case "days":
      return `${formatDays(value, language)}`;
    default:
      return formatCount(value, language);
  }
}

/** The unit suffix a days value needs, in the asker's language. */
export const DAYS_SUFFIX: Record<string, string> = {
  en: "days",
  ta: "நாட்கள்",
  hi: "दिन",
};
