import { expect, test, type Page } from "@playwright/test";

/** The guided tour. This replaces the demo video, so it has to work on a first
 *  visit, on a phone, and from the keyboard alone. */
const STEPS = 7;

/** A genuine first visit: nothing in localStorage. */
async function firstVisit(page: Page, role = "rm_tamil_nadu"): Promise<void> {
  await page.goto(`/?role=${role}`);
}

test("it starts by itself on a first visit and walks every step", async ({ page }) => {
  await firstVisit(page);
  const caption = page.getByTestId("tour-caption");
  await expect(caption).toBeVisible({ timeout: 40_000 });
  await expect(caption).toHaveAttribute("data-step", "1");

  for (let step = 1; step <= STEPS; step += 1) {
    await expect(caption).toHaveAttribute("data-step", String(step));
    // Every step lights something: a spotlight with a real rectangle.
    const spotlight = page.getByTestId("tour-spotlight");
    await expect(spotlight).toBeVisible();
    const box = await spotlight.boundingBox();
    expect(box, `step ${step} has no spotlight`).not.toBeNull();
    expect(box!.width, `step ${step} spotlight is empty`).toBeGreaterThan(8);
    expect(box!.height, `step ${step} spotlight is empty`).toBeGreaterThan(8);
    // And says something.
    expect((await caption.innerText()).length).toBeGreaterThan(40);
    await page.getByTestId("tour-next").click();
  }

  // The last Next finishes it.
  await expect(page.getByTestId("tour")).toHaveCount(0);
});

test("it is remembered, and the header control replays it", async ({ page }) => {
  await firstVisit(page);
  await expect(page.getByTestId("tour-caption")).toBeVisible({ timeout: 40_000 });
  await page.getByTestId("tour-skip").click();
  await expect(page.getByTestId("tour")).toHaveCount(0);

  // Reload: it does not come back.
  await page.reload();
  await expect(page.getByTestId("answer-canvas")).toBeVisible({ timeout: 40_000 });
  await expect(page.getByTestId("tour")).toHaveCount(0);

  // But the control replays it, from the first step.
  await page.getByTestId("take-tour").click();
  await expect(page.getByTestId("tour-caption")).toHaveAttribute("data-step", "1");
});

test("Skip ends it", async ({ page }) => {
  await firstVisit(page);
  await expect(page.getByTestId("tour-caption")).toBeVisible({ timeout: 40_000 });
  await page.getByTestId("tour-skip").click();
  await expect(page.getByTestId("tour")).toHaveCount(0);
});

test("Escape ends it", async ({ page }) => {
  await firstVisit(page);
  await expect(page.getByTestId("tour-caption")).toBeVisible({ timeout: 40_000 });
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("tour")).toHaveCount(0);
});

test("clicking outside the spotlight ends it", async ({ page }) => {
  await firstVisit(page);
  await expect(page.getByTestId("tour-caption")).toBeVisible({ timeout: 40_000 });
  // Top-left corner: always dimmed backdrop on step 1, never the spotlight.
  await page.mouse.click(4, 4);
  await expect(page.getByTestId("tour")).toHaveCount(0);
});

test("the keyboard alone can walk it: Enter, arrow, Escape", async ({ page }) => {
  await firstVisit(page);
  const caption = page.getByTestId("tour-caption");
  await expect(caption).toBeVisible({ timeout: 40_000 });

  // Focus follows the step, so the caption is what a screen reader lands on.
  await expect(caption).toBeFocused();

  await page.keyboard.press("Enter");
  await expect(caption).toHaveAttribute("data-step", "2");
  await expect(caption).toBeFocused();

  await page.keyboard.press("ArrowRight");
  await expect(caption).toHaveAttribute("data-step", "3");

  await page.keyboard.press("Escape");
  await expect(page.getByTestId("tour")).toHaveCount(0);
});

test("the receipt step is the longest caption, because it is the point", async ({ page }) => {
  await firstVisit(page);
  const caption = page.getByTestId("tour-caption");
  await expect(caption).toBeVisible({ timeout: 40_000 });
  const lengths: number[] = [];
  for (let step = 1; step <= STEPS; step += 1) {
    lengths.push((await caption.innerText()).length);
    await page.getByTestId("tour-next").click();
  }
  console.log(`caption lengths: ${lengths.join(", ")}`);
  const longest = lengths.indexOf(Math.max(...lengths));
  expect(longest, "step 2, the receipt, should carry the longest caption").toBe(1);
});

test("it works at 375px without scrolling the page sideways", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await firstVisit(page);
  await expect(page.getByTestId("tour-caption")).toBeVisible({ timeout: 40_000 });
  for (let step = 1; step <= STEPS; step += 1) {
    const caption = await page.getByTestId("tour-caption").boundingBox();
    expect(caption!.x, `step ${step} caption starts off-screen`).toBeGreaterThanOrEqual(-1);
    expect(caption!.x + caption!.width, `step ${step} caption runs off-screen`).toBeLessThanOrEqual(376);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `step ${step} scrolls sideways`).toBeLessThanOrEqual(0);
    await page.getByTestId("tour-next").click();
  }
});

test("the tour has no animated transitions", async ({ page }) => {
  await firstVisit(page);
  await expect(page.getByTestId("tour-caption")).toBeVisible({ timeout: 40_000 });
  for (const id of ["tour-caption", "tour-spotlight"]) {
    const moving = await page.getByTestId(id).evaluate((el) => {
      const style = getComputedStyle(el);
      return { transition: style.transitionDuration, animation: style.animationDuration };
    });
    console.log(`${id}: transition=${moving.transition} animation=${moving.animation}`);
    expect(moving.transition === "0s" || moving.transition === "").toBeTruthy();
    expect(moving.animation === "0s" || moving.animation === "").toBeTruthy();
  }
});

test("the caption never covers the thing it is describing", async ({ page }) => {
  // A screenshot caught the receipt step with its caption sitting on top of the
  // metric name and definition -- the exact thing the caption tells you to look
  // at. The receipt is nearly full-height, so neither above nor below fits and
  // the caption has to go beside it.
  await firstVisit(page);
  const caption = page.getByTestId("tour-caption");
  await expect(caption).toBeVisible({ timeout: 40_000 });

  for (let step = 1; step <= STEPS; step += 1) {
    const c = await caption.boundingBox();
    const s = await page.getByTestId("tour-spotlight").boundingBox();
    expect(c && s, `step ${step} missing a box`).toBeTruthy();
    const overlapX = Math.max(0, Math.min(c!.x + c!.width, s!.x + s!.width) - Math.max(c!.x, s!.x));
    const overlapY = Math.max(0, Math.min(c!.y + c!.height, s!.y + s!.height) - Math.max(c!.y, s!.y));
    const overlap = overlapX * overlapY;
    const spotlightArea = s!.width * s!.height;
    const share = spotlightArea > 0 ? overlap / spotlightArea : 0;
    console.log(`step ${step}: caption covers ${(share * 100).toFixed(1)}% of the spotlight`);
    // A phone cannot always avoid it; a desktop always can.
    const allowed = page.viewportSize()!.width < 500 ? 0.5 : 0.02;
    expect(share, `step ${step} caption covers the spotlight`).toBeLessThanOrEqual(allowed);
    await page.getByTestId("tour-next").click();
  }
});
