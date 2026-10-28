# P1 前端设计：我的报告 / 报告删除 / 游客认领 / 登录设备

> 状态：`implemented`（前端已实现；后端接口已完成本地联调）
> 最后更新：2026-10-25
> 适用范围：`PersonalityMatrixFE/pro-v3-dp`
> 关联文档：
> - 后端设计：[p1_reports_sessions_design_be.md](./p1_reports_sessions_design_be.md)
> - 账号 MVP 需求：[user_account_mvp_requirements_fe.md](./user_account_mvp_requirements_fe.md)
> - 账号 MVP 设计：[user_account_mvp_design_fe.md](./user_account_mvp_design_fe.md)
> - 系统架构：[docs/design/architecture.md](../../design/architecture.md)
>
> 事实源：代码与配置 > 系统架构 > PRD > `docs/ref/`。本文是 P1 功能设计，实施后以代码为准。

---

## 一、目标

把 P0 已具备的“账号 + 报告归属 + 会话”变成用户可用、可管理的能力：

1. 登录后可看到自己的报告列表（自测 + 第三人），支持筛选、分页、打开、删除。
2. 账号页展示最近报告摘要和登录设备。
3. 支持撤销指定设备、退出其他设备、撤销当前设备。
4. 匿名状态产生的报告，在登录/注册后凭本机 `report_key` 自动认领。
5. 不破坏 P0 语义：匿名答题、报告分享键、登出不自动清除报告访问键。
6. 6 语言覆盖，账号子页保持 CSR + `noindex`、不进 sitemap、不加载广告。

---

## 二、范围

### 2.1 包含

- 新增 `/{lang}/account/reports` 独立报告页。
- 账号页新增“最近报告”摘要卡片。
- 账号页会话卡片升级为“登录设备”卡片。
- 报告软删除、认领会话、设备撤销。
- 登录/注册后后台认领本机匿名报告。
- 新增 6 语言 `auth.reports.*` / `auth.sessions.*` 文案。
- 路由、sitemap、PRD、架构、CHANGELOG 同步。

### 2.2 不包含

- 报告恢复、物理删除、自动清理任务。
- `report_key` 轮换/吊销、注册用户分享管理。
- 报告重命名、收藏、标签。
- 独立 `reports` 表重构。
- 邮箱验证、找回密码、第三方登录、账号注销/导出。
- Access Token 即时黑名单（撤销会话后最多 15 分钟残留）。

---

## 三、与现有架构的一致性

| 现有约定 | P1 做法 |
|---|---|
| 账号页 `/{lang}/account` 为 CSR 私有页 | 新增的 `/{lang}/account/reports` 同样 CSR + `noindex` |
| 内容页预渲染 | 报告页/账号子页不预渲染、不进 sitemap，不影响内容页 |
| API 统一 `apiFetch` + `auth:'required'` | 报告/会话接口全部走 `apiFetch`，401 自动 refresh 重试 |
| 错误信封 `{code,message}` | 新接口统一由 `apiFetch` 归一化为 `ApiError` |
| 删除/退出使用二次确认 | 报告删除、设备撤销、退出其他设备使用 `window.confirm` |
| 6 语言 UI 文案在 `locales/*.json` | 新增 `auth.reports` / `auth.sessions` |
| 不新增运行时内容 API | 只新增账号域运行时接口，博客/职业/关系仍构建期 JSON |
| 登出不自动清理报告键 | 保留；P1 不改变该语义 |

---

## 四、路由与渲染

### 4.1 新增路由

| 路由 | 渲染 | 说明 | 收录 |
|---|---|---|---|
| `/{lang}/account/reports` | CSR（`ssr:false`） | 我的报告列表，需登录 | 否 |
| `/account/reports` | CSR 语言跳转存根 | 按浏览器/账号语言跳转 | 否 |

- 在 `nuxt.config.ts` 为 6 语言 + 无前缀显式配置 `ssr:false` 与 `X-Robots-Tag: noindex, nofollow`。
- sitemap `exclude` 增加：
  - `/account/reports`
  - `/**/account/reports`
- 不加入 `prerender:routes`。
- 页面内 `useHead` 输出本地化 title/description、canonical、`robots: noindex, nofollow`。

### 4.2 账号页结构

保留现有资料、安全、本机数据、退出登录，新增：

```text
账号设置
├─ 个人资料
├─ 账号安全
├─ 最近报告（P1，limit=3）
├─ 本机数据（P0）
└─ 登录设备（P1，替换原“会话”卡片）
```

- 最近报告卡失败不阻塞账号页其他模块。
- 登录设备卡自行 loading/error，不阻塞资料/安全。
- 退出登录保留在设备卡片中，继续使用 P0 的 `auth.logout()`。

---

