import { expect, test } from "@playwright/test";

import { createProject, expectSeqsStrictlyIncreasing, logEntry, signIn } from "./helpers";

test("sign in, create a project, watch events, approve the spec, see the run finish", async ({ page }) => {
  await signIn(page);
  await createProject(page, `A desk stand for my phone (e2e ${Date.now()})`);

  // Events stream into the build log while the agents work.
  await expect(logEntry(page, "run_started")).toBeVisible();
  await expect(logEntry(page, "node_started").first()).toBeVisible();

  // Approval gate 1: the spec is shown with an approve button.
  await expect(logEntry(page, "needs_approval")).toBeVisible();
  await expect(page.getByTestId("spec-card").first()).toBeVisible();
  await page.getByTestId("approve-spec").click();

  await expect(logEntry(page, "check_passed")).toBeVisible({ timeout: 90_000 });
  await expect(logEntry(page, "run_finished")).toBeVisible({ timeout: 90_000 });
  await expect(logEntry(page, "run_failed")).toHaveCount(0);
  await expectSeqsStrictlyIncreasing(page);

  // The finished version and its file are shown on the properties panel.
  await expect(page.getByTestId("artifact-list")).toBeVisible();
});
