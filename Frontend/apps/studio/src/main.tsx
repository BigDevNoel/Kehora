import "./styles.css";

import { ClerkProvider } from "@clerk/react";
import * as Sentry from "@sentry/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { ApiProvider } from "./api";
import { env } from "./env";
import { router } from "./router";

if (env.sentryDsn) {
  Sentry.init({ dsn: env.sentryDsn, environment: import.meta.env.MODE });
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, retry: 1 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Sentry.ErrorBoundary fallback={<p className="p-6">Something went wrong. Reload the page.</p>}>
      <ClerkProvider
        publishableKey={env.clerkPublishableKey}
        signInUrl="/sign-in"
        afterSignOutUrl="/sign-in"
      >
        <ApiProvider>
          <QueryClientProvider client={queryClient}>
            <RouterProvider router={router} />
          </QueryClientProvider>
        </ApiProvider>
      </ClerkProvider>
    </Sentry.ErrorBoundary>
  </StrictMode>,
);
