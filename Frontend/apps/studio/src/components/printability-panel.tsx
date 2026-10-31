import type { PrintabilityReport } from "@kehora/types";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@kehora/ui";
import { formatMm, formatSize } from "@kehora/viewer/geometry";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

import { FIX_LABELS, orientationHint } from "../lib/artifacts";

const VERDICT = {
  pass: { label: "Ready to print", variant: "success" },
  warn: { label: "Printable, with warnings", variant: "warning" },
  fail: { label: "Not printable yet", variant: "destructive" },
} as const;

export function PrintabilityPanel({ status, report }: { status: string; report: PrintabilityReport }) {
  const verdict = VERDICT[status as keyof typeof VERDICT] ?? VERDICT.fail;
  const given = report.as_given;
  const hint = orientationHint(report);
  const facts: [string, string][] = [
    ["Size", formatSize(given.size_mm)],
    ["Fits the bed", given.fits_bed ? (given.rotate_z_90 ? "Yes, turned 90°" : "Yes") : "No"],
    ["Thinnest wall", report.min_wall_mm == null ? "Not measured" : formatMm(report.min_wall_mm)],
    ["Overhang needing support", `${Math.round(given.overhang_area_mm2)} mm²`],
    ["Touching the bed", `${Math.round(given.bed_contact_area_mm2)} mm²`],
  ];

  return (
    <Card data-testid="printability">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>Printability</CardTitle>
          <Badge variant={verdict.variant} data-testid="printability-verdict">
            {verdict.label}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {report.printer_id} · {report.material_id.toUpperCase()}
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          {facts.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="text-right">{value}</dd>
            </div>
          ))}
        </dl>
        {hint && <p className="text-sm">{hint}</p>}
        {report.issues.length > 0 ? (
          <ul className="flex flex-col gap-2" data-testid="printability-issues">
            {report.issues.map((issue) => (
              <li key={issue.code} className="rounded-md border p-2 text-sm">
                <p className="flex items-start gap-2">
                  {issue.severity === "error" ? (
                    <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-label="Error" />
                  ) : (
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-label="Warning" />
                  )}
                  <span>{issue.message}</span>
                </p>
                {(issue.fixes?.length ?? 0) > 0 && (
                  <p className="mt-1.5 flex flex-wrap items-center gap-1 pl-6 text-xs text-muted-foreground">
                    Suggested fix:
                    {issue.fixes?.map((fix) => (
                      <Badge key={fix} variant="outline">
                        {FIX_LABELS[fix]}
                      </Badge>
                    ))}
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="flex items-center gap-2 text-sm">
            <CheckCircle2 className="size-4 text-success" aria-hidden /> No problems found.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