## 五、API 封装

新增 `composables/useAccountApi.ts`，避免把报告/会话领域逻辑塞进 `useAuthApi`。

### 5.1 类型

```ts
export interface ReportListItem {
  report_id: number
  perspective: 'self' | 'third_person'
  survey_id: number
  survey_name?: string
  question_count: number
  target_role?: string
  target_role_label?: string
  result_type: string
  confidence: number
  duration_ms: number
  result_available: boolean
  created_at: string
}

export interface ReportListData {
  items: ReportListItem[]
  next_cursor?: number
  has_more: boolean
}

export interface SessionItem {
  session_id: string
  current: boolean
  user_agent: string
  ip_masked: string
  last_used_at: string
  expires_at: string
}

export interface SessionListData {
  items: SessionItem[]
  has_more: boolean
}
```

### 5.2 方法

```ts
listMyReports(params: {
  limit?: number
  cursor?: number
  perspective?: 'self' | 'third_person'
  lang?: string
}): Promise<ReportListData>

deleteMyReport(reportId: number): Promise<{ report_id: number }>

claimReports(items: { report_id: number; report_key: string }[]): Promise<{
  claimed: number[]
  failed: number[]
}>

listSessions(): Promise<SessionListData>

revokeSession(sessionId: string): Promise<{ current: boolean }>

revokeOtherSessions(): Promise<{ revoked_count: number }>
```

- Base：`/api/v1/personality/auth`
- 全部 `apiFetch(..., { auth: 'required' })`。
- 列表 query 使用 `URLSearchParams`，空参数不发送。
- 默认 `limit=20`；报告页加载更多传 `next_cursor`。
- 删除/撤销用路径参数，`session_id` 不进 query。

---

## 六、页面与组件

### 6.1 `AccountReportRow.vue`

统一报告行组件，摘要和列表复用：

- Props：`item: ReportListItem`、`compact?: boolean`、`deletable?: boolean`、`deleting?: boolean`。
- Emits：`delete`。
- 展示：
  - 视角徽标：`自测` / `测测 Ta`。
  - 第三人额外显示 `target_role_label`；缺失时回退 `target_role` 或 `unknownRole`。
  - 有结果：`result_type` + `confidence/100` 百分比。
  - 无结果：显示 `resultUnavailable`，隐藏类型/置信度。
  - 题量：`questionCount`；第三人角色已显示时仍保留题量。
  - 用时：`duration_ms > 0` 时显示 `m:ss`，否则不显示/显示 `--`。
  - 创建时间：`Intl.DateTimeFormat(locale, { dateStyle:'medium', timeStyle:'short' })`。
  - 链接：
    - 自测 `/{lang}/report/{encodeReportId(report_id)}`
    - 第三人 `/{lang}/third-person/report/{encodeReportId(report_id)}`
- `deletable` 时显示删除按钮，点击 `emit('delete')`；父级负责确认与 API。
- `compact` 用于摘要卡片：隐藏部分次要信息，不显示删除。

### 6.2 `AccountReportsSummary.vue`

- 放在账号页资料/安全之后、本机数据之前。
- 挂载时 `listMyReports({ limit: 3, lang: locale })`。
- 独立 `loading / error / items`：
  - 加载：3 行骨架。
  - 失败：轻量错误 + 重试；不影响账号页其他卡片。
  - 空：`emptyTitle` + 去测试按钮。
- 顶部标题 + “查看全部” → `/{lang}/account/reports`。
- 监听 `mbti:reports-updated` 事件，认领完成后自动刷新。
- 不显示删除按钮（删除在独立列表页）。

### 6.3 `pages/[lang]/account/reports.vue`

布局：

```text
我的报告（h1）
├─ 返回账号设置
├─ 筛选 tabs：全部 / 自测 / 测测 Ta
├─ 状态提示（删除成功/失败）
├─ 报告列表（AccountReportRow）
├─ 加载更多（cursor）
└─ 空状态 / 错误 / 骨架
```

- 挂载时校验登录；未登录跳 `/{lang}/login?redirect=...`。
- 首次 `limit=20`；切换 tab 时清空列表、`cursor=undefined`、重新请求。
- 加载更多：`cursor=next_cursor`，追加；`has_more=false` 隐藏按钮。
- 删除：
  - `window.confirm(deleteConfirm)`；
  - 成功后从 `items` 移除并显示 `deleteSuccess`；
  - 失败保留行并显示 `deleteFailed`；429 可展示 `Retry-After` 提示；
  - 删除不清理本机 `report_key`（服务端已 404）。
- 空状态 CTA → `/{lang}/quiz`。
- 加载失败：保留当前列表；首次失败显示整页错误 + 重试。
- 监听 `mbti:reports-updated`，认领完成后重置并刷新列表。
- `useHead` 本地化 title/description + `noindex` + canonical。

