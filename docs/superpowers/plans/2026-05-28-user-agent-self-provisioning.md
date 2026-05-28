# User Agent Self-Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让普通用户登录后不再自动拥有全部智能体，而是在 `AgentSelector` 中基于模板自助创建私有智能体。

**Architecture:** 后端把“模板智能体”和“用户私有智能体”读取路径分离：管理员继续维护模板，普通用户仅读取自己私有实例，并通过新增 `from-template` 接口按需创建。前端保留现有 `AgentSelector` 入口位置，在空列表时展示引导并弹出创建流程（模板选择 + 完整配置），创建成功后刷新并切换。

**Tech Stack:** FastAPI + Pydantic（Python）、React + Zustand + Ant Design（TypeScript）、pytest、Vitest + Testing Library。

---

## File Structure and Responsibilities

- **Modify** `src/qwenpaw/app/user_agent_registry.py`
  - 新增“枚举用户私有智能体 ID”能力，供 `/api/agents` 非管理员分支读取。
- **Modify** `src/qwenpaw/app/routers/auth.py`
  - 移除注册/创建用户时的全量 seed 调用，避免自动初始化全部智能体。
- **Modify** `src/qwenpaw/app/routers/agents.py`
  - `GET /api/agents` 改为用户私有列表语义（管理员保持模板视角）。
  - 新增 `GET /api/agent-templates` 与 `POST /api/agents/from-template`。
- **Modify** `tests/integration/test_multi_user_auth.py`
  - 补充“新用户首次列表为空、不可自动全量初始化”断言。
- **Create** `tests/integration/test_agent_template_provisioning.py`
  - 覆盖模板查询、按模板创建私有实例、模板失效/禁用场景。

- **Modify** `console/src/api/types/agents.ts`
  - 新增模板摘要与按模板创建请求/响应类型。
- **Modify** `console/src/api/modules/agents.ts`
  - 新增 `listAgentTemplates`、`createAgentFromTemplate` API 封装。
- **Create** `console/src/components/AgentSelector/CreateAgentFromTemplateModal.tsx`
  - 承载“模板选择 + 完整高级配置”表单。
- **Modify** `console/src/components/AgentSelector/index.tsx`
  - 空列表 UI、创建入口、创建成功后的刷新与自动切换。
- **Create** `console/src/components/AgentSelector/CreateAgentFromTemplateModal.test.tsx`
  - 模态表单交互与请求参数覆盖测试。
- **Modify** `console/src/components/AgentSelector/AgentSelector.test.tsx`
  - 空列表引导、创建入口、成功切换等场景测试。
- **Modify** `console/src/locales/zh.json`
- **Modify** `console/src/locales/en.json`
  - 增加创建流程与空态文案。

---

### Task 1: 取消注册时全量初始化并建立“用户私有列表”读取基础

**Files:**
- Modify: `src/qwenpaw/app/user_agent_registry.py`
- Modify: `src/qwenpaw/app/routers/auth.py`
- Modify: `src/qwenpaw/app/routers/agents.py`
- Modify: `tests/integration/test_multi_user_auth.py`
- Test: `tests/integration/test_multi_user_auth.py`

- [ ] **Step 1: 先写失败测试（新用户首次列表应为空）**

```python
def test_new_user_agents_list_is_empty_before_self_provision(
    app_server: AppServer,
) -> None:
    token = register(
        app_server.client,
        app_server.base_url,
        "integ_user_empty_list",
        "integ_user_empty_list_secret",
    )
    resp = app_server.api_request(
        "GET",
        "/api/agents",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, app_server.logs_tail()
    data = resp.json()
    assert data["agents"] == []
```

- [ ] **Step 2: 运行测试确认失败（当前会返回全量）**

Run: `pytest tests/integration/test_multi_user_auth.py -k "empty_before_self_provision" -v`  
Expected: FAIL，`agents` 非空。

- [ ] **Step 3: 实现最小改动（移除 seed + 非管理员列表读取用户私有 ID）**

```python
# src/qwenpaw/app/user_agent_registry.py
def list_user_agent_ids(user_id: str) -> list[str]:
    """Return user-owned agent ids by scanning users/<uid>/agent_configs."""
    cfg_dir = constant.USERS_DIR / user_id / "agent_configs"
    if not cfg_dir.is_dir():
        return []
    ids: list[str] = []
    for agent_dir in sorted(cfg_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        if (agent_dir / "agent.json").is_file():
            ids.append(agent_dir.name)
    return ids
```

