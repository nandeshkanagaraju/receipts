import { STAGES, type Stage } from "../api/types";
import type { Copy } from "../i18n";

export type StepState = Partial<Record<Stage, "start" | "end">>;

/** The stages, live. Not a progress bar for its own sake: this is the same
 *  sequence the receipt will name afterwards, so the asker watches the
 *  reasoning happen and then gets a record of it.
 *
 *  aria-live="polite" so a screen reader hears progress without being
 *  interrupted -- and only the summary is live, not twelve separate rows. */
export function StepTrace({
  steps,
  running,
  copy,
}: {
  steps: StepState;
  running: boolean;
  copy: Copy;
}) {
  const reached = STAGES.filter((stage) => steps[stage] !== undefined);
  if (reached.length === 0 && !running) return null;
  const current = [...reached].reverse().find((stage) => steps[stage] === "start");

  return (
    <section data-testid="step-trace" className="my-4">
      <p aria-live="polite" className="sr-only">
        {running ? `${copy.thinking}: ${current ?? ""}` : ""}
      </p>
      <ul className="flex flex-wrap gap-x-3 gap-y-1">
        {reached.map((stage) => {
          const done = steps[stage] === "end";
          return (
            <li
              key={stage}
              data-testid={`step-${stage}`}
              data-state={steps[stage]}
              className={`flex items-center gap-1.5 text-xs ${done ? "text-ink/70" : "text-clarify"}`}
            >
              <span aria-hidden="true">{done ? "✓" : "⋯"}</span>
              <span>{stage}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
