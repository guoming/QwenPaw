# 多用户数据隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现多用户数据隔离：每用户独立 Agent 配置与运行时数据，Settings 11 项全局共享且仅 admin 可写，认证始终启用。

**Architecture:** 全局 `agents/<id>/agent.json` 作模板；每用户 `USERS_DIR/<user_id>/agent_configs|agent_data|agent_workspaces` 存副本与运行时。HTTP 请求经 `AuthMiddleware` 注入 `user_id`/`is_admin`；Agent 域 API 调用 `load_agent_config(agent_id, user_id=...)`；Settings 写 API 调用 `require_admin`。

**Tech Stack:** Python 3 / FastAPI / agentscope-runtime, React + TypeScript (console), JWT (stdlib HMAC), pytest

**Spec:** `docs/superpowers/specs/2026-05-28-multi-user-isolation-design.md`

---

## File Map（职责划分）

| 文件 | 职责 |
|------|------|
| `src/qwenpaw/app/deps.py` | **新建** `get_request_user_id`, `require_admin` |
| `src/qwenpaw/app/auth.py` | 移除 auth 开关；`is_admin`；middleware 始终校验 |
| `src/qwenpaw/app/routers/auth.py` | register seed；verify 返回 admin |
| `src/qwenpaw/app/user_agent_registry.py` | **新建** seed/purge/ensure |
| `src/qwenpaw/config/config.py` | `resolve_agent_config_path`, `load/save_agent_config(user_id)` |
| `src/qwenpaw/app/multi_agent_manager.py` | ensure copy；按 user evict |
| `src/qwenpaw/app/workspace/workspace.py` | `load_agent_config(..., user_id=self.user_id)` |
| `src/qwenpaw/app/agent_context.py` | `get_coding_dir` 用 user config；ContextVar |
| `src/qwenpaw/app/inbox_store.py` | 修复 `_load_events` |
| `src/qwenpaw/app/routers/*.py` | Agent 域传 `user_id`；Settings 写加 admin |
| `src/qwenpaw/app/user_migration.py` | **新建** legacy → admin 用户目录迁移 |
| `console/src/api/config.ts` | `user_id`, `is_admin` localStorage |
| `console/src/App.tsx` | 始终 AuthGuard |
| `console/src/hooks/useIsAdmin.ts` | **新建** admin 只读 hook |
| `tests/unit/app/test_user_agent_registry.py` | **新建** |
| `tests/unit/app/test_auth_admin.py` | **新建** |
| `tests/integration/conftest.py` | auth fixture + 移除 `AUTH_ENABLED=false` |

---

### Task 1: 认证始终开启 + `is_admin` 字段

**Files:**
- Modify: `src/qwenpaw/app/auth.py`
- Modify: `src/qwenpaw/app/routers/auth.py`
- Test: `tests/unit/app/test_auth_admin.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/app/test_auth_admin.py
import json
from qwenpaw.app.auth import register_user, authenticate, is_auth_enabled, verify_token

def test_auth_always_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr("qwenpaw.app.auth.AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr("qwenpaw.app.auth.SECRET_DIR", tmp_path)
    assert is_auth_enabled() is True

def test_first_user_is_admin(tmp_path, monkeypatch):
    monkeypatch.setattr("qwenpaw.app.auth.AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr("qwenpaw.app.auth.SECRET_DIR", tmp_path)
    uid = register_user("admin", "secret123")
    data = json.loads((tmp_path / "auth.json").read_text())
    assert data["users"][0]["is_admin"] is True
    token = authenticate("admin", "secret123")
    payload = verify_token(token)
    assert payload["is_admin"] is True

def test_second_user_not_admin(tmp_path, monkeypatch):
    monkeypatch.setattr("qwenpaw.app.auth.AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr("qwenpaw.app.auth.SECRET_DIR", tmp_path)
    register_user("admin", "secret123")
    register_user("bob", "secret456")
    data = json.loads((tmp_path / "auth.json").read_text())
    assert sum(1 for u in data["users"] if u.get("is_admin")) == 1
    token = authenticate("bob", "secret456")
    assert verify_token(token)["is_admin"] is False
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd /Users/guoming/Codes/github.com/agentscope/QwenPaw && pytest tests/unit/app/test_auth_admin.py -v
```

