import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/common_setup";
import AdminOnlyRoute from "./AdminOnlyRoute";

const { mockUseIsAdmin } = vi.hoisted(() => ({
  mockUseIsAdmin: vi.fn(),
}));

vi.mock("@/hooks/useIsAdmin", () => ({
  useIsAdmin: mockUseIsAdmin,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

describe("AdminOnlyRoute", () => {
  it("renders children when user is admin", () => {
    mockUseIsAdmin.mockReturnValue(true);
    renderWithProviders(
      <AdminOnlyRoute>
        <div>secure-content</div>
      </AdminOnlyRoute>,
    );
    expect(screen.getByText("secure-content")).toBeInTheDocument();
  });

  it("renders forbidden page when user is not admin", () => {
    mockUseIsAdmin.mockReturnValue(false);
    renderWithProviders(
      <AdminOnlyRoute>
        <div>secure-content</div>
      </AdminOnlyRoute>,
    );
    expect(screen.getByText("403")).toBeInTheDocument();
  });
});
