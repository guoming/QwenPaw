# Agent Management Admin-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `/api/agents` readable for logged-in users (for agent switching), while making agent management UI and mutating APIs strictly admin-only with explicit 403 behavior.

**Architecture:** Enforce admin-only mutation at the backend (`/api/agents*` write operations) and enforce admin-only management UI at the frontend (hide entry points and block `/agents` route with a 403 page). Preserve the existing agent selector flow by keeping read-only agent list APIs available to non-admin users.

**Tech Stack:** FastAPI (Python), React + React Router + Ant Design (TypeScript), pytest integration tests, Vitest + Testing Library.

---

## File Structure and Responsibilities

- **Modify** `src/qwenpaw/app/routers/agents.py`
  - Route-level admin guard for `/api/agents/{agentId}/toggle` write endpoint.
- **Modify** `tests/integration/test_multi_user_auth.py`
  - Multi-user permission assertions for read-vs-write behavior on `/api/agents`.
- **Modify** `console/src/components/AgentSelector/index.tsx`
  - Remove management jump entry from selector dropdown, keep switch-only behavior.
- **Modify** `console/src/components/AgentSelector/AgentSelector.test.tsx`
  - Assert selector remains usable and no management entry is exposed.
- **Create** `console/src/pages/Forbidden/index.tsx`
  - Reusable 403 page for route-level access denial.
- **Create** `console/src/components/AdminOnlyRoute.tsx`
  - Single-purpose route guard component rendering children for admin else 403 page.
- **Create** `console/src/components/AdminOnlyRoute.test.tsx`
  - Unit tests for admin/non-admin route rendering behavior.
- **Modify** `console/src/layouts/MainLayout/index.tsx`
  - Reuse `AdminOnlyRoute` for `/agents` and existing admin-only settings pages.
- **Modify** `console/src/locales/zh.json`
  - Add 403 page i18n text.
- **Modify** `console/src/locales/en.json`
  - Add 403 page i18n text.

---

### Task 1: Harden backend `/api/agents` write permission boundary

**Files:**
- Modify: `src/qwenpaw/app/routers/agents.py`
- Modify: `tests/integration/test_multi_user_auth.py`
- Test: `tests/integration/test_multi_user_auth.py`

- [ ] **Step 1: Write failing integration tests for non-admin access matrix**

```python
def test_non_admin_can_read_agents_list(app_server: AppServer) -> None:
    token_b = register(
        app_server.client,
        app_server.base_url,
        "integ_user_list_only",
        "integ_user_list_only_secret",
    )
    resp = app_server.api_request(
        "GET",
        "/api/agents",
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 200, app_server.logs_tail()
    assert isinstance(resp.json().get("agents"), list)


def test_non_admin_cannot_toggle_agent(app_server: AppServer) -> None:
    token_b = register(
        app_server.client,
        app_server.base_url,
        "integ_user_toggle_forbidden",
        "integ_user_toggle_forbidden_secret",
    )
    resp = app_server.api_request(
        "PATCH",
        "/api/agents/default/toggle",
        json={"enabled": False},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 403, app_server.logs_tail()
```

- [ ] **Step 2: Run tests to confirm at least one failure**

Run: `pytest tests/integration/test_multi_user_auth.py -k "agents_list or toggle" -v`  
Expected: FAIL on `test_non_admin_cannot_toggle_agent` (currently not guarded at route level).

- [ ] **Step 3: Add explicit admin guard to toggle endpoint**

```python
@router.patch(
    "/{agentId}/toggle",
    summary="Toggle agent enabled state",
    description="Enable or disable an agent (cannot disable default agent)",
)
async def toggle_agent_enabled(
    agentId: str = PathParam(...),
    enabled: bool = Body(..., embed=True),
    request: Request = None,
) -> dict:
    """Toggle agent enabled state."""
    require_admin(request)
    config = load_config()
    # ... keep existing logic unchanged
```

- [ ] **Step 4: Re-run tests and verify passing**

Run: `pytest tests/integration/test_multi_user_auth.py -k "agents_list or toggle" -v`  
Expected: PASS for both tests (`GET`=200 for non-admin, `PATCH`=403 for non-admin).

- [ ] **Step 5: Commit backend permission hardening**

```bash
git add src/qwenpaw/app/routers/agents.py tests/integration/test_multi_user_auth.py
git commit -m "fix(auth): enforce admin-only agent toggle while keeping list read-only"
```

---

### Task 2: Remove management entry from Agent selector UI

**Files:**
- Modify: `console/src/components/AgentSelector/index.tsx`
- Modify: `console/src/components/AgentSelector/AgentSelector.test.tsx`
- Test: `console/src/components/AgentSelector/AgentSelector.test.tsx`

- [ ] **Step 1: Add failing UI test ensuring no management action is rendered**

