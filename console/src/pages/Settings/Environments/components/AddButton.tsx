import { SparkPlusLine } from "@agentscope-ai/icons";
import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

interface AddButtonProps {
  onClick: () => void;
  className?: string;
  disabled?: boolean;
}

export function AddButton({ onClick, className, disabled }: AddButtonProps) {
  const { t } = useTranslation();

  return (
    <div className={`${styles.addBar} ${className || ""}`}>
      <button
        className={styles.addBtn}
        onClick={onClick}
        disabled={disabled}
        title={t("environments.addVariable")}
      >
        <SparkPlusLine />
        <span>{t("environments.addVariable")}</span>
      </button>
    </div>
  );
}
