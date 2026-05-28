import { getIsAdmin } from "../api/config";

export function useIsAdmin(): boolean {
  return getIsAdmin();
}