```tsx
it("does not expose management entry in selector dropdown", async () => {
  renderWithProviders(<AgentSelector />);
  await waitFor(() => expect(mockListAgents).toHaveBeenCalled());

  // open Select dropdown
  const combo = screen.getByRole("combobox");
  combo.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

  await waitFor(() => {
    expect(screen.queryByText("agent.management")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to confirm failure**

Run: `cd console && npm test -- AgentSelector.test.tsx`  
Expected: FAIL because dropdown header still renders `agent.management` button.

- [ ] **Step 3: Remove management jump button from selector dropdown**

```tsx
dropdownRender={(menu) => (
  <>
    <div className={styles.dropdownHeader}>
      <span className={styles.dropdownHeaderTitle}>
        {t("agent.currentWorkspace")}
      </span>
    </div>
    {menu}
  </>
)}
```

- [ ] **Step 4: Re-run selector test**

Run: `cd console && npm test -- AgentSelector.test.tsx`  
Expected: PASS; selector still loads/sorts agents and no management entry appears.

- [ ] **Step 5: Commit selector visibility change**

```bash
git add console/src/components/AgentSelector/index.tsx console/src/components/AgentSelector/AgentSelector.test.tsx
git commit -m "feat(console): remove agent management entry from selector"
```

---

### Task 3: Enforce `/agents` route 403 for non-admin users

**Files:**
- Create: `console/src/pages/Forbidden/index.tsx`
- Create: `console/src/components/AdminOnlyRoute.tsx`
- Create: `console/src/components/AdminOnlyRoute.test.tsx`
- Modify: `console/src/layouts/MainLayout/index.tsx`
- Modify: `console/src/locales/zh.json`
- Modify: `console/src/locales/en.json`
- Test: `console/src/components/AdminOnlyRoute.test.tsx`

- [ ] **Step 1: Write failing route-guard unit tests**

```tsx
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
```

- [ ] **Step 2: Run tests to verify failure before implementation**

Run: `cd console && npm test -- AdminOnlyRoute.test.tsx`  
Expected: FAIL because `AdminOnlyRoute` component does not exist yet.

- [ ] **Step 3: Implement reusable 403 route guard and wire `/agents`**

```tsx
// console/src/components/AdminOnlyRoute.tsx
import type { ReactElement } from "react";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import ForbiddenPage from "@/pages/Forbidden";

export default function AdminOnlyRoute({
  children,
}: {
  children: ReactElement;
}) {
  const isAdmin = useIsAdmin();
  if (!isAdmin) return <ForbiddenPage />;
  return children;
}
```

```tsx
// console/src/layouts/MainLayout/index.tsx
import AdminOnlyRoute from "@/components/AdminOnlyRoute";

<Route
  path="/agents"
  element={
    <AdminOnlyRoute>
      <SettingsPageShell>
        <AgentsPage />
      </SettingsPageShell>
    </AdminOnlyRoute>
  }
/>
```

```tsx
// console/src/pages/Forbidden/index.tsx
import { Result } from "antd";
import { useTranslation } from "react-i18next";

export default function ForbiddenPage() {
  const { t } = useTranslation();
  return (
    <Result
      status="403"
      title="403"
      subTitle={t("common.forbidden", "You do not have permission to access this page.")}
    />
  );
}
```

- [ ] **Step 4: Re-run tests for route guard**

Run: `cd console && npm test -- AdminOnlyRoute.test.tsx`  
Expected: PASS for admin and non-admin cases.

- [ ] **Step 5: Commit route-level 403 enforcement**

```bash
git add console/src/pages/Forbidden/index.tsx console/src/components/AdminOnlyRoute.tsx console/src/components/AdminOnlyRoute.test.tsx console/src/layouts/MainLayout/index.tsx console/src/locales/zh.json console/src/locales/en.json
git commit -m "feat(console): enforce admin-only agents route with 403 page"
```

---

### Task 4: Full regression verification and documentation sync

**Files:**
- Modify: `docs/superpowers/specs/2026-05-28-agent-management-admin-only-design.md` (status update only if needed)
- Test: `tests/integration/test_multi_user_auth.py`
- Test: `console/src/components/AgentSelector/AgentSelector.test.tsx`
- Test: `console/src/components/AdminOnlyRoute.test.tsx`

- [ ] **Step 1: Execute backend integration suite for changed permission area**

Run: `pytest tests/integration/test_multi_user_auth.py -v`  
Expected: PASS, including non-admin read-only and write forbidden assertions.

- [ ] **Step 2: Execute impacted frontend unit tests**

Run: `cd console && npm test -- AgentSelector.test.tsx AdminOnlyRoute.test.tsx`  
Expected: PASS.

- [ ] **Step 3: Run lint/typecheck for frontend safety**

Run: `cd console && npm run lint && npm run build`  
Expected: lint/build pass with no new errors.

- [ ] **Step 4: Optional spec status update**

```markdown
**状态:** 已确认（实施中）
```

- [ ] **Step 5: Commit final verification snapshot**

```bash
git add docs/superpowers/specs/2026-05-28-agent-management-admin-only-design.md
git commit -m "chore: verify admin-only agent management rollout"
```

---

## Self-Review Checklist (Completed)

- **Spec coverage:** Covered all confirmed requirements: hide management entry, `/agents` route 403, `/api/agents` read-only for non-admin, `/api/agents*` write 403.
- **Placeholder scan:** No TBD/TODO placeholders remain in tasks or commands.
- **Type consistency:** Route guard component and page imports use consistent names (`AdminOnlyRoute`, `ForbiddenPage`) across all tasks.
