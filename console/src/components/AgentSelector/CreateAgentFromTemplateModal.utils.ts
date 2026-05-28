import type { CreateAgentFromTemplateRequest } from "@/api/types/agents";

export interface CreateFromTemplateFormValues {
  template_agent_id: string;
  name?: string;
  description?: string;
}

export function buildCreateFromTemplatePayload(
  values: CreateFromTemplateFormValues,
): CreateAgentFromTemplateRequest {
  return {
    template_agent_id: values.template_agent_id,
    name: values.name?.trim() || undefined,
    description: values.description?.trim() || undefined,
  };
}