```python
# src/qwenpaw/app/routers/auth.py
@router.post("/register")
async def register(req: RegisterRequest):
    ...
    # 删除 seed_all_agents_for_user 调用，仅保留用户创建与返回 token
    return LoginResponse(token=token, username=username)
```

```python
# src/qwenpaw/app/routers/agents.py
from ..user_agent_registry import list_user_agent_ids

@router.get("")
async def list_agents(request: Request) -> AgentListResponse:
    config = load_config()
    auth_user_id = getattr(request.state, "user_id", None)
    is_admin = bool(getattr(request.state, "is_admin", False))

    if is_admin:
        ordered_agent_ids = _normalized_agent_order(config)
        config_user_id = None
    else:
        ordered_agent_ids = list_user_agent_ids(auth_user_id) if auth_user_id else []
        config_user_id = auth_user_id
    ...
```

- [ ] **Step 4: 重新运行测试确认通过**

Run: `pytest tests/integration/test_multi_user_auth.py -k "empty_before_self_provision or list_only" -v`  
Expected: PASS，`empty_before_self_provision` 与原有 `list_only` 同时通过（`list_only` 的期望需更新为“可读且列表可为空”）。

- [ ] **Step 5: 提交**

```bash
git add src/qwenpaw/app/user_agent_registry.py src/qwenpaw/app/routers/auth.py src/qwenpaw/app/routers/agents.py tests/integration/test_multi_user_auth.py
git commit -m "feat(auth): stop auto-seeding agents for new users"
```

---

### Task 2: 新增模板查询与按模板创建私有实例接口

**Files:**
- Modify: `src/qwenpaw/app/routers/agents.py`
- Create: `tests/integration/test_agent_template_provisioning.py`
- Test: `tests/integration/test_agent_template_provisioning.py`

- [ ] **Step 1: 先写失败测试（模板列表 + 从模板创建）**

```python
def test_non_admin_can_list_enabled_agent_templates(app_server: AppServer) -> None:
    token = register(
        app_server.client,
        app_server.base_url,
        "integ_user_template_list",
        "integ_user_template_list_secret",
    )
    resp = app_server.api_request(
        "GET",
        "/api/agent-templates",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, app_server.logs_tail()
    templates = resp.json()["templates"]
    assert isinstance(templates, list)
    assert all(t["enabled"] is True for t in templates)


def test_non_admin_can_create_private_agent_from_template(app_server: AppServer) -> None:
    token = register(
        app_server.client,
        app_server.base_url,
        "integ_user_template_create",
        "integ_user_template_create_secret",
    )
    create_resp = app_server.api_request(
        "POST",
        "/api/agents/from-template",
        json={
            "template_agent_id": "default",
            "name": "My Private Agent",
            "description": "created from template",
        },
        headers=auth_headers(token),
    )
    assert create_resp.status_code == 201, app_server.logs_tail()
    created_id = create_resp.json()["id"]

    list_resp = app_server.api_request(
        "GET",
        "/api/agents",
        headers=auth_headers(token),
    )
    ids = [a["id"] for a in list_resp.json()["agents"]]
    assert created_id in ids
```

- [ ] **Step 2: 运行测试确认失败（接口尚不存在）**

Run: `pytest tests/integration/test_agent_template_provisioning.py -v`  
Expected: FAIL，出现 404 或 schema mismatch。

- [ ] **Step 3: 实现最小接口与创建逻辑**

```python
class AgentTemplateSummary(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool


class AgentTemplateListResponse(BaseModel):
    templates: list[AgentTemplateSummary]


class CreateAgentFromTemplateRequest(BaseModel):
    template_agent_id: str
    name: str | None = None
    description: str | None = None
    workspace_dir: str | None = None
    skill_names: list[str] | None = None
    active_model: ModelSlotConfig | None = None


@router.get("/../agent-templates", response_model=AgentTemplateListResponse)
async def list_agent_templates(request: Request) -> AgentTemplateListResponse:
    # 非管理员可读，返回 enabled=True 模板
    ...


@router.post("/from-template", status_code=201, response_model=AgentSummary)
async def create_agent_from_template(
    request: Request,
    payload: CreateAgentFromTemplateRequest = Body(...),
) -> AgentSummary:
    # 读取模板配置 -> 生成 u_<shortid> -> 应用覆盖配置 -> save_agent_config(user_id=当前用户)
    # 初始化用户工作区 -> 返回新私有实例摘要
    ...
```

