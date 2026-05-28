import type { ReactElement } from "react";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import ForbiddenPage from "@/pages/Forbidden";

export default function AdminOnlyRoute({
  children,
}: {
  children: ReactElement;
}) {
  const isAdmin = useIsAdmin();
  if (!isAdmin) {
    return <ForbiddenPage />;
  }
  return children;
}