- [ ] **Step 3: Implement auth changes**

在 `auth.py`：

1. `is_auth_enabled()` 改为始终 `return True`（或删除函数，全仓库替换为 `True`）。
2. `register_user`：若 `users` 为空则 `is_admin=True`，否则 `False`。
3. `create_token` payload 增加 `"is_admin": bool`。
4. `AuthMiddleware`：删除 `if not is_auth_enabled(): return` 分支；验证成功后设置 `request.state.is_admin = payload.get("is_admin", False)`。
5. 删除 `EnvVarLoader.get_str("QWENPAW_AUTH_ENABLED", ...)` 相关逻辑。

在 `routers/auth.py`：

1. 删除所有 `if not is_auth_enabled():` 早退。
2. `AuthStatusResponse`：`enabled` 固定 `True`（或移除字段，前端同步删）。
3. `VerifyResponse` 增加 `is_admin: bool`。

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/unit/app/test_auth_admin.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/qwenpaw/app/auth.py src/qwenpaw/app/routers/auth.py tests/unit/app/test_auth_admin.py
git commit -m "feat(auth): always-on auth with is_admin for first user"
```

---

### Task 2: `require_admin` 与 `get_request_user_id`

**Files:**
- Create: `src/qwenpaw/app/deps.py`
- Test: `tests/unit/app/test_deps.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/app/test_deps.py
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from qwenpaw.app.deps import require_admin, get_request_user_id

def _req(**state):
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    r = Request(scope)
    for k, v in state.items():
        setattr(r.state, k, v)
    return r

def test_get_request_user_id_missing():
    with pytest.raises(HTTPException) as exc:
        get_request_user_id(_req())
    assert exc.value.status_code == 401

def test_require_admin_forbidden():
    with pytest.raises(HTTPException) as exc:
        require_admin(_req(user_id="u1", is_admin=False))
    assert exc.value.status_code == 403

def test_require_admin_ok():
    require_admin(_req(user_id="u1", is_admin=True))
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/unit/app/test_deps.py -v
```

- [ ] **Step 3: Create deps.py**

```python
# src/qwenpaw/app/deps.py
from fastapi import HTTPException, Request

def get_request_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id

def require_admin(request: Request) -> None:
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin only")
```

- [ ] **Step 4: Run test — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/qwenpaw/app/deps.py tests/unit/app/test_deps.py
git commit -m "feat: add get_request_user_id and require_admin deps"
```

---

### Task 3: `load_agent_config` / `save_agent_config` 支持 `user_id`

**Files:**
- Modify: `src/qwenpaw/config/config.py`
- Test: `tests/unit/app/test_agent_config_paths.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/app/test_agent_config_paths.py
from pathlib import Path
import json
from qwenpaw.config.config import resolve_agent_config_path, load_agent_config, save_agent_config
from qwenpaw.config.config import AgentProfileConfig

def test_resolve_user_path(monkeypatch, tmp_path):
    monkeypatch.setattr("qwenpaw.constant.USERS_DIR", tmp_path / "users")
    monkeypatch.setattr("qwenpaw.constant.WORKING_DIR", tmp_path)
    p = resolve_agent_config_path("bot1", user_id="u_abc")
    assert p == tmp_path / "users" / "u_abc" / "agent_configs" / "bot1" / "agent.json"

def test_load_user_config_roundtrip(monkeypatch, tmp_path):
    # setup global template + user copy; assert load with user_id reads user file
    ...
```

（实现时补全 roundtrip：全局模板写入后，用户路径写入不同 `name` 字段，断言 `load_agent_config("bot1", user_id="u1").name` 为用户值。）

- [ ] **Step 2: Implement in config.py**

