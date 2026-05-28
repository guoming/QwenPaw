import type { ReactElement } from "react";
import { WelcomePrompts, useChatAnywhereSessions } from "@agentscope-ai/chat";
import { ensureActiveChatSession } from "./ChatSubmitSessionGuard/ensureActiveChatSession";

export interface WelcomeRenderProps {
  greeting?: string | ReactElement;
  description?: string | ReactElement;
  avatar?: string | ReactElement;
  prompts?: Array<{ label?: string; value: string; icon?: ReactElement } | string>;
  onSubmit: (data: { query: string; fileList?: unknown[] }) => void;
}

type WelcomeWithSessionEnsureProps = WelcomeRenderProps;

/** Welcome prompts: create session before submit (bypasses sender beforeSubmit). */
export default function WelcomeWithSessionEnsure({
  onSubmit,
  ...welcomeProps
}: WelcomeWithSessionEnsureProps) {
  const { createSession, getCurrentSessionId } = useChatAnywhereSessions();

  const handlePromptClick = async (query: string) => {
    await ensureActiveChatSession(createSession, getCurrentSessionId, 0);
    onSubmit({ query });
  };

  return <WelcomePrompts {...welcomeProps} onClick={handlePromptClick} />;
}
