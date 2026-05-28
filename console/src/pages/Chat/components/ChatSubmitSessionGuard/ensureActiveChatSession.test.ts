import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  ensureActiveChatSession,
  isLocalTimestampSessionId,
} from "./ensureActiveChatSession";

interface CustomWindow extends Window {
  currentSessionId?: string;
}

declare const window: CustomWindow;

describe("isLocalTimestampSessionId", () => {
  it("detects numeric local ids", () => {
    expect(isLocalTimestampSessionId("1716880000123")).toBe(true);
    expect(isLocalTimestampSessionId("550e8400-e29b-41d4-a716-446655440000")).toBe(
      false,
    );
  });
});

describe("ensureActiveChatSession", () => {
  beforeEach(() => {
    window.currentSessionId = undefined;
  });

  it("creates session on welcome screen when only a stale backend session is selected", async () => {
    const createSession = vi.fn().mockResolvedValue("1716880000999");
    window.currentSessionId = "backend-uuid";
    await ensureActiveChatSession(
      createSession,
      () => "backend-uuid",
      0,
    );
    expect(createSession).toHaveBeenCalledOnce();
  });

  it("keeps fresh local new-chat session on welcome screen", async () => {
    const createSession = vi.fn();
    const localId = "1716880000123";
    window.currentSessionId = localId;
    await ensureActiveChatSession(createSession, () => localId, 0);
    expect(createSession).not.toHaveBeenCalled();
  });

  it("creates session when chat has messages but window id is missing", async () => {
    const createSession = vi.fn().mockResolvedValue("1716880000124");
    await ensureActiveChatSession(createSession, () => "some-id", 2);
    expect(createSession).toHaveBeenCalledOnce();
  });
});
