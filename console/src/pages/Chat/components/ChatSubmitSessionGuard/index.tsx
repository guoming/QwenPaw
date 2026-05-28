import { useEffect } from "react";
import { useChatAnywhereSessions } from "@agentscope-ai/chat";

interface CustomWindow extends Window {
  currentSessionId?: string;
}

declare const window: CustomWindow;

type EnsureSessionFn = () => Promise<void>;

let ensureSessionBeforeSubmit: EnsureSessionFn | null = null;

/** Called from ChatPage `beforeSubmit` (outside React context). */
export async function runEnsureSessionBeforeSubmit(): Promise<void> {
  if (ensureSessionBeforeSubmit) {
    await ensureSessionBeforeSubmit();
  }
}

/**
 * Registers a hook-backed ensure-session callback for first message on welcome
 * screen (when user has not clicked "New chat" yet).
 */
export default function ChatSubmitSessionGuard() {
  const { createSession, getCurrentSessionId } = useChatAnywhereSessions();

  useEffect(() => {
    ensureSessionBeforeSubmit = async () => {
      const sessionId = getCurrentSessionId();
      if (sessionId && window.currentSessionId) {
        return;
      }
      await createSession();
    };
    return () => {
      ensureSessionBeforeSubmit = null;
    };
  }, [createSession, getCurrentSessionId]);

  return null;
}
