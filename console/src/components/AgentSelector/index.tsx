import { Button, Modal, Select, Tag, Tooltip } from "antd";
import { useEffect, useState } from "react";
import { Bot, CheckCircle, EyeOff, Pencil, Trash2 } from "lucide-react";
import { SparkDownLine, SparkUpLine } from "@agentscope-ai/icons";
import { useAgentStore } from "../../stores/agentStore";
import { agentsApi } from "../../api/modules/agents";
import { useTranslation } from "react-i18next";
import { getAgentDisplayName } from "../../utils/agentDisplayName";
import { useAppMessage } from "../../hooks/useAppMessage";
import type { AgentSummary } from "@/api/types/agents";
import CreateAgentFromTemplateModal from "./CreateAgentFromTemplateModal";
import EditPrivateAgentModal from "./EditPrivateAgentModal";
import styles from "./index.module.less";

interface AgentSelectorProps {
  collapsed?: boolean;
}

function pickFallbackAgentId(
  agents: AgentSummary[],
  currentId: string,
): string | null {
  const remaining = agents.filter((agent) => agent.id !== currentId && agent.enabled);
  if (remaining.length > 0) return remaining[0].id;
  const anyRemaining = agents.find((agent) => agent.id !== currentId);
  return anyRemaining?.id ?? null;
}

