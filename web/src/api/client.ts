import { fetchEventSource } from "@microsoft/fetch-event-source";
import type {
  Answer,
  ApiErrorBody,
  LoginResponse,
  MetricSummary,
  Readyz,
  Stage,
} from "./types";

const BASE = "/api/v1";

/** A typed failure. The API never returns a bare 500, so neither does this. */
export class ApiError extends Error {
  constructor(readonly body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
  }
}

function unknownFailure(message: string): ApiErrorBody {
  return { code: "INTERNAL", message, retryable: false };
}

async function post<T>(path: string, token: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      (payload as ApiErrorBody | null) ?? unknownFailure(`HTTP ${response.status}`),
    );
  }
  return payload as T;
}

export async function login(role: string): Promise<LoginResponse> {
  const response = await fetch(`${BASE}/auth/demo-login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ role }),
  });
  if (!response.ok) throw new ApiError(unknownFailure("could not switch role"));
  return (await response.json()) as LoginResponse;
}

export async function readyz(): Promise<Readyz> {
  // 503 is a legitimate answer here, not a failure: it is how the API says the
  // model is down and catalog mode is open (J7).
  const response = await fetch("/readyz");
  return (await response.json()) as Readyz;
}

export async function metrics(token: string): Promise<MetricSummary[]> {
  const response = await fetch(`${BASE}/catalog/metrics`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new ApiError(unknownFailure("could not load the catalog"));
  return ((await response.json()) as { metrics: MetricSummary[] }).metrics;
}

export interface CatalogRunResult {
  status: string;
  catalog_mode: boolean;
  rows: (string | number | null)[][];
  columns: string[];
  row_count: number;
  receipt_id: string;
  plan_hash: string;
  sql_hash: string;
}

export function catalogRun(
  token: string,
  body: { metric: string; dimensions?: string[]; window?: unknown; grain?: string; limit?: number },
): Promise<CatalogRunResult> {
  return post<CatalogRunResult>("/catalog/run", token, body);
}

export interface StreamHandlers {
  onStep: (stage: Stage, state: "start" | "end") => void;
  onAnswer: (answer: Answer) => void;
  onError: (body: ApiErrorBody) => void;
  onDone: (receiptId: string | null) => void;
}

/** SSE over POST. The event ORDER is the contract: step* then answer|clarify
 *  then done, or error then done. A stream that stops without saying why is
 *  indistinguishable from a dropped connection, so `onDone` always runs. */
async function stream(
  path: string,
  token: string,
  body: unknown,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  let finished = false;
  try {
    await fetchEventSource(`${BASE}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
      signal,
      openWhenHidden: true,
      async onopen(response) {
        if (response.ok) return;
        const payload: unknown = await response.json().catch(() => null);
        throw new ApiError(
          (payload as ApiErrorBody | null) ?? unknownFailure(`HTTP ${response.status}`),
        );
      },
      onmessage(message) {
        const data: unknown = message.data ? JSON.parse(message.data) : {};
        if (message.event === "step") {
          const step = data as { stage: Stage; state: "start" | "end" };
          handlers.onStep(step.stage, step.state);
        } else if (message.event === "answer" || message.event === "clarify") {
          handlers.onAnswer(data as Answer);
        } else if (message.event === "error") {
          handlers.onError(data as ApiErrorBody);
        } else if (message.event === "done") {
          finished = true;
          handlers.onDone((data as { receipt_id: string | null }).receipt_id);
        }
      },
      onerror(error) {
        throw error; // Do not retry: a replayed demo has nothing to gain from it.
      },
    });
  } catch (error) {
    if (signal.aborted) return;
    handlers.onError(error instanceof ApiError ? error.body : unknownFailure(String(error)));
  } finally {
    if (!finished && !signal.aborted) handlers.onDone(null);
  }
}

export function ask(
  token: string,
  question: string,
  sessionId: string,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  return stream("/ask", token, { question, session_id: sessionId }, handlers, signal);
}

/** M17.1: the choice travels as an id and the ORIGINAL question is resent.
 *  The server matches the id against the options it derived on this run, so
 *  picking an option is possible and inventing one is not. */
export function clarify(
  token: string,
  args: { question: string; sessionId: string; clarificationId: string; optionId: string },
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  return stream(
    "/clarify",
    token,
    {
      question: args.question,
      session_id: args.sessionId,
      clarification_id: args.clarificationId,
      option_id: args.optionId,
    },
    handlers,
    signal,
  );
}
