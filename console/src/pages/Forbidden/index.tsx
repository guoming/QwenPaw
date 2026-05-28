import { Result } from "antd";
import { useTranslation } from "react-i18next";

export default function ForbiddenPage() {
  const { t } = useTranslation();

  return (
    <Result
      status="403"
      title="403"
      subTitle={t(
        "common.forbidden",
        "You do not have permission to access this page.",
      )}
    />
  );
}
