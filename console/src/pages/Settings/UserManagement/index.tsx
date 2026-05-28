import { useEffect, useState } from "react";
import {
  Button,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
} from "antd";
import { useTranslation } from "react-i18next";
import { authApi, type UserRecord } from "../../../api/modules/auth";
import { useAppMessage } from "../../../hooks/useAppMessage";
import { getUserId } from "../../../api/config";
import { PageHeader } from "@/components/PageHeader";
import { useIsAdmin } from "../../../hooks/useIsAdmin";

type CreateUserForm = {
  username: string;
  password: string;
  confirmPassword: string;
};

type ResetPasswordForm = {
  newPassword: string;
  confirmPassword: string;
};

export default function UserManagementPage() {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const isAdmin = useIsAdmin();
  const currentUserId = getUserId();

  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [targetUser, setTargetUser] = useState<UserRecord | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [createForm] = Form.useForm<CreateUserForm>();
  const [resetForm] = Form.useForm<ResetPasswordForm>();

  const loadUsers = async () => {
    setLoading(true);
    try {
      const list = await authApi.listUsers();
      setUsers(list);
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("userManagement.loadFailed");
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isAdmin) {
      return;
    }
    void loadUsers();
  }, [isAdmin]);

  const openCreateModal = () => {
    createForm.resetFields();
    setCreateOpen(true);
  };

  const handleCreate = async (values: CreateUserForm) => {
    setSubmitting(true);
    try {
      await authApi.createUser(values.username.trim(), values.password.trim());
      message.success(t("userManagement.createSuccess"));
      setCreateOpen(false);
      await loadUsers();
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("userManagement.createFailed");
      message.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const openResetModal = (user: UserRecord) => {
    setTargetUser(user);
    resetForm.resetFields();
    setResetOpen(true);
  };

  const handleResetPassword = async (values: ResetPasswordForm) => {
    if (!targetUser) return;
    setSubmitting(true);
    try {
      await authApi.resetUserPassword(
        targetUser.user_id,
        values.newPassword.trim(),
      );
      message.success(t("userManagement.resetSuccess"));
      setResetOpen(false);
      setTargetUser(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("userManagement.resetFailed");
      message.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (user: UserRecord) => {
    try {
      await authApi.deleteUser(user.user_id);
      message.success(t("userManagement.deleteSuccess"));
      await loadUsers();
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("userManagement.deleteFailed");
      message.error(msg);
    }
  };

  return (
    <div>
      <PageHeader parent={t("nav.settings")} current={t("userManagement.title")} />
      {!isAdmin ? (
        <Empty description={t("settings.adminOnlyBanner")} />
      ) : (
        <>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" onClick={openCreateModal}>
          {t("userManagement.addUser")}
        </Button>
        <Button onClick={() => void loadUsers()}>{t("common.refresh")}</Button>
      </Space>
      <Table<UserRecord>
        rowKey="user_id"
        loading={loading}
        dataSource={users}
        pagination={false}
        columns={[
          {
            title: t("userManagement.username"),
            dataIndex: "username",
            key: "username",
          },
          {
            title: t("userManagement.userId"),
            dataIndex: "user_id",
            key: "user_id",
          },
          {
            title: t("userManagement.role"),
            key: "role",
            render: (_, record) =>
              record.is_admin ? (
                <Tag color="orange">{t("userManagement.admin")}</Tag>
              ) : (
                <Tag>{t("userManagement.user")}</Tag>
              ),
          },
          {
            title: t("common.actions"),
            key: "actions",
            render: (_, record) => (
              <Space>
                <Button size="small" onClick={() => openResetModal(record)}>
                  {t("userManagement.resetPassword")}
                </Button>
                <Popconfirm
                  title={t("userManagement.deleteConfirm")}
                  onConfirm={() => void handleDelete(record)}
                  okText={t("common.confirm")}
                  cancelText={t("common.cancel")}
                  disabled={record.is_admin || record.user_id === currentUserId}
                >
                  <Button
                    size="small"
                    danger
                    disabled={record.is_admin || record.user_id === currentUserId}
                  >
                    {t("common.delete")}
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
        </>
      )}

      <Modal
        title={t("userManagement.addUser")}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <Form<CreateUserForm> form={createForm} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="username"
            label={t("userManagement.username")}
            rules={[{ required: true, message: t("login.usernameRequired") }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="password"
            label={t("userManagement.password")}
            rules={[{ required: true, message: t("login.passwordRequired") }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            label={t("userManagement.confirmPassword")}
            dependencies={["password"]}
            rules={[
              { required: true, message: t("userManagement.confirmPasswordRequired") },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue("password") === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error(t("account.passwordMismatch")));
                },
              }),
            ]}
          >
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={submitting}>
            {t("common.create")}
          </Button>
        </Form>
      </Modal>

      <Modal
        title={t("userManagement.resetPassword")}
        open={resetOpen}
        onCancel={() => {
          setResetOpen(false);
          setTargetUser(null);
        }}
        footer={null}
        destroyOnHidden
      >
        <Form<ResetPasswordForm>
          form={resetForm}
          layout="vertical"
          onFinish={handleResetPassword}
        >
          <Form.Item
            name="newPassword"
            label={t("userManagement.password")}
            rules={[{ required: true, message: t("login.passwordRequired") }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            label={t("userManagement.confirmPassword")}
            dependencies={["newPassword"]}
            rules={[
              { required: true, message: t("userManagement.confirmPasswordRequired") },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue("newPassword") === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error(t("account.passwordMismatch")));
                },
              }),
            ]}
          >
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={submitting}>
            {t("common.save")}
          </Button>
        </Form>
      </Modal>
    </div>
  );
}

