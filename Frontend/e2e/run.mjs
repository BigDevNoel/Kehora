// Runs the Playwright gate suite. Needs a Clerk dev instance (see .env.example).
// Locally, missing Clerk keys skip the suite with a loud warning; in CI they fail the build.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const envFile = resolve(import.meta.dirname, "../../.env");
if (existsSync(envFile)) process.loadEnvFile(envFile);

const required = ["VITE_CLERK_PUBLISHABLE_KEY", "CLERK_SECRET_KEY", "E2E_CLERK_USER_EMAIL"];
const missing = required.filter((k) => !process.env[k]);
if (missing.length) {
  const msg = `Playwright gate suite needs ${missing.join(", ")} (Clerk dev instance; see .env.example).`;
  if (process.env.CI) {
    console.error(`ERROR: ${msg}`);
    process.exit(1);
  }
  console.warn(`\n*** SKIPPED: ${msg}\n*** Phase 0 gate is NOT verified until these are set.\n`);
  process.exit(0);
}

const shell = process.platform === "win32";
const install = spawnSync("pnpm", ["exec", "playwright", "install", "chromium"], { stdio: "inherit", shell });
if (install.status !== 0) process.exit(install.status ?? 1);

const result = spawnSync("pnpm", ["exec", "playwright", "test", "--config", "e2e/playwright.config.ts", ...process.argv.slice(2)], {
  stdio: "inherit",
  shell,
});
process.exit(result.status ?? 1);
