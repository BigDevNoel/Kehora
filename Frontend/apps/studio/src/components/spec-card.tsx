import type { ProjectSpec } from "@kehora/types";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@kehora/ui";

export function SpecCard({ spec }: { spec: ProjectSpec }) {
  return (
    <Card data-testid="spec-card">
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>{spec.title}</CardTitle>
          <Badge variant="outline">{spec.kind}</Badge>
        </div>
        <CardDescription>{spec.summary}</CardDescription>
      </CardHeader>
      {(spec.requirements?.length ?? 0) > 0 && (
        <CardContent>
          <h4 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Requirements</h4>
          <ul className="list-disc space-y-0.5 pl-4 text-sm">
            {spec.requirements?.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </CardContent>
      )}
    </Card>
  );
}