```python
def resolve_agent_config_path(agent_id: str, user_id: str | None = None) -> Path:
    from ..constant import USERS_DIR, WORKING_DIR
    from .utils import load_config
    if user_id:
        return USERS_DIR / user_id / "agent_configs" / agent_id / "agent.json"
    config = load_config()
    agent_ref = config.agents.profiles[agent_id]
    return Path(agent_ref.workspace_dir).expanduser() / "agent.json"
```

- 修改 `load_agent_config(agent_id, *, user_id=None)`：用 `resolve_agent_config_path`；缓存 key `(agent_id, user_id or "")`。
- 修改 `save_agent_config(agent_id, config, *, user_id=None)`：写入对应路径，`user_id` 时 `mkdir(parents=True)`。

- [ ] **Step 3: Run tests PASS**

```bash
pytest tests/unit/app/test_agent_config_paths.py -v
```

- [ ] **Step 4: Commit**

---

### Task 4: `user_agent_registry` seed / purge

**Files:**
- Create: `src/qwenpaw/app/user_agent_registry.py`
- Test: `tests/unit/app/test_user_agent_registry.py`

- [ ] **Step 1: Write failing tests**

覆盖：
- `seed_agent_for_user` 从全局模板复制 `agent.json`，已存在则跳过
- `seed_all_agents_for_user` 遍历 `config.agents.profiles`
- `purge_agent_for_all_users` 删除 `users/*/agent_configs|agent_data|agent_workspaces/<agent_id>`

- [ ] **Step 2: Implement**

```python
# src/qwenpaw/app/user_agent_registry.py
import shutil
from pathlib import Path
from ..constant import USERS_DIR
from ..config.utils import load_config
from ..config.config import resolve_agent_config_path

def seed_agent_for_user(user_id: str, agent_id: str) -> None:
    dest = resolve_agent_config_path(agent_id, user_id=user_id)
    if dest.exists():
        return
    src = resolve_agent_config_path(agent_id, user_id=None)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy2(src, dest)
    # create agent_data / agent_workspaces dirs
    (USERS_DIR / user_id / "agent_data" / agent_id).mkdir(parents=True, exist_ok=True)
    (USERS_DIR / user_id / "agent_workspaces" / agent_id).mkdir(parents=True, exist_ok=True)

def list_all_user_ids() -> list[str]:
    if not USERS_DIR.is_dir():
        return []
    return [p.name for p in USERS_DIR.iterdir() if p.is_dir()]

def seed_all_agents_for_user(user_id: str) -> None:
    for agent_id in load_config().agents.profiles:
        seed_agent_for_user(user_id, agent_id)

def seed_user_for_all_users(agent_id: str) -> None:
    for uid in list_all_user_ids():
        seed_agent_for_user(uid, agent_id)

def purge_agent_for_all_users(agent_id: str) -> None:
    for uid in list_all_user_ids():
        for sub in ("agent_configs", "agent_data", "agent_workspaces"):
            path = USERS_DIR / uid / sub / agent_id
            if path.is_dir():
                shutil.rmtree(path)

def ensure_user_agent_copy(user_id: str, agent_id: str) -> None:
    seed_agent_for_user(user_id, agent_id)
```

- [ ] **Step 3: Tests PASS + Commit**

---

### Task 5: 注册 / Agent CRUD 挂载 seed & purge

**Files:**
- Modify: `src/qwenpaw/app/routers/auth.py`
- Modify: `src/qwenpaw/app/routers/agents.py`

- [ ] **Step 1: register 后 seed**

在 `POST /register` 成功创建用户后：

```python
from ..user_agent_registry import seed_all_agents_for_user
seed_all_agents_for_user(user_id)
```

- [ ] **Step 2: agents 写操作加 admin + seed/purge**

```python
from ..deps import require_admin
from ..user_agent_registry import seed_user_for_all_users, purge_agent_for_all_users

@router.post("")
async def create_agent(request: Request, ...):
    require_admin(request)
    ...
    seed_user_for_all_users(new_agent_id)

@router.delete("/{agentId}")
async def delete_agent(request: Request, agentId: str, ...):
    require_admin(request)
    purge_agent_for_all_users(agentId)
    ...
```

