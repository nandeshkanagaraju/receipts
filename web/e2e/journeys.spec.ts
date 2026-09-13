import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/** PDD §8.3 journeys, through the real UI against the real API in replay.
 *
 *  The questions are the exact recorded dev questions: the replay key hashes
 *  the question text, so a paraphrase is a 503 rather than a different answer.
 */
const J1_TA = "நேற்று சென்னையில் நமது UPI success rate எவ்வளவு?";
const J3_EN = "What was our revenue last month?";
const J4_EN = "How satisfied were our Chennai customers last month?";
const J5_EN = "What were the Dubai showrooms' sales last week?";
const J10_EN = "Card success rate by issuing bank in the UK last month, top 10.";

async function open(page: Page, role: string): Promise<void> {
  await page.goto(`/?role=${role}`);
  await expect(page.getByTestId("role-switcher")).toHaveValue(role);
}

/** Ask, and wait for the answer.
 *
 *  The demo allows 20 questions a minute per role AND per IP (SDD §19), which
 *  the suite genuinely exceeds -- it is one browser asking as one role. Rather
 *  than turning the limiter off for tests, this waits out the window the API
 *  itself names in `retry_after` and asks again, which is what the UI tells a
 *  user to do. A limiter disabled for the tests is a limiter nobody tests. */
async function ask(page: Page, question: string): Promise<void> {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.getByTestId("question-input").fill(question);
    await page.getByTestId("ask-button").click();
    const canvas = page.getByTestId("answer-canvas");
    const failure = page.getByTestId("answer-error");
    await expect(canvas.or(failure)).toBeVisible({ timeout: 40_000 });
    if ((await failure.count()) === 0) return;
    if ((await failure.getAttribute("data-code")) !== "RATE_LIMITED") return;
    await page.waitForTimeout(61_000 - (Date.now() % 60_000));
  }
}

test.describe("PDD §8.3", () => {
  test("J1 — a Tamil question gets a Tamil answer and a receipt", async ({ page }) => {
    await open(page, "rm_tamil_nadu");
    await ask(page, J1_TA);

    await expect(page.getByTestId("answer-canvas")).toHaveAttribute("data-status", "VERIFIED");
    const narration = await page.getByTestId("narration").innerText();
    // Tamil script, not merely "an answer came back".
    expect(narration).toMatch(/[஀-௿]/);

    const card = page.getByTestId("receipt-card");
    await expect(card).toBeVisible();
    await expect(page.getByTestId("receipt-stamp")).toContainText("VERIFIED");
    const receiptId = await card.getAttribute("data-receipt-id");
    expect(receiptId).toMatch(/^[0-9a-f]{16}$/);

    // The receipt discloses the reporting currency it actually used.
    await expect(page.getByTestId("receipt-defaults")).toContainText("INR");
  });

  test("J3 — one clarification, then the answer the user chose", async ({ page }) => {
    await open(page, "rm_tamil_nadu");
    await ask(page, J3_EN);

    await expect(page.getByTestId("answer-canvas")).toHaveAttribute("data-status", "CLARIFY");
    const options = page.getByTestId("clarify-option");
    await expect(options).toHaveCount(2);
    // No receipt while the question is still a question.
    await expect(page.getByTestId("no-receipt")).toBeVisible();

    // M17.1: pick the SECOND option and require its own metric back. Before the
    // fix both options returned net_revenue, VERIFIED, with a receipt.
    const second = options.nth(1);
    const label = (await second.innerText()).split(":")[0]?.trim();
    await second.click();

    await expect(page.getByTestId("answer-canvas")).toHaveAttribute("data-status", "VERIFIED", {
      timeout: 40_000,
    });
    await expect(page.getByTestId("receipt-card")).toBeVisible();
    expect(label).toBeTruthy();
    await expect(page.getByTestId("receipt-card")).toContainText(label!);
  });

  test("J4 — abstain, saying what is missing, with no receipt", async ({ page }) => {
    await open(page, "rm_tamil_nadu");
    await ask(page, J4_EN);

    await expect(page.getByTestId("answer-canvas")).toHaveAttribute("data-status", "ABSTAIN");
    await expect(page.getByTestId("answer-reason")).toBeVisible();
    await expect(page.getByTestId("receipt-card")).toHaveCount(0);
    await expect(page.getByTestId("no-receipt")).toBeVisible();
  });

  test("J5 — denied, and no UAE number anywhere on the page", async ({ page }) => {
    await open(page, "rm_tamil_nadu");
    await ask(page, J5_EN);

    await expect(page.getByTestId("answer-canvas")).toHaveAttribute("data-status", "DENIED");
    await expect(page.getByTestId("receipt-card")).toHaveCount(0);

    // PDD J5 is "no UAE NUMBERS anywhere in the response or trace", and the
    // distinction is the whole point. Naming Dubai in the refusal is correct:
    // it tells the asker what was refused, and it discloses nothing about
    // whether Dubai has data or what the data says. Asserting the word were
    // absent would be testing something the PDD does not ask for -- and would
    // push the product towards a refusal that does not say what it refused.
    const produced = (
      await page.locator("main section:nth-of-type(2)").innerText()
    ).toLowerCase();

    // No digit anywhere in what the system produced. A denial that reports a
    // number has answered the question it refused, and a row count, a date or
    // a currency amount would each be such a number.
    expect(produced).not.toMatch(/\d/);
    for (const term of ["aed", "dirham"]) {
      expect(produced).not.toContain(term);
    }

    // The asker's own question is echoed, and must be, or the screen would be
    // lying about what was asked.
    const conversation = (await page.getByTestId("conversation").innerText()).toLowerCase();
    expect(conversation).toContain("dubai");

    // No table and no chart: there is nothing to show.
    await expect(page.getByTestId("data-table")).toHaveCount(0);
    await expect(page.getByTestId("big-number")).toHaveCount(0);
  });

  test("J7 — the catalog form answers with no model in the path", async ({ page }) => {
    await open(page, "global_finance");
    await page.getByTestId("open-catalog").click();
    await expect(page.getByTestId("catalog-drawer")).toBeVisible();

    const result = page.getByTestId("catalog-result");
    const failure = page.getByTestId("catalog-error");
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await page.getByTestId("catalog-metric").selectOption("gmv_captured");
      await page.getByTestId("catalog-run").click();
      await expect(result.or(failure)).toBeVisible({ timeout: 30_000 });
      if ((await failure.count()) === 0) break;
      // /catalog/run is rate-limited like every other question-shaped route.
      expect(await failure.getAttribute("data-code")).toBe("RATE_LIMITED");
      await page.waitForTimeout(61_000 - (Date.now() % 60_000));
    }
    await expect(result).toBeVisible();
    await expect(result).toContainText("Receipt");
  });

  test("J10 — a follow-up split by a dimension renders as a table", async ({ page }) => {
    await open(page, "store_ops_uk");
    await ask(page, J10_EN);

    await expect(page.getByTestId("answer-canvas")).toHaveAttribute("data-status", "VERIFIED");
    // A breakdown: every chart has a table view, and this one has real rows.
    await page.getByTestId("view-table").click();
    const table = page.getByTestId("data-table");
    await expect(table).toBeVisible();
    expect(await table.locator("tbody tr").count()).toBeGreaterThan(1);
  });
});

