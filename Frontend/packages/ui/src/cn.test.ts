import { describe, expect, it } from "vitest";

import { cn } from "./cn";

describe("cn", () => {
  it("merges conflicting tailwind classes, last wins", () => {
    const hidden: string | false = false;
    expect(cn("px-2 text-sm", hidden, "px-4")).toBe("text-sm px-4");
  });
});