- `GET` 列表/详情保持全员可读；`load_agent_config(agent_id)` **不带** `user_id`（读全局模板摘要）。

- [ ] **Step 3: 手动验证**

1. 注册 admin → 检查 `users/<id>/agent_configs/` 有各 agent
2. admin 创建新 agent → 第二个用户目录也出现副本

- [ ] **Step 4: Commit**

---

### Task 6: Workspace / MultiAgentManager 使用 per-user config

**Files:**
- Modify: `src/qwenpaw/app/workspace/workspace.py`
- Modify: `src/qwenpaw/app/multi_agent_manager.py`
- Modify: `src/qwenpaw/app/agent_context.py`

- [ ] **Step 1: workspace.py**

将：

```python
self._config = load_agent_config(self.agent_id)
```

改为：

```python
self._config = load_agent_config(self.agent_id, user_id=self.user_id)
```

（两处 reload 同样修改。）

- [ ] **Step 2: multi_agent_manager.get_agent**

在创建 Workspace 前：

```python
from .user_agent_registry import ensure_user_agent_copy
if user_id:
    ensure_user_agent_copy(user_id, agent_id)
```

- [ ] **Step 3: get_coding_dir**

`load_agent_config(workspace.agent_id)` → `load_agent_config(workspace.agent_id, user_id=workspace.user_id)`

- [ ] **Step 4: 运行现有 workspace 单测**

```bash
pytest tests/unit/workspace/ -v --tb=short -q
```

- [ ] **Step 5: Commit**

---

### Task 7: Agent 域 Router 批量传入 `user_id`

**Files:**
- Modify: `src/qwenpaw/app/routers/tools.py`
- Modify: `src/qwenpaw/app/routers/workspace.py`
- Modify: `src/qwenpaw/app/routers/skills.py`（及 agent-scoped 路由）
- Modify: `src/qwenpaw/app/routers/mcp.py`, `mcp_oauth.py`, `config.py`（agent 配置读写）
- Modify: `src/qwenpaw/app/routers/providers.py`（agent 槽位，非全局 models）
- Modify: `src/qwenpaw/app/routers/coding_mode.py`, `coding_project.py`
- Modify: `src/qwenpaw/app/routers/agent_stats.py`
- Modify: `src/qwenpaw/app/routers/agent_scoped.py`（channels/cron/sessions 入口）
- Modify: `src/qwenpaw/app/workspace/service_factories.py`
- Modify: `src/qwenpaw/app/runner/runner.py`, `title_generator.py`, `daemon_commands.py`

- [ ] **Step 1: 审计命令**

```bash
rg "load_agent_config\(" src/qwenpaw/app --glob '*.py' -n
```

- [ ] **Step 2: 替换规则**

| 上下文 | 调用 |
|--------|------|
| 有 `workspace` 且 `workspace.user_id` | `load_agent_config(id, user_id=workspace.user_id)` |
| 有 `request` + agent 域 | `uid = get_request_user_id(request)` 后传入 |
| Settings `/agents` 全局 CRUD | `user_id=None` |
| CLI doctor 检查模板 | `user_id=None` |

- [ ] **Step 3: save_agent_config 同步**

所有 Agent 页面对配置的保存改为 `save_agent_config(..., user_id=workspace.user_id)`。

- [ ] **Step 4: Commit**（可按 router 分子 commit）

---

### Task 8: 修复 Inbox + 后台写入 `user_id`

**Files:**
- Modify: `src/qwenpaw/app/inbox_store.py`
- Modify: `src/qwenpaw/app/inbox_trace_store.py`
- Modify: `src/qwenpaw/app/crons/heartbeat.py`
- Modify: `src/qwenpaw/app/routers/console.py`

- [ ] **Step 1: 修复 _load_events bug**

```python
def _load_events(user_id: str | None = None) -> list[dict[str, Any]]:
    path = _get_user_inbox_path(user_id)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))  # 用 path 不是 _INBOX_PATH
    ...
```