### 6.4 `AccountSessionsCard.vue`

替换账号页原“会话”卡片：

```text
登录设备
├─ 当前设备（current 徽标）
│  ├─ UA 摘要 / ip_masked / 最近活跃 / 过期时间
│  └─ 退出
├─ 其他设备列表
│  ├─ UA 摘要 / ip_masked / 最近活跃
│  └─ 退出
├─ 退出其他设备（二次确认）
└─ 退出登录
```

- 挂载时 `listSessions()`；独立 loading/error/empty。
- `current=true` 显示“当前设备”徽标。
- UA 原样截断展示（`title` 属性保留全文），不引入 UA 解析库。
- `last_used_at` / `expires_at` 使用当前 locale 格式化。
- 撤销单个设备：
  - 二次确认（当前设备用 `revokeCurrentConfirm`，其他用通用确认）；
  - `revokeSession(session_id)`；
  - `current=false`：从列表移除，显示成功提示；
  - `current=true`：`auth.logout()` 清理本地会话 → 跳 `/{lang}/login`。
- 退出其他设备：
  - `window.confirm(revokeOtherConfirm)`；
  - 成功后只保留 `current` 项，显示成功提示。
- `has_more=true` 显示“仅显示最近 50 条”提示。
- 401：`apiFetch` 自动 refresh；刷新失败后账号页会跳登录。
- 429：展示限流提示，恢复按钮可用。

### 6.5 报告/会话时间格式

新增 `utils/accountFormat.ts`：

```ts
formatDurationMs(ms: number): string   // 0 / 非法 → '--'；否则 m:ss
formatAccountDate(value: string, locale: string): string
formatConfidence(value: number): string // value/100 四舍五入 + '%'
```

- `created_at` / `last_used_at` / `expires_at` 均为 RFC3339。
- 日期格式化失败时回退原始字符串。

---

## 七、游客报告认领

### 7.1 本机报告键枚举

在 `utils/reportAccess.ts` 新增：

```ts
export interface StoredReportKey {
  reportId: number
  key: string
  scope: 'self' | 'tp'
}

export function listStoredReportKeys(): StoredReportKey[]
```

- 枚举 localStorage `mbti_report_key:<scope>:<id>`。
- 校验 key 格式；非法 key 忽略。
- 合并模块内存缓存（localStorage 不可用时的兜底）。
- 按 `reportId` 去重。

### 7.2 认领时机

- `useAuthStore.login()` 成功后；
- `useAuthStore.register()` 成功后；
- 会话初始化 `me` 成功后（覆盖刷新页面/新设备恢复场景）；
- 不阻塞登录/注册跳转：后台执行，失败静默。

### 7.3 认领实现

```text
listStoredReportKeys()
  → 按 report_id 去重
  → 每 20 条一批
  → POST /auth/reports/claim
  → 汇总 claimed
  → claimed 非空时 dispatch 'mbti:reports-updated'
```

- 忽略 `failed`，不向用户暴露归属/存在性。
- 不删除本机 key；分享链接继续有效。
- 无 key 时不请求。
- 同一时刻只允许一个认领任务（去重），避免重复请求触发限流。
- 429/400 时停止剩余批次；其他错误静默。

### 7.4 UI 刷新

- `AccountReportsSummary` 和 `account/reports` 页面监听 `mbti:reports-updated`，重新拉取。
- 若事件在页面挂载前发生，页面挂载后的首次请求自然包含已认领报告。

---

## 八、状态与错误处理

| 场景 | 处理 |
|---|---|
| 401 旧 token 无 `sid` | `apiFetch` 自动 refresh 重试；失败后账号页跳登录 |
| 404 报告/会话 | 列表移除该项；显示“不存在或无权访问”提示 |
| 400 参数错误 | 通用错误提示，不展示后端原始 message |
| 429 | 本地化限流提示 + 可重试；不自动重试 |
| 5xx/网络 | 保留当前列表，提供重试 |
| 删除失败 | 恢复/保留原行，显示错误 |
| 撤销当前设备 | 返回 `current=true` 后清理本地会话并跳登录 |
| 认领失败 | 静默忽略，不阻塞登录 |

- 不在控制台/埋点打印 `session_id`、token、`report_key`。
- 所有删除/撤销操作二次确认。

---

## 九、i18n

新增两组文案，6 语言同步：

### 9.1 `auth.reports.*`

- `title`、`subtitle`、`backToAccount`
- `tabs.all`、`tabs.self`、`tabs.thirdPerson`
- `selfLabel`、`thirdPersonLabel`、`unknownRole`
- `questionCount`、`duration`、`createdAt`
- `confidence`
- `view`、`delete`、`deleteConfirm`、`deleteSuccess`、`deleteFailed`
- `emptyTitle`、`emptyDesc`、`goTest`
- `loadMore`、`loading`、`loadFailed`、`retry`
- `resultUnavailable`
- `summaryTitle`、`viewAll`

