import { expect, test } from "@playwright/test";

/** Committed screenshots of the tour: step 1 and step 2, the receipt. */
for (const step of [1, 2, 5]) {
  test(`tour step ${step}`, async ({ page }, info) => {
    const width = info.project.name === "mobile" ? 375 : 1280;
    await page.goto("/?role=rm_tamil_nadu");
    await expect(page.getByTestId("tour-caption")).toBeVisible({ timeout: 40_000 });
    for (let i = 1; i < step; i += 1) await page.getByTestId("tour-next").click();
    await expect(page.getByTestId("tour-caption")).toHaveAttribute("data-step", String(step));
    await page.screenshot({ path: `../docs/screens/tour-${width}-step${step}.png` });
  });
}