- [ ] **Step 2: 单元测试**

```python
def test_inbox_per_user_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr("qwenpaw.app.inbox_store.USERS_DIR", tmp_path)
    # append for u1 and u2, assert list for u1 does not contain u2 events
```

- [ ] **Step 3: heartbeat/cron append_event(..., user_id=workspace.user_id)**

- [ ] **Step 4: console inbox 路由已传 `request.state.user_id` — 验证 list API**

- [ ] **Step 5: Commit**

---

### Task 9: Console Chat `sender_id` + ContextVar

**Files:**
- Modify: `src/qwenpaw/app/routers/messages.py`（或 console chat 入口）
- Modify: `src/qwenpaw/config/context.py`
- Modify: `src/qwenpaw/app/runner/runner.py`

- [ ] **Step 1: messages/chat 请求**

```python
user_id = get_request_user_id(request)
sender_id = f"console:{user_id}"
```

替换默认 `"default"`。

- [ ] **Step 2: runner 入口**

```python
from ...config.context import set_current_user_id
set_current_user_id(workspace.user_id)
```

- [ ] **Step 3: Commit**

---

### Task 10: Settings 写 API 加 `require_admin`

**Files:**
- Modify: `src/qwenpaw/app/routers/providers.py`（POST/PUT/DELETE）
- Modify: `src/qwenpaw/app/routers/envs.py`
- Modify: `src/qwenpaw/app/routers/backup.py`
- Modify: `src/qwenpaw/app/routers/token_usage.py`（若有写）
- Modify: `src/qwenpaw/app/routers/market.py`
- Modify: `src/qwenpaw/app/routers/skills.py`（skill-pool 全局路径）
- Modify: `src/qwenpaw/app/routers/plugins.py`
- Modify: `src/qwenpaw/app/routers/config.py`（security 等全局配置）
- Modify: `src/qwenpaw/app/routers/voice.py`
- Modify: `src/qwenpaw/app/routers/settings.py`（若有写）

- [ ] **Step 1: 每个写 handler 首行 `require_admin(request)`**

- [ ] **Step 2: 集成测试**

```python
async def test_non_admin_cannot_create_agent(client, user_b_token):
    r = await client.post("/api/agents", json={...}, headers={"Authorization": f"Bearer {user_b_token}"})
    assert r.status_code == 403
```

- [ ] **Step 3: Commit**

---

### Task 11: Push / Approval 按用户分桶

**Files:**
- Modify: `src/qwenpaw/app/console_push_store.py`（或等效模块）
- Modify: `src/qwenpaw/app/approval_service.py`（或 routers/approval.py）

- [ ] **Step 1: push store key 改为 `user_id`**

WebSocket 连接注册时记录 `user_id`；广播仅发往匹配连接。

- [ ] **Step 2: approval 队列 dict[user_id] -> queue**

- [ ] **Step 3: Commit**

---

### Task 12: 前端认证与 admin 状态

**Files:**
- Modify: `console/src/api/config.ts`
- Modify: `console/src/api/modules/auth.ts`
- Modify: `console/src/App.tsx`
- Modify: `console/src/pages/Login/index.tsx`
- Create: `console/src/hooks/useIsAdmin.ts`

- [ ] **Step 1: config.ts**

```typescript
const USER_ID_KEY = "qwenpaw_user_id";
const IS_ADMIN_KEY = "qwenpaw_is_admin";

export function setAuthSession(token: string, username: string, userId: string, isAdmin: boolean) { ... }
export function getUserId(): string | null { ... }
export function getIsAdmin(): boolean { ... }
```

- [ ] **Step 2: Login 保存 verify/register 返回的 `user_id`, `is_admin`**

- [ ] **Step 3: App.tsx AuthGuard**

删除 `authEnabled === false` 跳过逻辑；无 token 一律 `/login`。

- [ ] **Step 4: Commit**

---

### Task 13: Settings 只读 UI

**Files:**
- Create: `console/src/components/AdminOnlyBanner.tsx`
- Modify: Settings 页面（Agents, Models, Environments, Security, TokenUsage, Backups, VoiceTranscription, Debug, PluginManager, SkillPool, Market）

