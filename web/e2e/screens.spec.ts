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
    // The tour auto-starts on a first visit and its overlay intercepts clicks.
    // Every spec that navigates directly has to opt out, or it tests the tour.
    await page.addInitScript(() => window.localStorage.setItem("receipts.tour.v1", "1"));
    await page.goto(`/?role=${shot.role}`);
    // The same rate-limit wait the journeys use. This spec runs after them, so
    // by the time it starts the demo's 20-a-minute allowance is often spent --
    // and a screenshot of an error page is a screenshot nobody wants committed.
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await page.getByTestId("question-input").fill(shot.question);
      await page.getByTestId("ask-button").click();
      const canvas = page.getByTestId("answer-canvas");
      const failure = page.getByTestId("answer-error");
      await expect(canvas.or(failure)).toBeVisible({ timeout: 40_000 });
      if ((await failure.count()) === 0) break;
      expect(await failure.getAttribute("data-code")).toBe("RATE_LIMITED");
      await page.waitForTimeout(61_000 - (Date.now() % 60_000));
    }
    await expect(page.getByTestId("answer-canvas")).toBeVisible();
    await expect(page.getByTestId("receipt-card")).toBeVisible();
    await page.screenshot({
      path: `../docs/screens/ask-${width}-${shot.name}.png`,
      fullPage: true,
    });
  });
}
