import { describe, it, expect, vi, beforeEach } from "vitest";
import { runEnsureSessionBeforeSubmit } from "./index";

describe("runEnsureSessionBeforeSubmit", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("does nothing when no guard is registered", async () => {
    await expect(runEnsureSessionBeforeSubmit()).resolves.toBeUndefined();
  });
});
