import { clerkSetup } from "@clerk/testing/playwright";

export default async function globalSetup() {
  // @clerk/testing reads CLERK_PUBLISHABLE_KEY; the apps use the VITE_ name.
  process.env.CLERK_PUBLISHABLE_KEY ??= process.env.VITE_CLERK_PUBLISHABLE_KEY;
  await clerkSetup();
}
