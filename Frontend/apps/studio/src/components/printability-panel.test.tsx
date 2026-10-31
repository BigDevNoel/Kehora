// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { report } from "../lib/test-reports";
import { PrintabilityPanel } from "./printability-panel";

afterEach(cleanup);

describe("PrintabilityPanel", () => {
  it("shows a clean part as ready to print", () => {
    render(<PrintabilityPanel status="pass" report={report()} />);
    expect(screen.getByTestId("printability-verdict").textContent).toBe("Ready to print");
    expect(screen.getByText("40 × 30 × 10 mm")).toBeTruthy();
    expect(screen.getByText("2.4 mm")).toBeTruthy();
    expect(screen.getByText("No problems found.")).toBeTruthy();
  });

  it("lists blocking issues with their suggested fixes", () => {
    const failing = report({
      blocking: true,
      as_given: { ...report().as_given, fits_bed: false },
      issues: [
        {
          code: "exceeds_bed",
          severity: "error",
          message: "It does not fit this printer as placed, but it fits if reoriented.",
          fixes: ["reorient", "split_for_bed"],
        },
      ],
    });
    render(<PrintabilityPanel status="fail" report={failing} />);
    expect(screen.getByTestId("printability-verdict").textContent).toBe("Not printable yet");
    const issues = screen.getByTestId("printability-issues");
    expect(within(issues).getByText(/does not fit this printer/)).toBeTruthy();
    expect(within(issues).getByText("Reorient")).toBeTruthy();
    expect(within(issues).getByText("Split for the bed")).toBeTruthy();
    expect(within(issues).getByLabelText("Error")).toBeTruthy();
  });

  it("says when the part only fits turned on the bed", () => {
    const turned = report({ as_given: { ...report().as_given, rotate_z_90: true } });
    render(<PrintabilityPanel status="pass" report={turned} />);
    expect(screen.getByText("Yes, turned 90°")).toBeTruthy();
  });
});