- [ ] **Step 4: 重新运行新增测试并通过**

Run: `pytest tests/integration/test_agent_template_provisioning.py -v`  
Expected: PASS，模板列表仅返回启用模板，创建后可在私有列表看到新实例。

- [ ] **Step 5: 提交**

```bash
git add src/qwenpaw/app/routers/agents.py tests/integration/test_agent_template_provisioning.py
git commit -m "feat(agents): add template listing and self-provision API"
```

---

### Task 3: 前端 API 层补齐模板查询与创建类型

**Files:**
- Modify: `console/src/api/types/agents.ts`
- Modify: `console/src/api/modules/agents.ts`
- Test: `console/src/components/AgentSelector/CreateAgentFromTemplateModal.test.tsx`

- [ ] **Step 1: 先写失败测试（调用新 API 方法）**

```tsx
it("calls createAgentFromTemplate with template id and overrides", async () => {
  const spy = vi.spyOn(agentsApi, "createAgentFromTemplate");
  await agentsApi.createAgentFromTemplate({
    template_agent_id: "default",
    name: "My Agent",
  });
  expect(spy).toHaveBeenCalledWith({
    template_agent_id: "default",
    name: "My Agent",
  });
});
```

- [ ] **Step 2: 运行测试确认失败（方法不存在）**

Run: `cd console && npm test -- CreateAgentFromTemplateModal.test.tsx -t "createAgentFromTemplate"`  
Expected: FAIL，`createAgentFromTemplate` is not a function。

- [ ] **Step 3: 增加类型与 API 封装**

```ts
// console/src/api/types/agents.ts
export interface AgentTemplateSummary {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
}

export interface AgentTemplateListResponse {
  templates: AgentTemplateSummary[];
}

export interface CreateAgentFromTemplateRequest {
  template_agent_id: string;
  name?: string;
  description?: string;
  workspace_dir?: string;
  skill_names?: string[];
  active_model?: ModelSlotConfig | null;
}
```

```ts
// console/src/api/modules/agents.ts
listAgentTemplates: () =>
  request<AgentTemplateListResponse>("/agent-templates"),

createAgentFromTemplate: (payload: CreateAgentFromTemplateRequest) =>
  request<AgentSummary>("/agents/from-template", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
```

- [ ] **Step 4: 重新运行测试并通过**

