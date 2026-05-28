# 多用户数据隔离设计

**日期:** 2026-05-28  
**状态:** 已通过  
**方案:** 用户目录统一隔离（方案 1）

---

## 1. 目标与范围

### 1.1 目标

在 QwenPaw 中实现多用户数据隔离：不同登录用户拥有独立的 Agent 配置、运行时数据、Channel 绑定与 Inbox；同时保留一组全局共享的 Settings 资源，由管理员统一维护。

### 1.2 认证要求

- **移除** 环境变量 `QWENPAW_AUTH_ENABLED`；认证**始终启用**。
- 无注册用户时，仅允许访问认证相关 API；其余 API 返回 `401`。
- 首个注册用户为 **admin**（`is_admin: true`），后续用户为普通用户。

### 1.3 隔离范围

**按用户隔离（必须）：**

| 区域 | 页面/能力 |
|------|-----------|
| 对话 | Chat、Coding |
| 收件箱 | Inbox |
| Control | Channels、Sessions、Cron Jobs、Heartbeat |
| Agent | Workspace、Skills、Tools、MCP、ACP、Agent Config、Agent Stats |

**全局共享（不按用户隔离）：**

| # | Settings 项 |
|---|-------------|
| 1 | 智能体管理（Agent 列表与模板） |
| 2 | 模型管理 |
| 3 | 技能池 |
| 4 | 技能市场 |
| 5 | 环境变量 |
| 6 | 安全 |
| 7 | Token 消耗 |
| 8 | 备份 |
| 9 | 语音转写 |
| 10 | 调试 |
| 11 | 插件管理 |

**权限：** 仅 admin 可修改上述 11 项；普通用户只读。

### 1.4 已确认的产品决策

| 决策点 | 选择 |
|--------|------|
| Agent 配置 | 所有用户共享 Agent **列表**；每个用户对每个 Agent 有独立 `agent.json` 副本 |
| Agent 同步 | **C**：新增 Agent 时为所有用户 seed；删除时清理；全局模板后续修改不覆盖用户副本 |
| Channels | 每用户独立配置（独立 Bot Token / Webhook） |
| Settings 权限 | 仅首个注册用户（admin）可写 |
| 认证开关 | 去掉 `QWENPAW_AUTH_ENABLED`，默认必须登录 |

### 1.5 非目标（本次不做）

- 多实例 / 跨节点用户数据同步
- OAuth / SSO
- 细粒度 RBAC（除 admin 外）
- Channel Token 全局去重或互斥校验

---

## 2. 架构概览

### 2.1 两层配置模型

```
全局层（Admin 可写）
├── config.json              # Agent 列表 registry、active_agent
├── agents/<id>/agent.json   # 全局模板
├── agents/<id>/workspace/   # 模板工作区文件
└── Settings 11 项资源       # models, skill_pool, envs, ...

用户层（每用户独立）
└── users/<user_id>/
    ├── agent_configs/<agent_id>/agent.json
    ├── agent_data/<agent_id>/          # chats, sessions, jobs, memory...
    ├── agent_workspaces/<agent_id>/    # coding 项目
    ├── inbox_events.json
    └── inbox_traces/
```

- **全局层** 决定 Agent 是否存在及默认模板。
- **用户层** 决定该用户如何使用各 Agent（配置 + 运行时 + Channel）。

### 2.2 目录结构（最终态）

```
~/.qwenpaw/   # WORKING_DIR
├── config.json
├── settings.json
├── skill_pool/
├── models/
├── token_usage.json
├── agents/<agent_id>/
│   ├── agent.json                 # 全局模板
│   └── workspace/                 # 模板工作区
└── users/<user_id>/
    ├── agent_configs/<agent_id>/
    │   └── agent.json
    ├── agent_data/<agent_id>/
    ├── agent_workspaces/<agent_id>/
    ├── inbox_events.json
    └── inbox_traces/
```

> Channels 配置位于 per-user `agent.json` 的 `channels` 字段，不单独使用 `channels.json` 文件，避免双源。

### 2.3 请求数据流

