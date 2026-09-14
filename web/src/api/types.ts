// The wire shapes, narrowed from the generated OpenAPI schema.
//
// `schema.d.ts` is generated and authoritative for the ROUTES; the engine's
// Answer is `additionalProperties` at the FastAPI boundary, so the fields below
// are written out here against SDD §8 and verified by the E2E tests rather than
// inferred. Every one of them was printed from a running answer before it was
// typed.
import type { paths } from "./schema";

export type Status = "VERIFIED" | "CLARIFY" | "UNVERIFIED" | "ABSTAIN" | "DENIED" | "ERROR";
export type Lang = "en" | "ta" | "hi" | "ta-Latn" | "hi-Latn";
export type Unit = "count" | "ratio" | "money" | "days";

/** The demo-login body. FastAPI types this route as `dict[str, Any]`, so the
 *  generated schema widens it to an index signature; the two fields are named
 *  here and asserted by the E2E login. `paths` is still re-exported so a route
 *  renamed in the API breaks this file at build time. */
export interface LoginResponse {
  token: string;
  role: string;
}
export type ApiPaths = paths;

export interface Column {
  name: string;
  kind: "dim" | "time" | "value";
  unit: Unit;
  currency: string | null;
}

/** Decimal arrives as a JSON string; money as integer minor units. */
export type Cell = string | number | null;

export interface ResultTable {
  columns: Column[];
  rows: Cell[][];
  truncated: boolean;
}

export interface ChartSpec {
  type: "number" | "line" | "bar" | "hbar" | "grouped_bar" | "table";
  x: string | null;
  y: string;
  series: string | null;
  unit: Unit;
  currency: string | null;
}

export interface Receipt {
  receipt_id: string;
  status: Status;
  metric: string | null;
  definition: string | null;
  scope_text: string;
  window_text: string;
  excludes: string[];
  base_count: number | null;
  source: string;
  fresh_through: string | null;
  defaults_applied: string[];
  siblings: string[];
  plan_hash: string | null;
  sql_hash: string | null;
  sql: string | null;
}

export interface ClarifyChoice {
  option_id: string;
  label: string;
  patch_json: string;
}

export interface Clarification {
  clarification_id: string;
  prompt: string;
  options: ClarifyChoice[];
}

export interface Answer {
  status: Status;
  language: Lang;
  narration: string;
  table: ResultTable | null;
  chart: ChartSpec | null;
  receipt: Receipt | null;
  clarification: Clarification | null;
  reason: string | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  retryable: boolean;
  retry_after?: number;
  catalog_mode?: boolean;
}

export interface Readyz {
  ready: boolean;
  checks: Record<string, string>;
  catalog_mode: boolean;
}

export interface MetricSummary {
  name: string;
  label: Record<string, string> | string;
  definition: string;
  unit: Unit;
  siblings: string[];
  allowed_dimensions: string[];
  /** Where the definition is written down — GLOSSARY.md and an anchor. */
  glossary_ref: string;
  /** What a role must hold to use it at all. Null means anyone in scope. */
  required_capability: string | null;
  excludes: string[];
}

/** The stages the API publishes, in order (receipts.api.sse.STAGES). */
export const STAGES = [
  "language",
  "intent",
  "retrieve",
  "plan",
  "validate",
  "gate",
  "compile",
  "guard",
  "execute",
  "compose",
  "ground",
  "receipt",
] as const;
export type Stage = (typeof STAGES)[number];

export const ROLES = ["rm_tamil_nadu", "global_finance", "store_ops_uk", "admin"] as const;
export type Role = (typeof ROLES)[number];

export function isRole(value: string): value is Role {
  return (ROLES as readonly string[]).includes(value);
}
