interface CustomWindow extends Window {
  currentSessionId?: string;
}

declare const window: CustomWindow;

/** True when id is a client-side timestamp session (new chat), not a backend UUID. */
export function isLocalTimestampSessionId(id: string): boolean {
  return /^\d+$/.test(id);
}

/**
 * Ensure a chat session exists before the first message.
 * On the welcome screen, ignore a stale selected history session (mount race).
 */
export async function ensureActiveChatSession(
  createSession: (data?: { name?: string }) => Promise<string>,
  getCurrentSessionId: () => string,
  messageCount: number,
): Promise<void> {
  const sessionId = getCurrentSessionId();

  if (messageCount === 0) {
    if (
      sessionId &&
      window.currentSessionId &&
      sessionId === window.currentSessionId &&
      isLocalTimestampSessionId(sessionId)
    ) {
      return;
    }
    await createSession();
    return;
  }

  if (!sessionId || !window.currentSessionId) {
    await createSession();
  }
}
