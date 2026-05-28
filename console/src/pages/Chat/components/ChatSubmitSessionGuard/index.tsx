import { useEffect } from "react";
import { useChatAnywhereSessions } from "@agentscope-ai/chat";
import { ensureActiveChatSession } from "./ensureActiveChatSession";

type EnsureSessionFn = () => Promise<void>;

let ensureSessionBeforeSubmit: EnsureSessionFn | null = null;

/** Called from ChatPage `beforeSubmit` and welcome prompt clicks. */
export async function runEnsureSessionBeforeSubmit(): Promise<void> {
  if (ensureSessionBeforeSubmit) {
    await ensureSessionBeforeSubmit();
  }
}

function isOnWelcomeScreen(): boolean {
  return document.querySelector('[class*="message-list-welcome"]') != null;
}

/**
 * Registers ensure-session logic for welcome screen and sender beforeSubmit.
 */
export default function ChatSubmitSessionGuard() {
  const { createSession, getCurrentSessionId } = useChatAnywhereSessions();

  useEffect(() => {
    ensureSessionBeforeSubmit = async () => {
      const welcomeMessageCount = isOnWelcomeScreen() ? 0 : 1;
      await ensureActiveChatSession(
        createSession,
        getCurrentSessionId,
        welcomeMessageCount,
      );
    };
    return () => {
      ensureSessionBeforeSubmit = null;
    };
  }, [createSession, getCurrentSessionId]);

  return null;
}
