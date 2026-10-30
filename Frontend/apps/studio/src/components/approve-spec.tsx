import { Button } from "@kehora/ui";
import { useMutation } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useState } from "react";

import { unwrap, useApi } from "../api";

export function ApproveSpec({ runId }: { runId: string }) {
  const { client } = useApi();
  // One key per decision so a retried click is replayed, not applied twice.
  const [key] = useState(() => crypto.randomUUID());
  const decide = useMutation({
    mutationFn: async (decision: "approve" | "reject") =>
      unwrap(
        await client.POST("/v1/runs/{run_id}/approvals/{gate}", {
          params: { path: { run_id: runId, gate: "spec" }, header: { "Idempotency-Key": `${key}:${decision}` } },
          body: { decision },
        }),
      ),
  });

  return (
    <div className="flex flex-col gap-2 rounded-md border border-warning/50 bg-warning/10 p-3">
      <p className="text-sm">Does this spec describe what you want? Approving starts the build.</p>
      <div className="flex gap-2">
        <Button
          data-testid="approve-spec"
          onClick={() => decide.mutate("approve")}
          disabled={decide.isPending || decide.isSuccess}
        >
          <Check aria-hidden /> {decide.isSuccess && decide.variables === "approve" ? "Approved" : "Approve spec"}
        </Button>
        <Button
          variant="outline"
          onClick={() => decide.mutate("reject")}
          disabled={decide.isPending || decide.isSuccess}
        >
          <X aria-hidden /> Reject
        </Button>
      </div>
      {decide.error && <p className="text-sm text-destructive">{decide.error.message}</p>}
    </div>
  );
}