```
Client (JWT: user_id, is_admin)
  → AuthMiddleware (始终校验，公开路径除外)
  → require_admin (仅 Settings 写 API)
  → get_agent_for_request(request)
       → MultiAgentManager.get_agent(agent_id, user_id)
       → Workspace(user_id) → data_dir = users/<uid>/agent_data/<id>/
       → load_agent_config(agent_id, user_id=...)
  → 响应仅含当前用户数据
```

---

## 3. Agent 生命周期（策略 C）

| 事件 | 行为 |
|------|------|
| 新用户注册 | `seed_all_agents_for_user(user_id)`：为所有已有 Agent 复制模板到 `agent_configs/`，创建必要目录 |
| Admin 新增 Agent | `seed_user_for_all_users(agent_id)`：为每个已有用户 seed 一份；已存在则跳过 |
| Admin 修改全局模板 | **不**覆盖任何用户已有 `agent.json` |
| Admin 删除 Agent | `purge_agent_for_all_users(agent_id)`：删除所有用户下该 Agent 的 configs/data/workspaces；`MultiAgentManager` evict 缓存 |
| 用户首次访问缺失副本 | 懒 seed（异常恢复），从全局模板复制 |

---

## 4. 后端设计

### 4.1 配置加载 API 变更

**文件:** `src/qwenpaw/config/config.py`

```python
def resolve_agent_config_path(agent_id: str, user_id: str | None = None) -> Path:
    """user_id=None → 全局模板；否则 → USERS_DIR/<user_id>/agent_configs/<agent_id>/agent.json"""

def load_agent_config(agent_id: str, *, user_id: str | None = None) -> AgentProfileConfig: ...

def save_agent_config(agent_id: str, config: AgentProfileConfig, *, user_id: str | None = None) -> None: ...
```

| 调用场景 | `user_id` |
|----------|-----------|
| Agent 分组路由（skills, tools, mcp, channels, cron, workspace...） | `request.state.user_id` |
| Settings `/api/agents` CRUD | `None`（全局模板） |
| Channel Manager / Workspace 启动 | `workspace.user_id` |
| CLI 无 HTTP 上下文 | 显式传参；管理命令用 admin 或指定 user |

- 配置缓存 key：`(agent_id, user_id or "")`。
- 所有现有 `load_agent_config(agent_id)` 调用点需审计：Agent 域 API 必须传 `user_id`。

### 4.2 用户 Agent Registry（新模块）

**文件:** `src/qwenpaw/app/user_agent_registry.py`（建议）

| 函数 | 说明 |
|------|------|
| `seed_agent_for_user(user_id, agent_id)` | 从全局模板复制 `agent.json` 及必要 workspace 文件 |
| `seed_all_agents_for_user(user_id)` | 注册后调用 |
| `seed_user_for_all_users(agent_id)` | Admin 创建 Agent 后调用 |
| `purge_agent_for_all_users(agent_id)` | Admin 删除 Agent 后调用 |
| `ensure_user_agent_copy(user_id, agent_id)` | 懒 seed，供 get_agent 兜底 |

**挂载点:**

- `POST /api/auth/register` → `seed_all_agents_for_user`
- `POST /api/agents` → `seed_user_for_all_users` + `require_admin`
- `DELETE /api/agents/{id}` → `purge_agent_for_all_users` + `require_admin`

### 4.3 MultiAgentManager 与 Workspace

**现状（保留并完善）:**

- 缓存 key：`f"{agent_id}:{user_id}"`
- `Workspace(user_id=...)` → `data_dir = USERS_DIR/<user_id>/agent_data/<agent_id>/`
- `get_coding_dir()` → `USERS_DIR/<user_id>/agent_workspaces/<agent_id>/`

**需补全:**

- `get_agent()` 在 user 副本缺失时调用 `ensure_user_agent_copy`
- `load_agent_config` 在 Workspace 内使用 `workspace.user_id`

### 4.4 认证模块变更

**文件:** `src/qwenpaw/app/auth.py`, `routers/auth.py`

