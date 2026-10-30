import { expect, test } from "@playwright/test";

import { compose, createProject, expectSeqsStrictlyIncreasing, logEntry, signIn } from "./helpers";

// `make e2e` runs the worker with ECHO_DELAY_S so the engine node is slow enough to interrupt.
test("the run finishes after the worker is killed and restarted mid-run", async ({ page }) => {
  await signIn(page);
  await createProject(page, `A cable clip for a desk edge (resume e2e ${Date.now()})`);

  await expect(logEntry(page, "needs_approval")).toBeVisible();
  await page.getByTestId("approve-spec").click();

  // Wait until the engine node is running inside the sandbox, then kill the worker.
  await expect(
    page.getByTestId("build-log").getByText("Running the engine in a sandbox…").first(),
  ).toBeVisible({ timeout: 60_000 });
  compose("kill", "worker");
  await expect(logEntry(page, "run_finished")).toHaveCount(0);
  compose("start", "worker");

  // The same open page keeps streaming: the run resumes from its checkpoint and finishes once.
  await expect(logEntry(page, "run_finished")).toHaveCount(1, { timeout: 120_000 });
  await expect(logEntry(page, "run_failed")).toHaveCount(0);
  await expectSeqsStrictlyIncreasing(page);
});
