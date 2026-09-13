import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api/client";
import type {
  Answer,
  ApiErrorBody,
  Lang,
  Receipt,
  Role,
  Stage,
} from "./api/types";
import { isRole } from "./api/types";
import { copyFor } from "./i18n";
import { EXAMPLES } from "./examples";
import { AnswerCanvas } from "./components/AnswerCanvas";
import { CatalogDrawer } from "./components/CatalogDrawer";
import { CatalogModeBanner } from "./components/CatalogModeBanner";
import { ChatPane } from "./components/ChatPane";
import { Header } from "./components/Header";
import { NoReceipt, ReceiptCard } from "./components/ReceiptCard";
import { ReceiptDrawer } from "./components/ReceiptDrawer";
import { StepTrace, type StepState } from "./components/StepTrace";

const DEFAULT_ROLE: Role = "rm_tamil_nadu";

/** Deep links (SDD §22): `?receipt=<id>` and `?role=<name>` in demo mode. No
 *  router -- one screen, two drawers, and the query string as the only state
 *  worth sharing. */
function readParams(): { role: Role; receipt: string | null } {
  const params = new URLSearchParams(window.location.search);
  const role = params.get("role");
  return {
    role: role && isRole(role) ? role : DEFAULT_ROLE,
    receipt: params.get("receipt"),
  };
}