- 删除 `is_auth_enabled()` 及 `QWENPAW_AUTH_ENABLED` 读取。
- `AuthMiddleware`：除 `_PUBLIC_PATHS` 外一律要求有效 token。
- `auth.json` 用户记录增加 `is_admin: bool`；首个注册用户 `is_admin=true`。
- JWT payload 或 verify 响应包含 `is_admin`。
- Middleware 设置 `request.state.is_admin`。

**公开路径（保持）:**

- `/api/auth/login`, `/register`, `/status`, `/verify`
- `/api/version`, `/api/settings/language`, `/api/frontend_plugin/`
- 静态资源前缀

### 4.5 Admin 守卫

**文件:** `src/qwenpaw/app/auth.py` 或 `deps.py`

```python
def require_admin(request: Request) -> None:
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin only")
```

**需加 `require_admin` 的写 API（示例）:**

- `/api/agents` — POST, PUT, DELETE, reorder
- `/api/models`, `/api/providers` — 写操作
- `/api/skill-pool`, `/api/market` — 写操作
- `/api/envs` — 写操作
- `/api/security` — 写操作
- `/api/backups` — 写操作
- `/api/voice-transcription` — 写操作
- `/api/debug` — 写操作
- `/api/plugins` — 管理类写操作

读 API 对所有已登录用户开放。

### 4.6 Inbox

**文件:** `src/qwenpaw/app/inbox_store.py`, `inbox_trace_store.py`

- **修复 bug:** `_load_events` 必须使用 `_get_user_inbox_path(user_id)` 读取，而非 `_INBOX_PATH`。
- 所有 `append_event` / `list_events` 调用方传入 `workspace.user_id`（heartbeat、cron、console router）。
- Legacy 全局 `WORKING_DIR/inbox_events.json` 仅用于迁移。

### 4.7 Console Chat 会话绑定

- Console channel 的 `sender_id` 使用 auth `user_id`（建议格式：`console:<user_id>`）。
- 避免多用户共用 `"default"` sender，导致会话串线。

### 4.8 ContextVar

**文件:** `src/qwenpaw/config/context.py`

- 在 agent runner 入口调用 `set_current_user_id(workspace.user_id)`。
- 无 Request 的工具/后台逻辑通过 ContextVar 获取 `user_id`。

### 4.9 Channel 隔离

- Channels 存于 per-user `agent.json` → 每用户独立 Channel Manager。
- Manager 按 `(user_id, agent_id)` 或 `workspace` 实例缓存。
- Admin 修改全局模板不影响已运行用户 Channel，直至用户自行重启/重载。

### 4.10 内存态隔离

| 组件 | 改造 |
|------|------|
| `console_push_store` | 按 `user_id` 分桶；WebSocket 推送仅发给对应用户连接 |
| `approval_service` | 审批队列按 `user_id` 隔离 |

---

## 5. 前端设计

### 5.1 认证

- 移除对 `auth/status.enabled` 的分支；`AuthGuard` 始终要求 token。
- `verify` 后持久化：`qwenpaw_user_id`, `qwenpaw_is_admin`（localStorage）。
- 401 拦截 → 清 token → `/login?redirect=...`。

### 5.2 Settings 只读 UI

- 非 admin：`is_admin === false` 时，Settings 11 项表单 disabled，隐藏创建/删除/保存按钮。
- 顶部 Banner：「仅管理员可修改全局设置」。
- 403 响应友好提示。

### 5.3 Agent 分组

- 路由与组件无需按用户分叉；后端按 JWT `user_id` 返回数据。
- Agent Stats 展示当前用户 `agent_data` 统计（与全局 Token Usage 区分）。

### 5.4 API 类型

```typescript
interface VerifyResponse {
  valid: boolean;
  username: string;
  user_id: string;
  is_admin: boolean;
}
```

**文件:** `console/src/api/config.ts`, `console/src/api/modules/auth.ts`

---

## 6. 数据迁移

### 6.1 触发条件

启动时检测 legacy 布局：

- `WORKING_DIR` 下存在全局 `chats.json` 或 legacy inbox，且 `USERS_DIR` 几乎为空。