### 9.2 `auth.sessions.*`

- `title`、`desc`
- `current`、`other`
- `lastActive`、`expiresAt`
- `revoke`、`revokeCurrentConfirm`、`revokeOtherConfirm`
- `revokeSuccess`、`revokeFailed`
- `revokeOthers`、`revokeOthersSuccess`
- `empty`、`unknownDevice`
- `loadFailed`、`retry`、`hasMore`

- 第三人角色优先使用后端 `target_role_label`（`lang` 已传当前 locale）；缺失时用 `target_role` 或 `unknownRole`。
- 日期使用 `Intl.DateTimeFormat`，不新增语言包。

---

## 十、测试与验收

### 10.1 后端联调（已通过）

已验证：

- 报告列表、`perspective` 筛选、分页字段；
- 删除报告幂等、删除后 token/key 读取 404；
- 游客报告认领、认领后出现在列表；
- 会话列表 `current` 标记、单设备撤销、撤销后 refresh 401；
- `revoke-others` 只保留当前设备。

### 10.2 前端手工验收

| # | 场景 | 期望 |
|---|---|---|
| 1 | 登录后打开账号页 | 显示最近 3 条报告 + 设备列表 |
| 2 | 打开“我的报告” | 自测/第三人混排，筛选、分页可用 |
| 3 | 删除报告 | 二次确认；成功后列表移除；打开返回无权限 |
| 4 | 删除后刷新页面 | 报告不再出现 |
| 5 | 两台设备登录 | 设备列表显示两条，当前设备有徽标 |
| 6 | 撤销另一台设备 | 该设备 refresh 失败，列表移除 |
| 7 | 退出其他设备 | 保留当前设备，其他全部失效 |
| 8 | 撤销当前设备 | 本地会话清理，跳登录 |
| 9 | 匿名测试后注册 | 本机 report_key 被认领，报告出现在列表 |
| 10 | 认领失败/无效 key | 静默忽略，不阻塞登录 |
| 11 | 6 语言 | 报告页、设备卡片、角色文案完整 |
| 12 | 429 | 显示提示，不自动重试 |
| 13 | 401 旧 token | 自动 refresh 后会话接口成功 |
| 14 | 移动端 | 报告列表/设备卡片无横向滚动 |

### 10.3 构建与冒烟

```bash
npm run build
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/en/account/reports
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/zh-CN/account
```

检查：

- 账号子页 `X-Robots-Tag: noindex, nofollow`；
- sitemap 不含 `/account/reports`；
- 内容页仍预渲染。

---

## 十一、上线与回滚

1. 后端迁移与发布（已完成本地联调）。
2. 前端发布：
   - 独立报告页；
   - 账号页摘要 + 设备卡片；
   - 登录/注册后的认领流程；
   - 6 语言文案。
3. 观察报告列表/删除/会话接口错误率与 429。

回滚：

- 前端可先回滚：P1 页面不再访问，账号页恢复 P0 结构；新接口不被调用。
- 后端 `answers.deleted_at` 为兼容字段，旧前端可忽略。
- 软删除数据不会因前端回滚恢复。

---

## 十二、已知限制

- 撤销当前设备后 Access Token 最长 15 分钟仍有效。
- 报告删除为软删；数据仍保留。
- 报告列表基于 `answers`；独立 `reports` 表重构后需迁移字段。
- 会话列表最多 50 条；超过时只展示最近 50 条。
- 游客认领只处理本机保存了 `report_key` 的匿名报告；key 丢失无法认领。
- 跨设备查看报告不需要 `report_key`；跨设备分享仍需要本机 key。
- 登出不自动清除本机报告访问键（P0 语义保持不变，账号页仍可手动清除）。

---

## 十三、文件清单

新增：

```text
composables/useAccountApi.ts
components/AccountReportRow.vue
components/AccountReportsSummary.vue
components/AccountSessionsCard.vue
pages/[lang]/account/reports.vue
pages/account/reports.vue
utils/accountFormat.ts
utils/accountEvents.ts
composables/useCooldown.ts
```

修改：

```text
utils/reportAccess.ts          # listStoredReportKeys
stores/useAuthStore.ts         # 登录/注册/初始化后认领
nuxt.config.ts                 # routeRules + sitemap exclude
pages/[lang]/account/index.vue # 摘要卡片 + 设备卡片
locales/*.json                 # auth.reports / auth.sessions
requirement.md
docs/design/architecture.md
docs/design/README.md
CHANGELOG.md
```
