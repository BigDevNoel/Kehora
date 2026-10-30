import { RedirectToSignIn, Show, SignIn, UserButton } from "@clerk/react";
import {
  createRootRoute,
  createRoute,
  createRouter,
  Link,
  Outlet,
  redirect,
} from "@tanstack/react-router";
import type { ReactNode } from "react";

import { ProjectsPage } from "./pages/projects";
import { StudioPage } from "./pages/studio";

function RequireAuth({ children }: { children: ReactNode }) {
  return (
    <>
      <Show when="signed-in">{children}</Show>
      <Show when="signed-out">
        <RedirectToSignIn />
      </Show>
    </>
  );
}

function Shell() {
  return (
    <div className="flex h-dvh flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <Link to="/projects" className="flex items-center gap-2 font-semibold tracking-tight">
          <span aria-hidden className="grid size-6 place-items-center rounded bg-primary text-xs text-primary-foreground">K</span>
          Kehora Studio
        </Link>
        <Show when="signed-in">
          <UserButton />
        </Show>
      </header>
      <main className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  );
}

const rootRoute = createRootRoute({ component: Shell });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/projects" });
  },
});

const signInRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sign-in/$",
  component: () => (
    <div className="grid flex-1 place-items-center p-4">
      <SignIn routing="path" path="/sign-in" fallbackRedirectUrl="/projects" />
    </div>
  ),
});

const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects",
  component: () => (
    <RequireAuth>
      <ProjectsPage />
    </RequireAuth>
  ),
});

const projectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/$projectId",
  component: function ProjectRoute() {
    const { projectId } = projectRoute.useParams();
    return (
      <RequireAuth>
        <StudioPage key={projectId} projectId={projectId} />
      </RequireAuth>
    );
  },
});

const routeTree = rootRoute.addChildren([indexRoute, signInRoute, projectsRoute, projectRoute]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
