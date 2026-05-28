import { useEffect, useState } from "react";
import { Form, Input, Modal, Spin } from "antd";
import type { AgentSummary } from "@/api/types/agents";
import { agentsApi } from "@/api/modules/agents";
import { useTranslation } from "react-i18next";
import { useAppMessage } from "@/hooks/useAppMessage";

interface EditPrivateAgentModalProps {
  open: boolean;
  agent: AgentSummary | null;
  onCancel: () => void;
  onUpdated: (agent: AgentSummary) => void;
}

export default function EditPrivateAgentModal({
  open,
  agent,
  onCancel,
  onUpdated,
}: EditPrivateAgentModalProps) {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !agent) return;
    setLoading(true);
    agentsApi
      .getAgent(agent.id)
      .then((config) => {
        form.setFieldsValue({
          name: config.name,
          description: config.description,
        });
      })
      .catch((error) => {
        console.error("Failed to load agent config:", error);
        message.error(t("agent.loadConfigFailed"));
        onCancel();
      })
      .finally(() => setLoading(false));
  }, [open, agent, form, message, onCancel, t]);

  const handleSubmit = async () => {
    if (!agent) return;
    try {
      const values = await form.validateFields();
      setSaving(true);
      const updated = await agentsApi.updatePrivateAgent(agent.id, {
        name: values.name?.trim() || undefined,
        description: values.description?.trim() || undefined,
      });
      onUpdated(updated);
    } catch (error: unknown) {
      if (
        typeof error === "object" &&
        error !== null &&
        "errorFields" in error
      ) {
        return;
      }
      console.error("Failed to update private agent:", error);
      message.error(t("agent.updateFailed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={t("agent.editTitle", { name: agent?.name ?? agent?.id ?? "" })}
      open={open}
      onOk={handleSubmit}
      onCancel={onCancel}
      confirmLoading={saving}
      okText={t("common.save")}
      cancelText={t("common.cancel")}
      destroyOnHidden
    >
      {loading ? (
        <div style={{ textAlign: "center", padding: "24px 0" }}>
          <Spin />
        </div>
      ) : (
        <Form form={form} layout="vertical" autoComplete="off">
          <Form.Item
            name="name"
            label={t("agent.name")}
            rules={[{ required: true, message: t("agent.nameRequired") }]}
          >
            <Input placeholder={t("agent.namePlaceholder")} />
          </Form.Item>
          <Form.Item name="description" label={t("agent.description")}>
            <Input.TextArea
              placeholder={t("agent.descriptionPlaceholder")}
              rows={3}
            />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}
