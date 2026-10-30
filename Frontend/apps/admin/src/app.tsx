import { RedirectToSignIn, Show, UserButton } from "@clerk/react";
import { Badge, Button, Tabs, TabsContent, TabsList, TabsTrigger } from "@kehora/ui";
import { useInfiniteQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import type { KehoraClient, Schemas } from "@kehora/api-client";

import { useApi } from "./api";

interface PageOf<T> {
  items: T[];
  next_cursor: string | null;
}
type Fetcher<T> = (client: KehoraClient, cursor: string | undefined) => Promise<{ data?: PageOf<T>; response: Response }>;

interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
}

class ForbiddenError extends Error {}

function AdminTable<T extends { id: string }>({
  name,
  fetchPage,
  columns,
}: {
  name: string;
  fetchPage: Fetcher<T>;
  columns: Column<T>[];
}) {
  const { client } = useApi();
  const query = useInfiniteQuery({
    queryKey: ["admin", name],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const res = await fetchPage(client, pageParam);
      if (res.response.status === 403) throw new ForbiddenError("Staff only");
      if (!res.data) throw new Error(`${res.response.status}`);
      return res.data;
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: (count, err) => !(err instanceof ForbiddenError) && count < 1,
  });

  if (query.error instanceof ForbiddenError) {
    return (
      <p data-testid="forbidden" className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm">
        This console is for Kehora staff. Ask an admin to set your role in Clerk (public metadata
        <code className="mx-1">{'{"role": "support"}'}</code>).
      </p>
    );
  }
  if (query.error) return <p className="text-sm text-destructive">{query.error.message}</p>;
  if (query.isPending) return <p className="text-sm text-muted-foreground">Loading…</p>;

  const rows = query.data.pages.flatMap((p) => p.items);
  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
            <tr>
              {columns.map((c) => (
                <th key={c.header} className="px-3 py-2 font-medium">{c.header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t">
                {columns.map((c) => (
                  <td key={c.header} className="px-3 py-2 align-top">{c.cell(row)}</td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-6 text-center text-muted-foreground">Nothing yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {query.hasNextPage && (
        <Button variant="outline" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>
          Load more
        </Button>
      )}
    </div>
  );
}

const when = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : "—");
const mono = (s: string) => <code className="text-xs">{s.slice(0, 8)}</code>;

type UserRow = Schemas["AdminUser"];
type ProjectRow = Schemas["AdminProject"];
type RunRow = Schemas["AdminRun"];
const q = (cursor: string | undefined) => ({ params: { query: { limit: 50, cursor } } });

export function App() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4 p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Kehora Admin</h1>
        <Show when="signed-in"><UserButton /></Show>
      </header>
      <Show when="signed-out"><RedirectToSignIn /></Show>
      <Show when="signed-in">
        <Tabs defaultValue="users" className="flex flex-col gap-4">
          <TabsList className="self-start">
            <TabsTrigger value="users">Users</TabsTrigger>
            <TabsTrigger value="projects">Projects</TabsTrigger>
            <TabsTrigger value="runs">Runs</TabsTrigger>
          </TabsList>
          <TabsContent value="users">
            <AdminTable<UserRow>
              name="users"
              fetchPage={(c, cursor) => c.GET("/v1/admin/users", q(cursor))}
              columns={[
                { header: "Id", cell: (u) => mono(u.id) },
                { header: "Email", cell: (u) => u.email ?? "—" },
                { header: "Name", cell: (u) => u.name ?? "—" },
                { header: "Role", cell: (u) => <Badge variant={u.role === "user" ? "outline" : "default"}>{u.role}</Badge> },
                { header: "Created", cell: (u) => when(u.created_at) },
                { header: "Deleted", cell: (u) => when(u.deleted_at) },
              ]}
            />
          </TabsContent>
          <TabsContent value="projects">
            <AdminTable<ProjectRow>
              name="projects"
              fetchPage={(c, cursor) => c.GET("/v1/admin/projects", q(cursor))}
              columns={[
                { header: "Id", cell: (p) => mono(p.id) },
                { header: "Title", cell: (p) => p.title },
                { header: "Kind", cell: (p) => p.kind ?? "—" },
                { header: "Visibility", cell: (p) => p.visibility },
                { header: "Org", cell: (p) => mono(p.org_id) },
                { header: "Created", cell: (p) => when(p.created_at) },
              ]}
            />
          </TabsContent>
          <TabsContent value="runs">
            <AdminTable<RunRow>
              name="runs"
              fetchPage={(c, cursor) => c.GET("/v1/admin/runs", q(cursor))}
              columns={[
                { header: "Id", cell: (r) => mono(r.id) },
                { header: "Project", cell: (r) => mono(r.project_id) },
                { header: "Status", cell: (r) => <Badge variant="secondary">{r.status}</Badge> },
                { header: "Cost", cell: (r) => `${(r.cost_minor / 100).toFixed(2)} ${r.cost_currency}` },
                { header: "Error", cell: (r) => <span className="line-clamp-2 max-w-xs">{r.error ?? "—"}</span> },
                { header: "Created", cell: (r) => when(r.created_at) },
                { header: "Finished", cell: (r) => when(r.finished_at) },
              ]}
            />
          </TabsContent>
        </Tabs>
      </Show>
    </div>
  );
}
