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
    <div className="flex h-full flex-col">
      {/* Bottom-aligned: a transcript grows downwards, and `flex-1` alone left
          a large void between the first question and the input. */}
      <ol
        className="flex flex-1 flex-col justify-end space-y-3 overflow-y-auto"
        data-testid="conversation"
      >
        {asked.map((question, index) => (
          <li
            key={`${index}-${question}`}
            className="rounded border border-rule bg-panel px-4 py-3 text-sm leading-relaxed text-ink"
          >
            {question}
          </li>
        ))}
      </ol>

      {trace}

      <form
        className="mt-1"
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
            className="min-w-0 flex-1 rounded border border-rule bg-panel px-3 py-2.5 text-base text-ink placeholder:text-ink/65 disabled:opacity-60"
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
            instruction is only true while the examples are on screen, so it is
            only shown then -- a note telling the reader to start with an
            example below, above nothing, is a small lie about its own page. */}
        <p className="mt-2 text-xs leading-relaxed text-ink/65" data-testid="recorded-note">
          {copy.recordedNote}
          {showExamples ? ` ${copy.startWithExample}` : ""}
        </p>
      </form>

      {/* Examples are an empty state, so they go once an answer is on screen --
          leaving them up pushed the answer below three buttons and the trace at
          375px. But they come BACK on a failure.
          
          Without that, the 503 copy said "try one of the examples" while the
          examples were hidden: the one thing the error told the reader to do was
          the one thing they could not see. A first-time visitor who typed their
          own question before clicking an example reached a dead end that named
          its own way out and then withheld it. */}
      {showExamples ? (
        <ul className="mt-3 space-y-1.5" data-testid="examples">
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
    </div>
  );
}