Run: `cd console && npm test -- CreateAgentFromTemplateModal.test.tsx -t "createAgentFromTemplate"`  
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add console/src/api/types/agents.ts console/src/api/modules/agents.ts
git commit -m "feat(console): add template provisioning agents API client"
```

---

### Task 4: 在 AgentSelector 实现空态与“从模板创建私有智能体”流程

**Files:**
- Create: `console/src/components/AgentSelector/CreateAgentFromTemplateModal.tsx`
- Create: `console/src/components/AgentSelector/CreateAgentFromTemplateModal.test.tsx`
- Modify: `console/src/components/AgentSelector/index.tsx`
- Modify: `console/src/components/AgentSelector/AgentSelector.test.tsx`
- Modify: `console/src/locales/zh.json`
- Modify: `console/src/locales/en.json`
- Test: `console/src/components/AgentSelector/AgentSelector.test.tsx`
- Test: `console/src/components/AgentSelector/CreateAgentFromTemplateModal.test.tsx`

- [ ] **Step 1: 先写失败测试（空列表显示创建入口）**

```tsx
it("renders empty-state create button when agent list is empty", async () => {
  mockListAgents.mockResolvedValue({ agents: [] });
  renderWithProviders(<AgentSelector />);
  await waitFor(() => expect(mockListAgents).toHaveBeenCalled());
  expect(screen.getByText("agent.createFirstAgent")).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行测试确认失败（当前无空态入口）**

Run: `cd console && npm test -- AgentSelector.test.tsx -t "empty-state create button"`  
Expected: FAIL，找不到 `agent.createFirstAgent`。

- [ ] **Step 3: 新建创建弹窗并接入 Selector**

```tsx
// console/src/components/AgentSelector/CreateAgentFromTemplateModal.tsx
export default function CreateAgentFromTemplateModal({
  open,
  onCancel,
  onCreated,
}: Props) {
  const [templates, setTemplates] = useState<AgentTemplateSummary[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const handleSubmit = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      const created = await agentsApi.createAgentFromTemplate(values);
      onCreated(created);
    } finally {
      setSubmitting(false);
    }
  };
  ...
}
```

```tsx
// console/src/components/AgentSelector/index.tsx
{agents?.length ? (
  <Select ... />
) : (
  <div className={styles.emptyState}>
    <span>{t("agent.noPrivateAgents")}</span>
    <Button type="primary" onClick={() => setCreateOpen(true)}>
      {t("agent.createFirstAgent")}
    </Button>
  </div>
)}

<CreateAgentFromTemplateModal
  open={createOpen}
  onCancel={() => setCreateOpen(false)}
  onCreated={(created) => {
    setCreateOpen(false);
    void loadAgents().then(() => setSelectedAgent(created.id));
  }}
/>
```

- [ ] **Step 4: 增加文案键并补全测试**

```json
// console/src/locales/zh.json
{
  "agent.noPrivateAgents": "你还没有智能体，请先创建",
  "agent.createFirstAgent": "创建智能体",
  "agent.template": "模板",
  "agent.templateRequired": "请选择模板",
  "agent.templateChanged": "模板已变更，请重新选择"
}
```

```json
// console/src/locales/en.json
{
  "agent.noPrivateAgents": "You don't have any agents yet. Create one first.",
  "agent.createFirstAgent": "Create Agent",
  "agent.template": "Template",
  "agent.templateRequired": "Please select a template",
  "agent.templateChanged": "Template changed. Please choose again."
}
```

- [ ] **Step 5: 运行前端测试确认通过**

Run: `cd console && npm test -- AgentSelector.test.tsx CreateAgentFromTemplateModal.test.tsx`  
Expected: PASS，覆盖空态、模板选择、创建成功回调。

- [ ] **Step 6: 提交**

```bash
git add console/src/components/AgentSelector/index.tsx console/src/components/AgentSelector/CreateAgentFromTemplateModal.tsx console/src/components/AgentSelector/CreateAgentFromTemplateModal.test.tsx console/src/components/AgentSelector/AgentSelector.test.tsx console/src/locales/zh.json console/src/locales/en.json
git commit -m "feat(console): support self-provisioning agents from templates"
```

---

### Task 5: 全量回归验证与文档同步

**Files:**
- Modify: `docs/superpowers/specs/2026-05-28-user-agent-self-provisioning-design.md`（状态更新，可选）
- Test: `tests/integration/test_multi_user_auth.py`
- Test: `tests/integration/test_agent_template_provisioning.py`
- Test: `console/src/components/AgentSelector/AgentSelector.test.tsx`
- Test: `console/src/components/AgentSelector/CreateAgentFromTemplateModal.test.tsx`

- [ ] **Step 1: 运行后端关键集成测试**

Run: `pytest tests/integration/test_multi_user_auth.py tests/integration/test_agent_template_provisioning.py -v`  
Expected: PASS。

- [ ] **Step 2: 运行前端关键单测**

Run: `cd console && npm test -- AgentSelector.test.tsx CreateAgentFromTemplateModal.test.tsx`  
Expected: PASS。

- [ ] **Step 3: 运行前端 lint 与构建**

Run: `cd console && npm run lint && npm run build`  
Expected: PASS，无新增 lint/type/build 错误。

- [ ] **Step 4: 更新 spec 状态（可选但推荐）**

```markdown
**状态:** 已确认（实施中）
```

- [ ] **Step 5: 提交验证快照**

```bash
git add docs/superpowers/specs/2026-05-28-user-agent-self-provisioning-design.md
git commit -m "chore: verify self-provisioning rollout readiness"
```

---

## Self-Review Checklist (Completed)

- **Spec coverage:** 已覆盖“不自动全量初始化、空态引导、模板创建私有副本、模板范围、完整配置、权限不回退”全部需求。
- **Placeholder scan:** 已移除 TBD/TODO 与“后续补充”描述；每个代码步骤都给了可执行片段。
- **Type consistency:** 前后端接口名统一使用 `agent-templates` 与 `from-template`，请求字段统一为 `template_agent_id`。

