import { request } from "../request";
import type { AgentStatsSummary } from "../types/agentStats";

export interface GetAgentStatsParams {
  start_date: string;
  end_date: string;
  /** Admin only: aggregate statistics across all users for current agent */
  scope?: "all";
}

export const agentStatsApi = {
  getAgentStats: (params: GetAgentStatsParams) => {
    const search = new URLSearchParams({
      start_date: params.start_date,
      end_date: params.end_date,
    });
    if (params.scope) search.set("scope", params.scope);
    return request<AgentStatsSummary>(`/agent-stats?${search.toString()}`);
  },
};
