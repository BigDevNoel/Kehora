import { useAuth } from "@clerk/react";
import { createKehoraClient, type KehoraClient, type TokenGetter } from "@kehora/api-client";
import { createContext, type ReactNode, useContext, useMemo } from "react";

import { env } from "./env";

interface ApiContextValue {
  client: KehoraClient;
  getToken: TokenGetter;
}

const ApiContext = createContext<ApiContextValue | null>(null);

export function ApiProvider({ children }: { children: ReactNode }) {
  const { getToken } = useAuth();
  const value = useMemo(() => {
    const tokenGetter: TokenGetter = () => getToken();
    return { client: createKehoraClient(env.apiUrl, tokenGetter), getToken: tokenGetter };
  }, [getToken]);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiContextValue {
  const ctx = useContext(ApiContext);
  if (!ctx) throw new Error("useApi must be used inside <ApiProvider>");
  return ctx;
}

/** Throw a readable error for non-2xx openapi-fetch results. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data === undefined) {
    const detail =
      typeof result.error === "object" && result.error && "detail" in result.error
        ? String((result.error as { detail: unknown }).detail)
        : result.response.statusText;
    throw new Error(`${result.response.status}: ${detail}`);
  }
  return result.data;
}
