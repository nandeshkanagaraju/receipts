import { expect, test } from "@playwright/test";

/** Committed screenshots of the tour: step 1 and step 2, the receipt. */
for (const step of [1, 2, 5]) {
  test(`tour step ${step}`, async ({ page }, info) => {
    const width = info.project.name === "mobile" ? 375 : 1280;
    await page.goto("/?role=rm_tamil_nadu");
    await expect(page.getByTestId("tour-caption")).toBeVisible({ timeout: 40_000 });
    for (let i = 1; i < step; i += 1) await page.getByTestId("tour-next").click();
    await expect(page.getByTestId("tour-caption")).toHaveAttribute("data-step", String(step));
    // Clicking through the steps leaves focus wherever the last click put it,
    // and the focus ring lands in the PNG — two runs of step 2 differed in 4.5%
    // of their pixels over a ring nobody meant to photograph. Drop focus first.
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    await page.screenshot({ path: `../docs/screens/tour-${width}-step${step}.png` });
  });
}
