import { expect, test } from "@playwright/test";

/** The committed screenshots. Not assertions -- artefacts for the record.
 *  BUILD_PROMPTS M17 asks for a 375px shot of the Ask screen; the rest are the
 *  VERIFY walkthrough, one per demo role. */
const SHOTS: { role: string; question: string; name: string }[] = [
  {
    role: "rm_tamil_nadu",
    question: "நேற்று சென்னையில் நமது UPI success rate எவ்வளவு?",
    name: "rm_tamil_nadu-ta",
  },
  {
    role: "global_finance",
    question: "How much captured money was still unsettled at the end of August?",
    name: "global_finance-en",
  },
  {
    role: "store_ops_uk",
    question: "Top 5 UK showrooms by units sold last month.",
    name: "store_ops_uk-en",
  },
  {
    role: "admin",
    question: "Total captured GMV across all countries last month, in US dollars.",
    name: "admin-en",
  },
];

for (const shot of SHOTS) {
  test(`screenshot ${shot.name}`, async ({ page }, info) => {
    const width = info.project.name === "mobile" ? 375 : 1280;
    await page.goto(`/?role=${shot.role}`);
    await page.getByTestId("question-input").fill(shot.question);
    await page.getByTestId("ask-button").click();
    await expect(page.getByTestId("answer-canvas")).toBeVisible({ timeout: 40_000 });
    await expect(page.getByTestId("receipt-card")).toBeVisible();
    await page.screenshot({
      path: `../docs/screens/ask-${width}-${shot.name}.png`,
      fullPage: true,
    });
  });
}
