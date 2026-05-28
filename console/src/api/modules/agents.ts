import { request } from "../request";
import type {
  AgentListResponse,
  AgentSummary,
  AgentTemplateListResponse,
  AgentProfileConfig,
  CreateAgentRequest,
  CreateAgentFromTemplateRequest,
  UpdatePrivateAgentRequest,
  AgentProfileRef,
  ReorderAgentsResponse,
} from "../types/agents";

// Multi-agent management API
export const agentsApi = {
  // List all agents
  listAgents: () => request<AgentListResponse>("/agents"),

  // List enabled templates for self-provisioning
  listAgentTemplates: () =>
    request<AgentTemplateListResponse>("/agent-templates"),

  // Get agent details
  getAgent: (agentId: string) =>
    request<AgentProfileConfig>(`/agents/${agentId}`),

  // Create new agent
  createAgent: (agent: CreateAgentRequest) =>
    request<AgentProfileRef>("/agents", {
      method: "POST",
      body: JSON.stringify(agent),
    }),

  // Create private agent from template
  createAgentFromTemplate: (payload: CreateAgentFromTemplateRequest) =>
    request<AgentSummary>("/agents/from-template", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updatePrivateAgent: (agentId: string, payload: UpdatePrivateAgentRequest) =>
    request<AgentSummary>(`/agents/${agentId}/self`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deletePrivateAgent: (agentId: string) =>
    request<{ success: boolean; agent_id: string }>(`/agents/${agentId}/self`, {
      method: "DELETE",
    }),

  // Update agent configuration
  updateAgent: (agentId: string, agent: AgentProfileConfig) =>
    request<AgentProfileConfig>(`/agents/${agentId}`, {
      method: "PUT",
      body: JSON.stringify(agent),
    }),

  // Delete agent
  deleteAgent: (agentId: string) =>
    request<{ success: boolean; agent_id: string }>(`/agents/${agentId}`, {
      method: "DELETE",
    }),

  // Persist ordered agent ids
  reorderAgents: (agentIds: string[]) =>
    request<ReorderAgentsResponse>("/agents/order", {
      method: "PUT",
      body: JSON.stringify({ agent_ids: agentIds }),
    }),

  // Toggle agent enabled state
  toggleAgentEnabled: (agentId: string, enabled: boolean) =>
    request<{ success: boolean; agent_id: string; enabled: boolean }>(
      `/agents/${agentId}/toggle`,
      {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      },
    ),
};
