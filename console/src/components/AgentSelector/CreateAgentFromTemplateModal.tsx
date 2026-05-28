import { useEffect, useState } from "react";
import { Form, Input, Modal, Select, Spin, Typography } from "antd";
import type {
  AgentSummary,
  AgentTemplateSummary,
} from "@/api/types/agents";
import { agentsApi } from "@/api/modules/agents";
import { useTranslation } from "react-i18next";
import { useAppMessage } from "@/hooks/useAppMessage";
import { buildCreateFromTemplatePayload } from "./CreateAgentFromTemplateModal.utils";

interface CreateAgentFromTemplateModalProps {
  open: boolean;
  onCancel: () => void;
  onCreated: (agent: AgentSummary) => void;
}

export default function CreateAgentFromTemplateModal({
  open,
  onCancel,
  onCreated,
}: CreateAgentFromTemplateModalProps) {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [templates, setTemplates] = useState<AgentTemplateSummary[]>([]);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    agentsApi
      .listAgentTemplates()
      .then((templatesResp) => {
        const templateList = templatesResp.templates ?? [];
        setTemplates(templateList);
        if (!form.getFieldValue("template_agent_id") && templateList.length > 0) {
          form.setFieldValue("template_agent_id", templateList[0].id);
        }
      })
      .catch((error) => {
        console.error("Failed to load template modal resources:", error);
        message.error(t("agent.loadFailed"));
      })
      .finally(() => setLoading(false));
  }, [open, form, message, t]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const created = await agentsApi.createAgentFromTemplate(
        buildCreateFromTemplatePayload(values),
      );
      form.resetFields();
      onCreated(created);
    } catch (error: unknown) {
      if (
        typeof error === "object" &&
        error !== null &&
        "errorFields" in error
      ) {
        return;
      }
      console.error("Failed to create agent from template:", error);
      const errMsg =
        typeof error === "object" &&
        error !== null &&
        "message" in error &&
        typeof (error as { message: unknown }).message === "string"
          ? (error as { message: string }).message
          : t("agent.createFailed");
      message.error(errMsg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={t("agent.createTitle")}
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
          <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
            {t("agent.createFromTemplateHint")}
          </Typography.Paragraph>
          <Form.Item
            name="template_agent_id"
            label={t("agent.template")}
            rules={[{ required: true, message: t("agent.templateRequired") }]}
          >
            <Select
              placeholder={t("agent.template")}
              options={templates.map((tpl) => ({
                value: tpl.id,
                label: tpl.name,
              }))}
            />
          </Form.Item>
          <Form.Item name="name" label={t("agent.name")}>
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