### 6.2 迁移规则

目标用户：首个 admin 的 `user_id`（若尚无用户，需先完成注册）。

| Legacy | 目标 |
|--------|------|
| 全局/模板 `agent_data/<id>/` | `users/<admin_id>/agent_data/<id>/` |
| 模板 workspace 文件 | `users/<admin_id>/agent_workspaces/<id>/` |
| 全局 `agents/<id>/agent.json` | `users/<admin_id>/agent_configs/<id>/agent.json`（若不存在） |
| `inbox_events.json` | `users/<admin_id>/inbox_events.json` |

- 迁移完成后写入 `.migrated` 标记，避免重复执行。
- Legacy 文件保留为备份，不自动删除。

### 6.3 CLI

可选：`qwenpaw migrate-users` 命令，供手动触发与 doctor 检查。

---

## 7. 测试策略

| 层级 | 用例 |
|------|------|
| 单元 | `user_agent_registry` seed/purge；`load_agent_config(user_id)` 路径；inbox `_load_events` 用户路径；`require_admin` |
| 集成 | 用户 A/B 互不可见配置；admin 新增 Agent 后 B 自动有副本；非 admin 写 Settings 返回 403 |
| 集成 | 认证关闭分支已移除；无 token 返回 401 |
| E2E | 注册 admin → 注册 user B → 各自改 skills → 互不影响 |

**测试环境:** 集成测试不再设置 `QWENPAW_AUTH_ENABLED=false`；使用 fixture 创建测试用户与 token。

---

## 8. 关键文件清单

| 文件 | 变更类型 |
|------|----------|
| `src/qwenpaw/app/auth.py` | 移除 auth 开关；admin 字段；middleware 始终开启 |
| `src/qwenpaw/app/routers/auth.py` | 注册 seed；verify 返回 is_admin |
| `src/qwenpaw/app/user_agent_registry.py` | **新建** seed/purge |
| `src/qwenpaw/config/config.py` | `load/save_agent_config` 支持 user_id |
| `src/qwenpaw/app/agent_context.py` | 贯通 user_id；ContextVar |
| `src/qwenpaw/app/multi_agent_manager.py` | ensure copy；evict by user |
| `src/qwenpaw/app/inbox_store.py` | 修复 _load_events bug |
| `src/qwenpaw/app/routers/agents.py` | admin only 写；seed/purge hooks |
| `src/qwenpaw/app/routers/*.py` | Agent 域传 user_id；Settings 写加 admin |
| `src/qwenpaw/constant.py` | USERS_DIR（已有） |
| `console/src/api/config.ts` | user_id, is_admin 存储 |
| `console/src/App.tsx` | 始终 AuthGuard |
| `console/src/layouts/Sidebar.tsx` | admin UI |
| Settings 页面 | 只读模式 |
| `tests/integration/conftest.py` | 移除 AUTH_ENABLED=false |
| 文档 | 删除 QWENPAW_AUTH_ENABLED 说明 |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `load_agent_config` 调用点遗漏 | grep 审计 + 集成测试覆盖主要路由 |
| 后台任务未传 user_id | workspace.user_id 强制；ContextVar 兜底 |
| 迁移数据丢失 | 不删除 legacy；`.migrated` 标记；CLI 手动迁移 |
| 多用户同 Bot Token | 文档说明；不强制互斥 |
| WIP 代码 inbox bug | 本需求第一批修复 |

---

## 10. 验收标准

1. 启用认证后，未登录访问 `/api/*`（除公开路径）返回 401。
2. 用户 A 修改 Agent Config / Skills / Channels，用户 B 不可见。
3. Admin 在 Settings 新增 Agent 后，所有已有用户自动获得独立副本。
4. Admin 删除 Agent 后，所有用户对应数据被清理。
5. 非 admin 无法修改 Settings 11 项（API 403 + UI disabled）。
6. Settings 11 项对所有登录用户只读可见且内容一致。
7. Inbox、Chat、Coding、Sessions 按用户隔离。
8. 无 `QWENPAW_AUTH_ENABLED` 环境变量及代码引用。
