import { useState } from "react";
import type { Copy } from "../i18n";

/** Question input, the conversation, and example questions per role in the
 *  user's language (SDD §22).
 *
 *  The "recorded questions" line sits beside the input rather than only in the
 *  error: a reviewer who reads it before typing understands the demo, and one
 *  who discovers it as a 503 concludes the thing is broken. */
export function ChatPane({
  asked,
  examples,
  busy,
  copy,
  onAsk,
  trace,
  stuck,
}: {
  asked: string[];
  examples: readonly string[];
  busy: boolean;
  copy: Copy;
  onAsk: (question: string) => void;
  /** The step trace, rendered between the transcript and the input -- beside
   *  the question it describes rather than above it or below the examples. */
  trace: React.ReactNode;
  /** True when the last attempt failed. The examples come back, because the
   *  error copy tells the reader to try one and they were not on screen. */
  stuck: boolean;
}) {
  const showExamples = asked.length === 0 || stuck;
  const [draft, setDraft] = useState("");

  return (
    <div className="flex shrink-0 flex-col">
      {/* The input and the examples come FIRST, so both are above the fold at
          375px. A transcript-first layout put the one thing a visitor needs to
          click below three other blocks, and the examples below the input --
          which is the correct chat convention and the wrong one here, because
          the examples are the only questions this demo can answer. */}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const question = draft.trim();
          if (!question || busy) return;
          onAsk(question);
          setDraft("");
        }}
      >
        <label htmlFor="question" className="sr-only">
          {copy.askPlaceholder}
        </label>
        <div className="flex gap-2">
          <input
            id="question"
            data-testid="question-input"
            value={draft}
            disabled={busy}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={copy.askPlaceholder}
            /* text-base: 16px, so iOS does not zoom the viewport on focus --
               which is most of what breaks a 375px layout in practice. */
            className="min-w-0 flex-1 rounded border border-rule bg-panel px-3 py-2.5 text-base text-ink placeholder:text-ink/40 disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={busy || draft.trim() === ""}
            data-testid="ask-button"
            className="rounded bg-ink px-4 py-2.5 text-sm font-semibold text-panel disabled:opacity-40"
          >
            {copy.ask}
          </button>
        </div>
        {/* The explanation is always true, so it is always shown. The
            instruction is only true while the examples are on screen. */}
        <p className="mt-2 text-xs leading-relaxed text-ink/65" data-testid="recorded-note">
          {copy.recordedNote}
          {showExamples ? ` ${copy.startWithExample}` : ""}
        </p>
      </form>

      {showExamples ? (
        <ul className="mt-2.5 space-y-1.5" data-testid="examples">
          {examples.map((question) => (
            <li key={question}>
              <button
                type="button"
                disabled={busy}
                data-testid="example-question"
                onClick={() => onAsk(question)}
                className="w-full rounded border border-rule bg-panel px-3 py-2 text-left text-sm leading-relaxed text-ink/80 hover:border-ink/25 hover:bg-surface disabled:opacity-50"
              >
                {question}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {asked.length > 0 ? (
        <ol className="mt-4 space-y-2" data-testid="conversation">
          {asked.map((question, index) => (
            <li
              key={`${index}-${question}`}
              className="rounded border border-rule bg-panel px-3 py-2 text-sm leading-relaxed text-ink"
            >
              {question}
            </li>
          ))}
        </ol>
      ) : null}

      {trace}
    </div>
  );
}
