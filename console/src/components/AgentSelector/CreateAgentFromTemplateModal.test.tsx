import { describe, it, expect } from "vitest";
import { buildCreateFromTemplatePayload } from "./CreateAgentFromTemplateModal.utils";

describe("buildCreateFromTemplatePayload", () => {
  it("sends only template id when optional fields are empty", () => {
    const payload = buildCreateFromTemplatePayload({
      template_agent_id: "default",
    });
    expect(payload).toEqual({
      template_agent_id: "default",
      name: undefined,
      description: undefined,
    });
  });

  it("trims optional name and description", () => {
    const payload = buildCreateFromTemplatePayload({
      template_agent_id: "default",
      name: "  My Agent  ",
      description: "  Desc  ",
    });
    expect(payload).toEqual({
      template_agent_id: "default",
      name: "My Agent",
      description: "Desc",
    });
  });
});
