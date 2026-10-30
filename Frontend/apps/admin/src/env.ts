function required(name: string, value: string | undefined): string {
  if (!value) throw new Error(`${name} is not set; see .env.example`);
  return value;
}

export const env = {
  apiUrl: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
  clerkPublishableKey: required(
    "VITE_CLERK_PUBLISHABLE_KEY",
    import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
  ),
  sentryDsn: import.meta.env.VITE_SENTRY_DSN || undefined,
};
