import { Alert } from "antd";
import { useTranslation } from "react-i18next";

interface AdminOnlyBannerProps {
  show: boolean;
}

export default function AdminOnlyBanner({ show }: AdminOnlyBannerProps) {
  const { t } = useTranslation();

  if (!show) {
    return null;
  }

  return (
    <Alert
      type="warning"
      showIcon
      style={{ marginBottom: 16 }}
      message={t(
        "settings.adminOnlyBanner",
        "Only administrators can change global settings. You have read-only access.",
      )}
    />
  );
}
