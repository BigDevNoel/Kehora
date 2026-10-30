import type { ProjectSpec } from "@kehora/types";
import { Button, Tabs, TabsContent, TabsList, TabsTrigger } from "@kehora/ui";
import { ViewerPlaceholder } from "@kehora/viewer";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText } from "lucide-react";

import { unwrap, useApi } from "../api";
import { ApproveSpec } from "../components/approve-spec";
import { BuildLog } from "../components/build-log";
import { SpecCard } from "../components/spec-card";
import { useRunEvents } from "../lib/use-run-events";

// One render for both layouts: tabs below 768px, three columns from md up.
const PANEL =
  "min-h-0 flex-col gap-3 overflow-y-auto p-3 data-[state=active]:flex data-[state=inactive]:hidden md:data-[state=inactive]:flex md:flex md:border-r last:border-r-0";

export function StudioPage({ projectId }: { projectId: string }) {
  const { client } = useApi();
  const queryClient = useQueryClient();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: async () =>
      unwrap(await client.GET("/v1/projects/{project_id}", { params: { path: { project_id: projectId } } })),
  });
  const run = project.data?.runs[0];
  const log = useRunEvents(run?.id, () =>
    queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  );

  async function download(artifactId: string) {
    const res = unwrap(
      await client.GET("/v1/artifacts/{artifact_id}/download", {
        params: { path: { artifact_id: artifactId } },
      }),
    );
    window.open(res.url, "_blank", "noopener");
  }

  if (project.isPending) return <p className="p-6 text-sm text-muted-foreground">Loading project…</p>;
  if (project.error) return <p className="p-6 text-sm text-destructive">{project.error.message}</p>;

  const version = project.data.current_version;
  const spec = (version?.spec as ProjectSpec | undefined) ?? log.pendingSpec;

  return (
    <Tabs defaultValue="build" className="flex min-h-0 flex-1 flex-col">
      <div className="border-b px-3 py-2 md:hidden">
        <TabsList className="w-full">
          <TabsTrigger value="build" className="flex-1">Chat & log</TabsTrigger>
          <TabsTrigger value="viewer" className="flex-1">Viewer</TabsTrigger>
          <TabsTrigger value="props" className="flex-1">Properties</TabsTrigger>
        </TabsList>
      </div>
      <div className="grid min-h-0 flex-1 md:grid-cols-[minmax(300px,1fr)_2fr_minmax(260px,1fr)]">
        <TabsContent value="build" forceMount className={PANEL}>
          <div className="rounded-md bg-muted/50 p-3 text-sm">
            <span className="text-xs font-semibold text-muted-foreground">You asked</span>
            <p data-testid="trigger-prompt" className="whitespace-pre-wrap">{run?.trigger_prompt}</p>
          </div>
          {log.awaitingApproval && log.pendingSpec && run && (
            <>
              <SpecCard spec={log.pendingSpec} />
              <ApproveSpec key={run.id} runId={run.id} />
            </>
          )}
          <BuildLog log={log} />
        </TabsContent>

        <TabsContent value="viewer" forceMount className={PANEL}>
          <h1 className="text-lg font-semibold" data-testid="project-title">{project.data.title}</h1>
          <ViewerPlaceholder title="3D viewer" />
        </TabsContent>

        <TabsContent value="props" forceMount className={PANEL}>
          <h2 className="text-sm font-semibold">Spec</h2>
          {spec ? <SpecCard spec={spec} /> : <p className="text-sm text-muted-foreground">No spec yet.</p>}
          <h2 className="text-sm font-semibold">Files</h2>
          {version?.artifacts.length ? (
            <ul data-testid="artifact-list" className="flex flex-col gap-1">
              {version.artifacts.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-2 rounded-md border p-2 text-sm">
                  <span className="flex items-center gap-2">
                    <FileText className="size-4 text-muted-foreground" aria-hidden />
                    {a.type}.{a.format} <span className="text-xs text-muted-foreground">{a.size} B</span>
                  </span>
                  <Button size="icon" variant="ghost" aria-label={`Download ${a.type}`} onClick={() => download(a.id)}>
                    <Download aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Files appear here when the build produces them.</p>
          )}
        </TabsContent>
      </div>
    </Tabs>
  );
}
