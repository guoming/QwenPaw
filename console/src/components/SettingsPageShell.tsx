import { createContext, useContext, type ReactNode } from "react";
import AdminOnlyBanner from "./AdminOnlyBanner";
import { useIsAdmin } from "../hooks/useIsAdmin";

const SettingsWritableContext = createContext(true);

export function useSettingsWritable(): boolean {
  return useContext(SettingsWritableContext);
}

/** Spread onto Ant Design buttons/inputs that mutate global Settings. */
export function useSettingsWriteProps(): { disabled: boolean } {
  return { disabled: !useSettingsWritable() };
}

interface SettingsPageShellProps {
  children: ReactNode;
}

export default function SettingsPageShell({ children }: SettingsPageShellProps) {
  const writable = useIsAdmin();

  return (
    <SettingsWritableContext.Provider value={writable}>
      <AdminOnlyBanner show={!writable} />
      {children}
    </SettingsWritableContext.Provider>
  );
}
