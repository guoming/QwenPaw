import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/common_setup";
import AgentSelector from "./index";

const { mockSetSelectedAgent, mockSetAgents, mockListAgents } =
  vi.hoisted(() => ({
    mockSetSelectedAgent: vi.fn(),
    mockSetAgents: vi.fn(),
    mockListAgents: vi.fn(),
  }));

vi.mock("@/api/modules/agents", () => ({
  agentsApi: { listAgents: mockListAgents },
}));

vi.mock("@/stores/agentStore", () => ({
  useAgentStore: vi.fn(() => ({
    selectedAgent: "default",
    agents: [],
    setSelectedAgent: mockSetSelectedAgent,
    setAgents: mockSetAgents,
  })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

const mockAgentsData = {
  agents: [
    { id: "agent-1", name: "Agent One", enabled: true, description: "desc" },
    { id: "agent-2", name: "Agent Two", enabled: false, description: "" },
  ],
};

describe("AgentSelector", () => {
  beforeEach(() => {
    mockListAgents.mockResolvedValue(mockAgentsData);
  });

  afterEach(() => vi.clearAllMocks());

  it("calls listAgents on mount", async () => {
    renderWithProviders(<AgentSelector />);
    await waitFor(() => expect(mockListAgents).toHaveBeenCalledOnce());
  });

  it("after loading, setAgents receives the list with enabled agents first", async () => {
    renderWithProviders(<AgentSelector />);
    await waitFor(() => expect(mockSetAgents).toHaveBeenCalled());
    const sortedAgents = mockSetAgents.mock.calls[0][0];
    expect(sortedAgents[0].enabled).toBe(true);
    expect(sortedAgents[1].enabled).toBe(false);
  });

  it("does not render Select in collapsed mode", async () => {
    renderWithProviders(<AgentSelector collapsed />);
    await waitFor(() => expect(mockListAgents).toHaveBeenCalled());
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("renders Select in non-collapsed mode", async () => {
    renderWithProviders(<AgentSelector />);
    await waitFor(() => expect(mockListAgents).toHaveBeenCalled());
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("does not crash when listAgents fails", async () => {
    mockListAgents.mockRejectedValue(new Error("network error"));
    expect(() => renderWithProviders(<AgentSelector />)).not.toThrow();
    await waitFor(() => expect(mockListAgents).toHaveBeenCalled());
  });

  it("renders empty-state create button when agent list is empty", async () => {
    mockListAgents.mockResolvedValue({ agents: [] });
    renderWithProviders(<AgentSelector />);
    await waitFor(() => expect(mockListAgents).toHaveBeenCalled());
    expect(screen.getByText("agent.createFirstAgent")).toBeInTheDocument();
  });

  it("does not expose management entry in selector dropdown", async () => {
    renderWithProviders(<AgentSelector />);
    await waitFor(() => expect(mockListAgents).toHaveBeenCalled());
    expect(screen.queryByText("agent.management")).not.toBeInTheDocument();
  });
});