test.describe("a first-time visitor is never at a dead end", () => {
  test("an unrecorded question explains itself and the way out is on screen", async ({
    page,
  }) => {
    await open(page, "rm_tamil_nadu");

    // Exactly what a reviewer does: type their own question before noticing
    // the examples. Nothing recorded this, so it cannot be answered.
    await page.getByTestId("question-input").fill("what is the airspeed of a swallow");
    await page.getByTestId("ask-button").click();

    const failure = page.getByTestId("answer-error");
    await expect(failure).toBeVisible({ timeout: 40_000 });
    await expect(failure).toHaveAttribute("data-code", "MODEL_UNAVAILABLE");

    // It says nothing is broken, and says why.
    await expect(failure).toContainText("Nothing is broken");
    await expect(failure).toContainText("recorded evaluation");

    // And the thing it tells them to do is ON SCREEN. Before this, the copy
    // said "try one of the examples" while the examples were hidden.
    const examples = page.getByTestId("example-question");
    await expect(examples.first()).toBeVisible();
    expect(await examples.count()).toBeGreaterThanOrEqual(3);

    // Clicking one gets a real answer with a receipt: the dead end has an exit
    // and the exit works.
    await examples.first().click();
    await expect(page.getByTestId("answer-canvas")).toHaveAttribute("data-status", "VERIFIED", {
      timeout: 40_000,
    });
    await expect(page.getByTestId("receipt-card")).toBeVisible();
  });

  test("the replay note is visible before anything is typed", async ({ page }) => {
    await open(page, "rm_tamil_nadu");
    const note = page.getByTestId("recorded-note");
    await expect(note).toBeVisible();
    // It leads with what IS true rather than with what is missing.
    await expect(note).toContainText("replayed from the recorded evaluation");
    await expect(note).toContainText("Start with an example");
    // And the examples it names are there to start with.
    expect(await page.getByTestId("example-question").count()).toBeGreaterThanOrEqual(3);

    // Once an answer is up the examples go, and so does the instruction to use
    // them -- the note must not point below itself at nothing.
    await page.getByTestId("example-question").first().click();
    await expect(page.getByTestId("answer-canvas")).toBeVisible({ timeout: 40_000 });
    await expect(page.getByTestId("example-question")).toHaveCount(0);
    await expect(note).toContainText("replayed from the recorded evaluation");
    await expect(note).not.toContainText("Start with an example");
  });
});

test.describe("quality floor (SDD §22)", () => {
  test("axe-core finds no serious violation with an answer rendered", async ({ page }) => {
    await open(page, "rm_tamil_nadu");
    await ask(page, J1_TA);
    await expect(page.getByTestId("receipt-card")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = results.violations.filter(
      (violation) => violation.impact === "serious" || violation.impact === "critical",
    );
    if (serious.length > 0) {
      console.log(JSON.stringify(serious.map((v) => ({ id: v.id, nodes: v.nodes.length })), null, 2));
    }
    expect(serious).toEqual([]);
  });

  test("focus moves to the answer when it arrives", async ({ page }) => {
    await open(page, "rm_tamil_nadu");
    await ask(page, J1_TA);
    await expect(page.getByTestId("answer-canvas")).toBeFocused();
  });

  test("the screen is keyboard-complete and the drawer traps and restores focus", async ({
    page,
  }) => {
    await open(page, "rm_tamil_nadu");
    await ask(page, J1_TA);

    const opener = page.getByTestId("open-receipt-drawer");
    await opener.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("receipt-drawer")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("receipt-drawer")).toHaveCount(0);
    await expect(opener).toBeFocused();
  });

  test("the page never scrolls sideways at 375px", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 780 });
    await open(page, "rm_tamil_nadu");
    await ask(page, J1_TA);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
