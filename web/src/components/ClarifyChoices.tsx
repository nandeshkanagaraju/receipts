import type { Clarification } from "../api/types";
import type { Copy } from "../i18n";

/** One tap per choice (PDD §8.1).
 *
 *  M17.1: the button carries the option's `option_id` and nothing else. The
 *  server matches it against the options it derived on this run, so the asker
 *  picks a plan rather than describing one -- and before M17.1 both buttons
 *  here would have returned the same number. */
export function ClarifyChoices({
  clarification,
  onChoose,
  busy,
  copy,
}: {
  clarification: Clarification;
  onChoose: (optionId: string) => void;
  busy: boolean;
  copy: Copy;
}) {
  return (
    <section data-testid="clarify-choices" className="mt-4">
      <h3 className="text-sm font-semibold text-ink">{clarification.prompt}</h3>
      <ul className="mt-3 space-y-2">
        {clarification.options.map((option) => (
          <li key={option.option_id}>
            <button
              type="button"
              disabled={busy}
              data-testid="clarify-option"
              data-option-id={option.option_id}
              onClick={() => onChoose(option.option_id)}
              className="w-full rounded border border-rule bg-panel px-4 py-3 text-left text-sm text-ink hover:border-clarify/50 hover:bg-clarify/[0.04] disabled:opacity-50"
            >
              {option.label}
            </button>
          </li>
        ))}
      </ul>
      <p className="sr-only">{copy.answerRegion}</p>
    </section>
  );
}
