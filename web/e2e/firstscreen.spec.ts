import { expect, test } from "@playwright/test";

/** The first screen, untouched — what a reviewer sees before doing anything.
 *  Committed to docs/screens/ because the first screen is the thing that was
 *  wrong, and a screenshot is what found both of the layout defects. */
const ROLES = ["rm_tamil_nadu", "global_finance", "store_ops_uk", "admin"];

for (const role of ROLES) {
  test(`first screen ${role}`, async ({ page }, info) => {
    const width = info.project.name === "mobile" ? 375 : 1280;
    // The tour auto-starts on a first visit and its overlay intercepts clicks.
    // Every spec that navigates directly has to opt out, or it tests the tour.
    await page.addInitScript(() => window.localStorage.setItem("receipts.tour.v1", "1"));
    await page.goto(`/?role=${role}`);
    await expect(page.getByTestId("receipt-card")).toBeVisible({ timeout: 40_000 });
    await expect(page.getByTestId("catalog-metric-row").first()).toBeVisible();
    await page.screenshot({ path: `../docs/screens/first-${width}-${role}.png`, fullPage: true });
  });
}
