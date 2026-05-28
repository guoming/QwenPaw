# 普通用户无智能体管理权限设计

**日期:** 2026-05-28  
**状态:** 已确认（待实现）  
**目标:** 普通用户不可见智能体管理入口，仅保留切换智能体能力

---

## 1. 需求边界（已确认）

- 普通用户看不到“智能体管理”入口与管理操作。
- 普通用户直接访问前端路由 `/agents` 时，应返回 `403` 语义（无权限）。
- 后端 `/api/agents` 对普通用户保留只读能力，仅用于 Agent 切换与展示。
- 后端 `/api/agents*` 的写操作（POST/PUT/PATCH/DELETE）仅管理员可用，普通用户一律 `403`。

---

## 2. 设计方案（采用方案 3 的收敛版）

### 2.1 后端权限策略

- `GET /api/agents`、`GET /api/agents/{agentId}`：
  - 登录用户可访问；
  - 仅用于获取可选 Agent 列表与当前 Agent 配置展示。
- `POST /api/agents`、`PUT /api/agents/{agentId}`、`PATCH /api/agents/{agentId}/toggle`、`DELETE /api/agents/{agentId}`、`PUT /api/agents/order`：
  - 必须管理员；
  - 普通用户返回 `403`，错误信息保持 `Admin only`。

### 2.2 前端可见性与路由策略

- 侧边栏保持隐藏“智能体管理”菜单（普通用户不可见）。
- `AgentSelector` 保留下拉切换能力，但移除“管理入口”跳转按钮，防止普通用户通过组件侧路进入 `/agents`。
- `/agents` 路由增加管理员守卫：
  - 非管理员显示 `403` 视图（不重定向到 `/chat`，避免掩盖权限行为）。

### 2.3 交互与异常处理

- `GET /api/agents` 返回 `401`：走现有登录失效流程，跳转登录页。
- `GET /api/agents` 返回 `403`（异常配置场景）：前端提示无权限并保留当前页面，不导致应用崩溃。
- 非管理员触发任何管理写请求时，后端稳定返回 `403`，前端统一提示“仅管理员可操作”。

---

## 3. 影响范围

### 3.1 前端文件

- `console/src/components/AgentSelector/index.tsx`
  - 去除管理入口按钮及其跳转行为。
- `console/src/layouts/MainLayout/index.tsx`
  - 调整 `AdminOnlyRoute`：从“重定向到 `/chat`”改为“渲染 403 页面或无权限视图”。
- （可选）新增统一 403 页面组件，如 `console/src/pages/Forbidden/index.tsx`。

### 3.2 后端文件

- `src/qwenpaw/app/routers/agents.py`
  - 校验 GET 接口继续对登录用户开放；
  - 写接口全部保留/补齐 `require_admin`。
- `src/qwenpaw/app/admin_middleware.py`
  - 维持 `/api/agents*` 写操作的 admin 拦截策略，确保“后端兜底”。

---

## 4. 验收标准

1. 普通用户登录后，界面中看不到“智能体管理”入口。
2. 普通用户可正常使用 Agent 下拉选择器切换智能体。
3. 普通用户访问 `/agents`，页面显示 `403`（非跳转）。
4. 普通用户调用 `GET /api/agents` 成功（200）。
5. 普通用户调用任一 `/api/agents*` 写接口返回 `403`。
6. 管理员对 `/agents` 页面与 `/api/agents*` 写接口均可正常使用。

---

## 5. 测试计划

### 5.1 前端测试

- 路由测试：
  - admin 访问 `/agents` 可渲染管理页；
  - non-admin 访问 `/agents` 渲染 `403` 视图。
- 组件测试：
  - 普通用户 `AgentSelector` 不出现管理跳转按钮；
  - 下拉切换功能不受影响。

### 5.2 后端测试

- API 权限测试：
  - non-admin: `GET /api/agents` -> 200；
  - non-admin: `POST/PUT/PATCH/DELETE /api/agents*` -> 403；
  - admin 写接口 -> 2xx。

### 5.3 回归测试

- Chat/Coding 中基于当前 Agent 的会话创建与切换不受影响。
- 现有多用户隔离逻辑（用户维度 agent config）不回退。

---

## 6. 风险与缓解

- 风险：前端仅隐藏入口但遗漏直连路由保护。  
  缓解：`/agents` 路由强制 admin 守卫并提供 403 页面。

- 风险：后端某个写接口遗漏 admin 校验。  
  缓解：路由层 `require_admin` + `AdminWriteMiddleware` 双保险。

- 风险：误将 `/api/agents` GET 也限制为 admin，导致普通用户无法切换 Agent。  
  缓解：新增 API 权限用例，明确 GET 为“登录可读”。
