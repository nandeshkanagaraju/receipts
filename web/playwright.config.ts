import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

/** The interpreter that has `receipts` installed.
 *
 *  Locally that is the project venv; in CI the package is installed into the
 *  runner's own Python and there is no venv, which is how this config first
 *  failed -- exit code 127 from a path that exists on one machine only. */
const PYTHON = existsSync("../.venv/bin/python") ? "../.venv/bin/python" : "python";

/** The real API, in replay mode, with a fixed as_of. No network (D9): the model
 *  responses come from eval/recordings/receipts and the warehouse is the local
 *  DuckDB file. */
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1, // The demo rate limit is 20 questions a minute, per role AND per IP.
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8011",
    trace: "off",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile",
      use: { ...devices["Desktop Chrome"], viewport: { width: 375, height: 780 } },
    },
  ],
  webServer: {
    command: `cd .. && RECEIPTS_LLM_MODE=replay ${PYTHON.replace("../", "")} -m uvicorn --factory receipts.api.app:create_app --host 127.0.0.1 --port 8011`,
    url: "http://127.0.0.1:8011/healthz",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
