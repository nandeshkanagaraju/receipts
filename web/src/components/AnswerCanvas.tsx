import { forwardRef } from "react";
import type { Answer, ApiErrorBody, Lang } from "../api/types";
import type { Copy } from "../i18n";
import { ChartView } from "./ChartView";
import { ClarifyChoices } from "./ClarifyChoices";
import { StatusBadge } from "./StatusBadge";

/** StatusBadge, narration, ChartView with a table toggle, ClarifyChoices and
 *  "Ask why" (SDD §22).
 *
 *  "Ask why" is rendered DISABLED with the cut named on it. The why-agent is
 *  M18 and is cut; `POST /api/v1/why` returns a typed 404. Omitting the control
 *  would silently drop a row from a frozen spec and showing it live would
 *  promise a 404, so it is shown and disabled. This is the one documented §22
 *  deviation (LIMITATIONS.md). */
export const AnswerCanvas = forwardRef<
  HTMLDivElement,
  {
    answer: Answer | null;
    failure: ApiErrorBody | null;
    language: Lang;
    copy: Copy;
    busy: boolean;
    onChoose: (optionId: string) => void;
    retryAfter: number | null;
    /** The question, when this answer is the page's own preloaded example
     *  rather than something the visitor asked. Labelled, because a screen that
     *  shows an answer to an unasked question and says nothing is lying about a
     *  small thing on a page whose argument is that it does not. */
    preloaded?: string | null;
  }
>(function AnswerCanvas(
  { answer, failure, language, copy, busy, onChoose, retryAfter, preloaded = null },
  ref,
) {
  if (failure) {
    return (
      <div
        ref={ref}
        tabIndex={-1}
        role="alert"
        data-testid="answer-error"
        data-code={failure.code}
        className="rounded border border-denied/30 bg-denied/[0.05] p-5"
      >
        <h2 className="text-sm font-semibold text-denied">{failure.code}</h2>
        <p className="mt-1 text-sm leading-relaxed text-ink/85">
          {copy.errors[failure.code] ?? failure.message ?? copy.errorFallback}
        </p>
        {retryAfter !== null ? (
          <p className="mt-2 text-sm text-ink/70">{copy.retryIn(retryAfter)}</p>
        ) : null}
      </div>
    );
  }

  if (!answer) return null;

  return (
    <div
      ref={ref}
      tabIndex={-1}
      data-testid="answer-canvas"
      data-status={answer.status}
      aria-label={copy.answerRegion}
      className="rounded border border-rule bg-panel p-5"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <StatusBadge status={answer.status} label={copy.statusOf(answer.status)} />
        {preloaded ? (
          <span data-testid="preloaded-label" className="text-xs text-ink/65">
            {copy.exampleAnswerLabel}
          </span>
        ) : null}
      </div>
      {preloaded ? (
        <p data-testid="preloaded-question" className="mt-3 text-sm italic text-ink/70">
          “{preloaded}”
        </p>
      ) : null}

      {answer.narration ? (
        <p data-testid="narration" className="mt-4 text-[15px] leading-relaxed text-ink">
          {answer.narration}
        </p>
      ) : null}

      {answer.reason && answer.status !== "VERIFIED" ? (
        <p data-testid="answer-reason" className="mt-2 text-sm leading-relaxed text-ink/70">
          {answer.reason}
        </p>
      ) : null}

      {answer.clarification ? (
        <ClarifyChoices
          clarification={answer.clarification}
          onChoose={onChoose}
          busy={busy}
          copy={copy}
        />
      ) : null}

      {answer.table ? (
        <ChartView table={answer.table} chart={answer.chart} language={language} copy={copy} />
      ) : null}

      {answer.table ? (
        <button
          type="button"
          disabled
          data-testid="ask-why"
          title={copy.askWhyCut}
          className="mt-5 cursor-not-allowed text-sm text-ink/65 underline underline-offset-4"
        >
          {copy.askWhy} ›
        </button>
      ) : null}
      {answer.table ? (
        <p className="mt-1 text-xs text-ink/65">{copy.askWhyCut}</p>
      ) : null}
    </div>
  );
});
