import type { Project } from "@kehora/api-client";
import { Badge, Button, Card, CardDescription, CardHeader, CardTitle, Textarea } from "@kehora/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Sparkles } from "lucide-react";
import { type FormEvent, useState } from "react";

import { unwrap, useApi } from "../api";

const STATUS_VARIANT = {
  queued: "outline",
  running: "secondary",
  awaiting_approval: "warning",
  succeeded: "success",
  failed: "destructive",
  cancelled: "outline",
} as const;

function NewProject() {
  const { client } = useApi();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [prompt, setPrompt] = useState("");
  const [key, setKey] = useState(() => crypto.randomUUID());

  const create = useMutation({
    mutationFn: async (text: string) =>
      unwrap(
        await client.POST("/v1/projects", {
          params: { header: { "Idempotency-Key": key } },
          body: { prompt: text },
        }),
      ),
    onSuccess: async (data) => {
      setKey(crypto.randomUUID());
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      await navigate({ to: "/projects/$projectId", params: { projectId: data.project.id } });
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (prompt.trim()) create.mutate(prompt.trim());
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2" aria-label="New project">
      <label htmlFor="prompt" className="text-lg font-semibold">
        What do you want to make?
      </label>
      <Textarea
        id="prompt"
        name="prompt"
        data-testid="prompt"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="A desk stand for my phone that holds it at 60°, printable in PLA"
        rows={3}
        maxLength={4000}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
        }}
      />
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">You'll review a written spec before anything is built.</p>
        <Button type="submit" data-testid="create-project" disabled={!prompt.trim() || create.isPending}>
          <Sparkles aria-hidden /> {create.isPending ? "Starting…" : "Design it"}
        </Button>
      </div>
      {create.error && <p className="text-sm text-destructive">{create.error.message}</p>}
    </form>
  );
}

function ProjectRow({ project }: { project: Project }) {
  const status = project.latest_run?.status;
  return (
    <Link to="/projects/$projectId" params={{ projectId: project.id }} className="block">
      <Card className="transition-colors hover:bg-accent/40">
        <CardHeader className="flex-row items-center justify-between gap-2">
          <div className="min-w-0">
            <CardTitle className="truncate text-base">{project.title}</CardTitle>
            <CardDescription>
              {new Date(project.created_at).toLocaleString()} {project.kind ? `· ${project.kind}` : ""}
            </CardDescription>
          </div>
          {status && <Badge variant={STATUS_VARIANT[status]}>{status.replace("_", " ")}</Badge>}
        </CardHeader>
      </Card>
    </Link>
  );
}

export function ProjectsPage() {
  const { client } = useApi();
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: async () => unwrap(await client.GET("/v1/projects", { params: { query: { limit: 50 } } })),
  });

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-8">
      <NewProject />
      <section aria-label="Your projects" className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-muted-foreground">Your projects</h2>
        {projects.isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
        {projects.error && <p className="text-sm text-destructive">{projects.error.message}</p>}
        {projects.data?.items.length === 0 && (
          <p className="text-sm text-muted-foreground">No projects yet. Describe something above.</p>
        )}
        <div data-testid="project-list" className="flex flex-col gap-2">
          {projects.data?.items.map((p) => <ProjectRow key={p.id} project={p} />)}
        </div>
      </section>
    </div>
  );
}