export default function AgentSelector({
  collapsed = false,
}: AgentSelectorProps) {
  const { t } = useTranslation();
  const { selectedAgent, agents, setSelectedAgent, setAgents } =
    useAgentStore();
  const { message } = useAppMessage();
  const [loading, setLoading] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentSummary | null>(null);
  const [fetchedAgents, setFetchedAgents] = useState<AgentSummary[]>([]);
  const visibleAgents =
    agents && agents.length > 0 ? agents : (fetchedAgents ?? []);

  useEffect(() => {
    void loadAgents();
  }, []);

  const loadAgents = async () => {
    try {
      setLoading(true);
      const data = await agentsApi.listAgents();
      const sortedAgents = [...data.agents].sort((a, b) => {
        if (a.enabled === b.enabled) return 0;
        return a.enabled ? -1 : 1;
      });
      setFetchedAgents(sortedAgents);
      setAgents(sortedAgents);
    } catch (error) {
      console.error("Failed to load agents:", error);
      message.error(t("agent.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (value: string) => {
    const targetAgent = visibleAgents?.find((a) => a.id === value);

    if (targetAgent && !targetAgent.enabled) {
      message.warning(t("agent.cannotSwitchToDisabled"));
      return;
    }

    setSelectedAgent(value);
    message.success(t("agent.switchSuccess"));
  };

  useEffect(() => {
    if (!visibleAgents?.length) return;

    const currentAgent = visibleAgents.find((a) => a.id === selectedAgent);

    if (!currentAgent) {
      const fallback = pickFallbackAgentId(visibleAgents, selectedAgent);
      if (fallback) {
        setSelectedAgent(fallback);
        message.warning(t("agent.currentAgentDeleted"));
      }
      return;
    }

    if (!currentAgent.enabled) {
      const fallback = pickFallbackAgentId(visibleAgents, selectedAgent);
      if (fallback) {
        setSelectedAgent(fallback);
        message.warning(t("agent.currentAgentDisabled"));
      }
    }
  }, [visibleAgents, selectedAgent, setSelectedAgent, message, t]);

  const enabledCount = visibleAgents?.filter((a) => a.enabled).length ?? 0;
  const agentCount = enabledCount;

  const currentAgentInfo = visibleAgents?.find((a) => a.id === selectedAgent);

  const handleEdit = (agent: AgentSummary, event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setEditingAgent(agent);
    setEditModalOpen(true);
    setDropdownOpen(false);
  };

  const handleDelete = (agent: AgentSummary, event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setDropdownOpen(false);
    Modal.confirm({
      title: t("agent.deleteConfirm"),
      content: t("agent.deletePrivateConfirmDesc", {
        name: getAgentDisplayName(agent, t),
      }),
      okText: t("agent.delete"),
      okType: "danger",
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await agentsApi.deletePrivateAgent(agent.id);
          message.success(t("agent.deleteSuccess"));
          if (selectedAgent === agent.id) {
            const fallback = pickFallbackAgentId(visibleAgents, agent.id);
            if (fallback) setSelectedAgent(fallback);
          }
          await loadAgents();
        } catch (error) {
          console.error("Failed to delete private agent:", error);
          message.error(t("agent.deleteFailed"));
        }
      },
    });
  };

  if (collapsed) {
    return (
      <Tooltip
        title={
          currentAgentInfo
            ? getAgentDisplayName(currentAgentInfo, t)
            : selectedAgent
        }
        placement="right"
        overlayInnerStyle={{ background: "rgba(0,0,0,0.75)", color: "#fff" }}
      >
        <div className={styles.agentSelectorCollapsed}>
          <Bot size={18} strokeWidth={2} />
        </div>
      </Tooltip>
    );
  }

  return (
    <div className={styles.agentSelectorWrapper}>
      <div className={styles.agentSelectorLabel}>
        <span>
          {t("agent.currentWorkspace")}
          {agentCount > 0 && (
            <span className={styles.agentCountBadge}> ({agentCount})</span>
          )}
        </span>
      </div>
      {visibleAgents.length === 0 && !loading ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyStateText}>{t("agent.noPrivateAgents")}</div>
          <Button type="primary" size="small" onClick={() => setCreateModalOpen(true)}>
            {t("agent.createFirstAgent")}
          </Button>
        </div>
      ) : (
        <Select
          value={selectedAgent}
          onChange={handleChange}
          loading={loading}
          open={dropdownOpen}
          className={styles.agentSelector}
          placeholder={t("agent.selectAgent")}
          optionLabelProp="label"
          popupClassName={styles.agentSelectorDropdown}
          onDropdownVisibleChange={setDropdownOpen}
          suffixIcon={
            dropdownOpen ? <SparkUpLine size={20} /> : <SparkDownLine size={20} />
          }
          dropdownRender={(menu) => (
            <>
              <div className={styles.dropdownHeader}>
                <span className={styles.dropdownHeaderTitle}>
                  {t("agent.currentWorkspace")}
                </span>
                <Button
                  type="link"
                  size="small"
                  className={styles.dropdownCreateButton}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    setCreateModalOpen(true);
                  }}
                >
                  {t("agent.create")}
                </Button>
              </div>
              {menu}
            </>
          )}
        >
          {visibleAgents?.map((agent) => (
            <Select.Option
              key={agent.id}
              value={agent.id}
              disabled={!agent.enabled}
              label={
                <div className={styles.selectedAgentLabel}>
                  <Bot size={14} strokeWidth={2} />
                  <span>{getAgentDisplayName(agent, t)}</span>
                  {!agent.enabled && <EyeOff size={12} strokeWidth={2} />}
                </div>
              }
            >
              <div
                className={styles.agentOption}
                style={{ opacity: agent.enabled ? 1 : 0.5 }}
              >
                <div className={styles.agentOptionHeader}>
                  <div className={styles.agentOptionIcon}>
                    <Bot size={16} strokeWidth={2} />
                  </div>
                  <div className={styles.agentOptionContent}>
                    <div className={styles.agentOptionName}>
                      <span className={styles.agentOptionNameText}>
                        {getAgentDisplayName(agent, t)}
                      </span>
                      {agent.id === selectedAgent && (
                        <CheckCircle
                          size={14}
                          strokeWidth={2}
                          className={styles.activeIndicator}
                        />
                      )}
                      {!agent.enabled && (
                        <Tag style={{ margin: 0 }}>{t("agent.disabled")}</Tag>
                      )}
                    </div>
                    {agent.description && (
                      <div className={styles.agentOptionDescription}>
                        {agent.description}
                      </div>
                    )}
                  </div>
                  <div className={styles.agentOptionActions}>
                    <Tooltip title={t("agent.edit")}>
                      <button
                        type="button"
                        className={styles.agentOptionActionButton}
                        aria-label={t("agent.edit")}
                        onClick={(event) => handleEdit(agent, event)}
                      >
                        <Pencil size={14} strokeWidth={2} />
                      </button>
                    </Tooltip>
                    <Tooltip title={t("agent.delete")}>
                      <button
                        type="button"
                        className={`${styles.agentOptionActionButton} ${styles.agentOptionActionButtonDanger}`}
                        aria-label={t("agent.delete")}
                        onClick={(event) => handleDelete(agent, event)}
                      >
                        <Trash2 size={14} strokeWidth={2} />
                      </button>
                    </Tooltip>
                  </div>
                </div>
                <div className={styles.agentOptionId}>ID: {agent.id}</div>
              </div>
            </Select.Option>
          ))}
        </Select>
      )}
      <CreateAgentFromTemplateModal
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onCreated={(created) => {
          setCreateModalOpen(false);
          message.success(t("agent.createSuccess"));
          void loadAgents().then(() => {
            setSelectedAgent(created.id);
          });
        }}
      />
      <EditPrivateAgentModal
        open={editModalOpen}
        agent={editingAgent}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingAgent(null);
        }}
        onUpdated={(updated) => {
          setEditModalOpen(false);
          setEditingAgent(null);
          message.success(t("agent.updateSuccess"));
          void loadAgents().then(() => {
            if (selectedAgent === updated.id) {
              setSelectedAgent(updated.id);
            }
          });
        }}
      />
    </div>
  );
}
