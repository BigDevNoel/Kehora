import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

import { clerk } from "@clerk/testing/playwright";
import { expect, type Page } from "@playwright/test";

const REPO = resolve(import.meta.dirname, "../../..");

export async function signIn(page: Page) {
  await page.goto("/sign-in");
  await clerk.signIn({ page, emailAddress: process.env.E2E_CLERK_USER_EMAIL! });
  await page.goto("/projects");
  await expect(page.getByText(/what do you want to make/i)).toBeVisible();
}

/** Create a project from the prompt box and land in the studio. */
export async function createProject(page: Page, prompt: string) {
  await page.getByTestId("prompt").fill(prompt);
  await page.getByTestId("create-project").click();
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("trigger-prompt")).toHaveText(prompt);
}

export function logEntry(page: Page, type: string) {
  return page.getByTestId("build-log").locator(`li[data-event-type="${type}"]`);
}

export async function expectSeqsStrictlyIncreasing(page: Page) {
  const seqs = await page
    .getByTestId("build-log")
    .locator("li[data-seq]")
    .evaluateAll((els) => els.map((el) => Number(el.getAttribute("data-seq"))));
  expect(seqs.length).toBeGreaterThan(0);
  expect(seqs).toEqual([...new Set(seqs)].sort((a, b) => a - b));
}

export function compose(...args: string[]) {
  execFileSync("docker", ["compose", ...args], { cwd: REPO, stdio: "pipe" });
}
