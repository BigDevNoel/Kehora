import "./styles.css";

import { ClerkProvider } from "@clerk/react";
import * as Sentry from "@sentry/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { ApiProvider } from "./api";
import { App } from "./app";
import { env } from "./env";

if (env.sentryDsn) {
  Sentry.init({ dsn: env.sentryDsn, environment: import.meta.env.MODE });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Sentry.ErrorBoundary fallback={<p className="p-6">Something went wrong. Reload the page.</p>}>
      <ClerkProvider publishableKey={env.clerkPublishableKey}>
        <ApiProvider>
          <QueryClientProvider client={new QueryClient()}>
            <App />
          </QueryClientProvider>
        </ApiProvider>
      </ClerkProvider>
    </Sentry.ErrorBoundary>
  </StrictMode>,
);