export function App() {
  const initial = useRef(readParams());
  const [role, setRole] = useState<Role>(initial.current.role);
  const [language, setLanguage] = useState<Lang>("en");
  const [token, setToken] = useState("");
  const [sessionId] = useState(() => `web-${Math.floor(Date.now() / 1000)}`);

  const [asked, setAsked] = useState<string[]>([]);
  const [lastQuestion, setLastQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [failure, setFailure] = useState<ApiErrorBody | null>(null);
  const [steps, setSteps] = useState<StepState>({});
  const [order, setOrder] = useState<Stage[]>([]);
  const [busy, setBusy] = useState(false);

  const [catalogMode, setCatalogMode] = useState(false);
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [deepReceipt] = useState<string | null>(initial.current.receipt);

  const canvas = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);
  const copy = copyFor(language);

  // A role switch mints a new demo token. The token carries a role name and
  // nothing else; scope is recomputed server-side from roles.yaml (D7).
  useEffect(() => {
    let live = true;
    api
      .login(role)
      .then((session) => {
        if (live) setToken(session.token);
      })
      .catch(() => {
        if (live) setFailure({ code: "AUTH_REQUIRED", message: "", retryable: false });
      });
    return () => {
      live = false;
    };
  }, [role]);

  useEffect(() => {
    api
      .readyz()
      .then((state) => setCatalogMode(state.catalog_mode || state.checks["model"] === "down"))
      .catch(() => setCatalogMode(false));
  }, []);

  // The deep link opens the drawer on load. The receipt itself is whatever the
  // session has answered; a link to another session's receipt shows the drawer
  // with nothing in it rather than inventing one.
  useEffect(() => {
    if (deepReceipt) setReceiptOpen(true);
  }, [deepReceipt]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    params.set("role", role);
    const receiptId = answer?.receipt?.receipt_id;
    if (receiptId) params.set("receipt", receiptId);
    window.history.replaceState(null, "", `?${params.toString()}`);
  }, [role, answer]);

  /** Focus moves to the answer when it arrives (SDD §22 quality floor). */
  const settle = useCallback(() => {
    setBusy(false);
    window.requestAnimationFrame(() => {
      // Scroll as well as focus. At 375px the answer is below the fold, and
      // focus alone does not always bring it into view inside a scroll
      // container.
      canvas.current?.focus();
      canvas.current?.scrollIntoView({ block: "nearest" });
    });
  }, []);

  const handlers = useCallback(
    (): api.StreamHandlers => ({
      onStep: (stage, state) => {
        setSteps((current) => ({ ...current, [stage]: state }));
        if (state === "end") setOrder((current) => [...current, stage]);
      },
      onAnswer: (received) => setAnswer(received),
      onError: (body) => setFailure(body),
      onDone: () => settle(),
    }),
    [settle],
  );

  const run = useCallback(
    (question: string, choice: { clarificationId: string; optionId: string } | null) => {
      if (!token) return;
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      setBusy(true);
      setAnswer(null);
      setFailure(null);
      setSteps({});
      setOrder([]);
      if (!choice) {
        setAsked((current) => [...current, question]);
        setLastQuestion(question);
      }
      const stream = choice
        ? api.clarify(
            token,
            {
              question,
              sessionId,
              clarificationId: choice.clarificationId,
              optionId: choice.optionId,
            },
            handlers(),
            controller.signal,
          )
        : api.ask(token, question, sessionId, handlers(), controller.signal);
      void stream;
    },
    [token, sessionId, handlers],
  );

  const onChoose = useCallback(
    (optionId: string) => {
      const clarification = answer?.clarification;
      if (!clarification) return;
      run(lastQuestion, {
        clarificationId: clarification.clarification_id,
        optionId,
      });
    },
    [answer, lastQuestion, run],
  );

  const receipt: Receipt | null = answer?.receipt ?? null;
  const examples = EXAMPLES[role]?.[language] ?? EXAMPLES[role]?.["en"] ?? [];
  const showRail = answer !== null && !busy;

  return (
    <div className="flex h-full flex-col">
      <Header
        role={role}
        language={language}
        copy={copy}
        onRole={(next) => {
          setRole(next);
          setAnswer(null);
          setFailure(null);
          setAsked([]);
        }}
        onLanguage={setLanguage}
        onCatalog={() => setCatalogOpen(true)}
      />
      {catalogMode ? (
        <CatalogModeBanner copy={copy} onCatalog={() => setCatalogOpen(true)} />
      ) : null}

      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Conversation ~40% on desktop, one column on mobile. */}
        <section className="flex min-h-0 flex-col border-b border-rule px-4 py-5 sm:px-6 lg:w-2/5 lg:border-b-0 lg:border-r">
          <ChatPane
            asked={asked}
            examples={examples}
            busy={busy}
            copy={copy}
            onAsk={(question) => run(question, null)}
            trace={<StepTrace steps={steps} running={busy} copy={copy} />}
          />
        </section>

        {/* Answer canvas, with the receipt docked at its edge. */}
        <section className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-5 sm:px-6">
          {answer === null && failure === null ? (
            <div className="m-auto max-w-md text-center">
              <h2 className="text-lg font-semibold text-ink">{copy.emptyTitle}</h2>
              <p className="mt-2 text-sm leading-relaxed text-ink/65">{copy.emptyBody}</p>
            </div>
          ) : (
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start">
              <div className="min-w-0 flex-1">
                <AnswerCanvas
                  ref={canvas}
                  answer={answer}
                  failure={failure}
                  language={language}
                  copy={copy}
                  busy={busy}
                  onChoose={onChoose}
                  retryAfter={failure?.retry_after ?? null}
                />
              </div>
              {showRail ? (
                <aside className="w-full shrink-0 xl:w-[340px]">
                  {receipt ? (
                    <ReceiptCard
                      receipt={receipt}
                      copy={copy}
                      onOpenDrawer={() => setReceiptOpen(true)}
                    />
                  ) : (
                    <NoReceipt copy={copy} reason={answer?.reason ?? null} />
                  )}
                </aside>
              ) : null}
            </div>
          )}
        </section>
      </main>

      <ReceiptDrawer
        open={receiptOpen}
        onClose={() => setReceiptOpen(false)}
        receipt={receipt}
        steps={order}
        copy={copy}
      />
      <CatalogDrawer
        open={catalogOpen}
        onClose={() => setCatalogOpen(false)}
        token={token}
        catalogMode={catalogMode}
        language={language}
        copy={copy}
      />
    </div>
  );
}