- [ ] **Step 1: useIsAdmin hook**

```typescript
export function useIsAdmin(): boolean {
  return getIsAdmin();
}
```

- [ ] **Step 2: 各 Settings 页**

```tsx
const isAdmin = useIsAdmin();
<AdminOnlyBanner show={!isAdmin} />
// 所有 Button type=primary submit、Delete → disabled={!isAdmin}
```

- [ ] **Step 3: API 403 全局拦截提示（可选在 axios interceptor）**

- [ ] **Step 4: Commit**

---

### Task 14: Legacy 数据迁移

**Files:**
- Create: `src/qwenpaw/app/user_migration.py`
- Modify: `src/qwenpaw/app/_app.py`（startup hook）

- [ ] **Step 1: migrate_legacy_to_admin()**

检测 `WORKING_DIR/.user_data_migrated`；若未迁移且存在 legacy 数据：
- 找 `is_admin` 用户或首个用户
- 移动/复制 spec 6.2 表格路径
- 写标记文件

- [ ] **Step 2: startup 调用（有用户时）**

- [ ] **Step 3: 单元测试 tmp_path 迁移**

- [ ] **Step 4: Commit**

---

### Task 15: 集成测试 fixture

**Files:**
- Modify: `tests/integration/conftest.py`
- Create: `tests/integration/auth_helpers.py`

- [ ] **Step 1: 移除 `QWENPAW_AUTH_ENABLED=false`**

- [ ] **Step 2: 添加 fixture**

```python
@pytest.fixture
def admin_token(qwenpaw_server):
    # register admin, return token

@pytest.fixture
def user_b_token(qwenpaw_server):
    # register second user
```

- [ ] **Step 3: 至少一条隔离冒烟测试**

- [ ] **Step 4: Commit**

---

### Task 16: 清理文档与残留引用

**Files:**
- Modify: `README.md` / `docs/**`（若有 AUTH_ENABLED 说明）
- Modify: `src/qwenpaw/cli/app_cmd.py`, `auth_cmd.py`, `doctor_cmd.py`

- [ ] **Step 1: 全仓库 grep**

```bash
rg "QWENPAW_AUTH_ENABLED|is_auth_enabled" --glob '*'
```

- [ ] **Step 2: 删除或更新每一处**

- [ ] **Step 3: Commit**

---

## 验收检查清单（对应 Spec §10）

- [ ] 无 token → `/api/agents` 返回 401
- [ ] 用户 A/B 修改 agent-config 互不可见
- [ ] admin 新增 agent → 所有用户 `agent_configs/<id>` 存在
- [ ] admin 删除 agent → 所有用户目录清理
- [ ] 非 admin POST `/api/models` → 403
- [ ] Settings 页非 admin 按钮 disabled
- [ ] Inbox 按用户分离
- [ ] `rg QWENPAW_AUTH_ENABLED` 无结果

---

## Spec Coverage Self-Review

| Spec 章节 | Task |
|-----------|------|
| §1.2 认证始终开启 | Task 1, 16 |
| §1.3 隔离范围 | Task 6–9, 12–13 |
| §1.4 产品决策 | Task 4–5, 8–9 |
| §3 Agent 生命周期 C | Task 4–5 |
| §4.1 load_agent_config | Task 3, 7 |
| §4.4–4.5 auth/admin | Task 1–2, 10 |
| §4.6 Inbox | Task 8 |
| §4.7 Console sender | Task 9 |
| §4.8 ContextVar | Task 9 |
| §4.9 Channels | Task 6–7（per-user agent.json） |
| §4.10 Push/Approval | Task 11 |
| §5 前端 | Task 12–13 |
| §6 迁移 | Task 14 |
| §7 测试 | 各 Task 内单测 + Task 15 |
| §10 验收 | 检查清单 |

---

## 建议实施顺序

```
Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16
```

Task 7 工作量最大，可在 Task 6 后按 router 分批合并。
