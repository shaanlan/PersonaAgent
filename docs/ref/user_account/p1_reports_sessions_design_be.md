# P1 设计：我的报告 / 报告删除 / 游客报告认领 / 跨设备会话

> 状态：后端已实现，待前后端联调
> 适用范围：`PersonalityMatrix`（后端） + `PersonalityMatrixFE/pro-v3-dp`（前端）
> 关联文档：
> - 账号 MVP：`ref/user_account_mvp_design.md`
> - 后端总设计：`design.md`
> - 需求：`requirement.md`
> - 前端账号需求：`PersonalityMatrixFE/pro-v3-dp/docs/ref/user_account/user_account_mvp_requirements_fe.md`
> - 前端账号设计：`PersonalityMatrixFE/pro-v3-dp/docs/ref/user_account/user_account_mvp_design_fe.md`

---

## 1. 背景与目标

注册页文案是：

> 注册后可保存测试结果，并在不同设备上登录。

MVP 已经具备：

- 账号 + Access/Refresh Token；
- 报告按 `uid` 归属；
- 同一账号可在不同设备登录；
- 报告读取支持「本人 token」或「report_key」。

但缺少“能看见、能管理”的入口：

- 登录后没有“我的报告”列表，用户只能打开旧链接；
- 不能删除报告；
- 不能查看/下线其他登录设备；
- 注册前匿名产生的报告不会自动归属新账号。

P1 补齐这四块，让注册文案真正成立。

---

## 2. 范围

### 2.1 包含

- 我的报告列表（自测 + 第三人，游标分页、按视角筛选）
- 报告软删除
- 游客报告认领（凭 `report_key`）
- 登录设备列表
- 撤销单个设备
- 退出其他设备
- 当前设备撤销（前端清本地会话）
- `answers.deleted_at` 数据库迁移脚本与回滚
- 前端独立报告页 + 账号页报告摘要/设备卡片 + 6 语言文案

### 2.2 不包含（后续）

- 报告恢复、物理删除、自动清理任务
- `report_key` 轮换/吊销、注册用户分享管理
- 报告重命名、收藏、标签
- 独立 `reports` 表重构
- 邮箱验证、找回密码、第三方登录、账号注销/导出
- Access Token 即时黑名单（撤销会话后最长 15 分钟残留）

---

## 3. 关键决策

| # | 决策 | 取值 | 说明 |
| -- | -- | -- | -- |
| D1 | 报告删除 | 软删除 | `answers.deleted_at`，保留数据；读取统一 404 |
| D2 | 游客报告 | 支持认领 | 凭 `report_key` 证明持有，`uid=0` 才可认领 |
| D3 | 报告列表数据源 | `answers` | 暂不等待独立 `reports` 表 |
| D4 | 会话来源 | `refresh_tokens` family | 每个活跃 family 当前只有一条未撤销 token |
| D5 | 当前设备识别 | JWT `sid` claim | `sid` = refresh token `family_id` |
| D6 | 撤销当前设备 | 允许 | 返回 `current=true`，前端清本地会话 |
| D7 | 报告列表页面 | 独立页 | `/{lang}/account/reports`，账号页放摘要卡片 |
| D8 | 认领后 report_key | 保留 | 分享链接继续有效；读取仍校验归属/权限 |
| D9 | IP 展示 | 脱敏 | 列表只返回 `ip_masked`，原始 IP 仅存库 |
| D10 | 会话列表上限 | 50 | 返回 `has_more` |

---

## 4. 数据与迁移

### 4.1 `answers` 变更

```sql
ALTER TABLE `answers`
  ADD COLUMN `deleted_at` DATETIME(3) NULL COMMENT '软删除时间；NULL=未删除',
  ADD KEY `idx_uid_deleted_id` (`uid`, `deleted_at`, `id`);
```

- 旧数据 `deleted_at` 为 `NULL`，行为不变。
- 列表：`WHERE uid=? AND deleted_at IS NULL ORDER BY id DESC`
- 报告读取（自测/第三人）：增加 `AND deleted_at IS NULL`
- 删除：`UPDATE answers SET deleted_at=NOW() WHERE id=? AND uid=?`
- 不修改 `report_key_hash`；删除后带 key 读取也返回 404。

### 4.2 会话

`refresh_tokens` 不需要新增字段：

- 登录创建一个 `family_id`；
- 每次刷新轮换 token，但沿用 `family_id`，旧 token 标记 `revoked_at`；
- 活跃 family 对应一条 `revoked_at IS NULL AND expires_at > NOW()` 的记录；
- `session_id` 直接使用 `family_id`（32 位小写 hex）。

### 4.3 JWT 变更

Access Token 新增：

```json
{ "uid": 10001, "sid": "0123456789abcdef0123456789abcdef" }
```

- `sid` = 当前 Refresh Token 的 `family_id`
- 旧 Access Token 没有 `sid` 仍可用于普通鉴权
- 会话相关接口遇到无 `sid` 的 token 返回 401，前端自动 refresh 后重试（新 token 带 `sid`）
- 会话撤销后 Access Token 仍可能有效最多 15 分钟，这是已接受的 MVP 限制

### 4.4 迁移脚本

```bash
# 预检
MYSQL_PWD='...' ./scripts/upgrade_p1_report_sessions.sh \
  --host 127.0.0.1 --user root --database personality_db --dry-run

# 执行（失败自动回滚）
MYSQL_PWD='...' ./scripts/upgrade_p1_report_sessions.sh \
  --host 127.0.0.1 --user root --database personality_db --yes

# 手动回滚
MYSQL_PWD='...' ./scripts/upgrade_p1_report_sessions.sh \
  --rollback ./db_backups/p1_report_sessions_20261025_120000 --yes
```

- 脚本会备份 `answers`，加列/索引，失败自动回滚。
- 加列/索引是向后兼容的；旧后端可忽略 `deleted_at`。
- 建议低峰期执行，索引构建可能耗时。

---

## 5. 后端 API

### 5.1 通用约定

- 前缀：`/api/v1/personality/auth`
- 认证：`Authorization: Bearer <access_token>`
- 成功：`200 {"code":0,"data":...}`
- 失败：HTTP 4xx/5xx + `{"code":<http>,"message":"..."}`
- 语言：`lang` 白名单外回退 `zh-CN`
- 新接口均要求登录

| 接口 | 限流 |
| -- | -- |
| 报告列表 | 60 次/分钟/用户 |
| 删除报告 | 30 次/分钟/用户 |
| 认领报告 | 10 次/分钟/用户 |
| 会话列表 | 60 次/分钟/用户 |
| 撤销会话 | 20 次/分钟/用户 |
| 退出其他设备 | 20 次/分钟/用户 |

超限返回 `429` + `Retry-After`。

### 5.2 我的报告列表

```
GET /api/v1/personality/auth/reports?limit=20&cursor=&perspective=&lang=zh-CN
```

| 参数 | 必填 | 说明 |
| -- | :--: | -- |
| limit | ⭕ | 默认 20，最大 50 |
| cursor | ⭕ | 上一页最后一条 `report_id`；不传则从最新开始 |
| perspective | ⭕ | `self` / `third_person`；不传=全部 |
| lang | ⭕ | 用于第三人角色文案，支持 6 语言 |

响应：

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "report_id": 106,
        "perspective": "third_person",
        "survey_id": 30,
        "question_count": 10,
        "target_role": "partner",
        "target_role_label": "恋人",
        "result_type": "INTJ",
        "confidence": 7500,
        "duration_ms": 120000,
        "result_available": true,
        "created_at": "2026-10-25T16:34:51+08:00"
      },
      {
        "report_id": 105,
        "perspective": "self",
        "survey_id": 4,
        "question_count": 20,
        "result_type": "ENFP",
        "confidence": 6800,
        "duration_ms": 95000,
        "result_available": true,
        "created_at": "2026-10-25T16:34:51+08:00"
      }
    ],
    "next_cursor": 105,
    "has_more": true
  }
}
```

字段说明：

| 字段 | 类型 | 说明 |
| -- | -- | -- |
| report_id | int64 | 报告 ID（前端用现有 `encodeId` 生成路径） |
| perspective | string | `self` / `third_person` |
| survey_id | int64 | 问卷 ID |
| survey_name | string? | 有则返回；当前多数问卷可能为空，前端用 `survey_id`/题量做展示 |
| question_count | int64 | 题量（10/20/40） |
| target_role | string? | 第三人角色；自测不返回 |
| target_role_label | string? | 第三人角色本地化文案；自测不返回 |
| result_type | string | 4 字母 MBTI；结果不可用时为空字符串 |
| confidence | int32 | 置信度（约 3000~9200） |
| duration_ms | int64 | 答题用时；旧数据/无结束时间为 0 |
| result_available | bool | `result` JSON 是否可解析 |
| created_at | RFC3339 | 创建时间 |

- 排序：`report_id DESC`
- 分页：`cursor` 传上一页 `next_cursor`；`has_more=false` 时结束
- 已删除报告不会出现
- 匿名报告（`uid=0`）不会出现，除非被当前用户认领
- 结果解析失败时 `result_available=false`，不阻塞整个列表

错误：

| HTTP | message |
| -- | -- |
| 400 | `invalid limit` / `invalid cursor` / `invalid perspective` |
| 401 | `unauthorized` |
| 500 | `internal error` |

### 5.3 删除报告

```
DELETE /api/v1/personality/auth/reports/{report_id}
```

- 仅能删除自己的报告
- 已删除再删返回 200（幂等）
- 不存在 / 非本人 → 404
- 删除后：
  - 列表不再返回
  - 本人 token 读取 → 404
  - 分享 `report_key` 读取 → 404
  - `answers` 数据仍保留（软删）

响应：

```json
{ "code": 0, "data": { "report_id": 105 } }
```

错误：

| HTTP | message |
| -- | -- |
| 400 | `invalid report_id` |
| 404 | `report not found` |
| 401 | `unauthorized` |

### 5.4 游客报告认领

```
POST /api/v1/personality/auth/reports/claim
```

请求：

```json
{
  "reports": [
    { "report_id": 100, "report_key": "rk_..." }
  ]
}
```

- 每次最多 20 条
- 只认领 `uid=0`、`deleted_at IS NULL`、`report_key_hash` 匹配的报告
- 已归属当前用户的报告再次提交视为成功（幂等）
- 已归属其他用户、key 错误、已删除、不存在 → 失败
- 认领成功后保留 `report_key_hash`，分享链接继续有效
- 重复 `report_id` 自动去重

响应：

```json
{
  "code": 0,
  "data": {
    "claimed": [100, 102],
    "failed": [101]
  }
}
```

- `failed` 不返回原因，避免泄露报告归属/存在性
- 部分成功是正常结果

错误：

| HTTP | message |
| -- | -- |
| 400 | `invalid request body` / `no reports to claim` / `too many reports to claim` |
| 401 | `unauthorized` |

### 5.5 登录设备列表

```
GET /api/v1/personality/auth/sessions
```

- 只返回未撤销、未过期的活跃会话
- 当前设备通过 token 的 `sid` 识别
- 无 `sid` 的旧 token → 401；前端 refresh 后重试
- 最多返回 50 条，`has_more` 标记截断

响应：

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "session_id": "0123456789abcdef0123456789abcdef",
        "current": true,
        "user_agent": "Mozilla/5.0 ...",
        "ip_masked": "1.2.3.*",
        "last_used_at": "2026-10-25T16:34:51+08:00",
        "expires_at": "2026-11-24T16:34:51+08:00"
      }
    ],
    "has_more": false
  }
}
```

| 字段 | 说明 |
| -- | -- |
| session_id | `family_id`，32 位小写 hex；不是登录凭证 |
| current | 是否当前设备 |
| user_agent | 最近一次刷新/登录的 UA |
| ip_masked | 脱敏 IP（如 `1.2.3.*`） |
| last_used_at | 最近一次刷新/登录时间 |
| expires_at | 当前 refresh token 过期时间 |

### 5.6 撤销指定设备

```
DELETE /api/v1/personality/auth/sessions/{session_id}
```

- 仅能撤销自己的会话
- 不存在/非本人 → 404
- 返回被撤销的是否为当前设备

响应：

```json
{ "code": 0, "data": { "current": true } }
```

前端行为：

- `current=false`：从列表移除该设备
- `current=true`：清理本地会话，跳转登录页/首页
- 被撤销设备的 Refresh Token 立即失效；Access Token 最长残留 15 分钟

错误：

| HTTP | message |
| -- | -- |
| 400 | `invalid session_id` |
| 404 | `session not found` |
| 401 | `unauthorized` |

### 5.7 退出其他设备

```
POST /api/v1/personality/auth/sessions/revoke-others
```

- 撤销除当前 `sid` 外的全部活跃会话
- 当前设备保持不变

响应：

```json
{ "code": 0, "data": { "revoked_count": 2 } }
```

### 5.8 错误与前端处理

| HTTP | 场景 | 前端处理 |
| -- | -- | -- |
| 401 | 会话失效 / 旧 token 无 `sid` | `apiFetch` 自动 refresh 并重试 |
| 404 | 报告/会话不存在或无权 | 列表移除该项；toast “不存在或无权访问” |
| 400 | 参数错误 | 一般不应出现，按通用错误提示 |
| 429 | 限流 | 展示 `Retry-After` 倒计时 |
| 500 | 服务错误 | 通用错误提示，保留当前数据 |

---

## 6. 前端设计（给前端 LLM 的实现口径）

### 6.1 路由与页面

| 路由 | 渲染 | 说明 |
| -- | -- | -- |
| `/{lang}/account` | CSR | 现有账号页，新增“我的报告”摘要卡片 + “登录设备”卡片 |
| `/{lang}/account/reports` | CSR | 新增独立报告列表页 |
| `/account/reports` | CSR 跳转存根 | 检测语言后跳 `/{lang}/account/reports` |

- 两个账号子页都 `ssr:false`、`noindex, nofollow`、不进 sitemap、不加载广告。
- 在 `routeRules` 中为 6 语言显式配置。
- 账号页现有“本机数据”“退出登录”保留。

### 6.2 API 封装

建议在 `composables/useAuthApi.ts` 增加（或新建 `useAccountApi.ts`）：

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

方法：

```ts
listMyReports(params: { limit?: number; cursor?: number; perspective?: string; lang?: string }): Promise<ReportListData>
deleteMyReport(reportId: number): Promise<{ report_id: number }>
claimReports(items: { report_id: number; report_key: string }[]): Promise<{ claimed: number[]; failed: number[] }>
listSessions(): Promise<SessionListData>
revokeSession(sessionId: string): Promise<{ current: boolean }>
revokeOtherSessions(): Promise<{ revoked_count: number }>
```

统一使用：

```ts
apiFetch<T>(url, { auth: 'required', method, body })
```

> 会话接口在旧 Access Token 无 `sid` 时会返回 401；现有 `apiFetch` 会自动 refresh 并重试一次，不需要前端额外处理。

### 6.3 独立报告页 `/{lang}/account/reports`

布局建议：

```text
我的报告（h1）
├─ 返回账号设置
├─ 筛选 tabs：全部 / 自测 / 测测 Ta
├─ 报告列表
│  ├─ 类型徽标：自测 / 测测 Ta（第三人显示角色）
│  ├─ MBTI 类型 + 置信度
│  ├─ 题量/角色、答题用时、创建时间
│  ├─ “查看” → 对应报告页
│  └─ “删除” → 二次确认
├─ 加载更多（cursor）
└─ 空状态：还没有报告 → 去测试
```

展示规则：

- 自测：`自测 · {question_count} 题`
- 第三人：`测测 Ta · {target_role_label}`（使用后端本地化文案；6 语言已支持）
- `result_available=false`：显示“结果不可用”，隐藏类型/置信度，仍可删除
- `duration_ms=0`：不显示用时或显示 `--`
- 时间用 `Intl.DateTimeFormat(locale)` 格式化
- 链接：
  - 自测：`/{lang}/report/{encodeId(report_id)}`
  - 第三人：`/{lang}/third-person/report/{encodeId(report_id)}`
- 删除：
  - `window.confirm` 或设计系统 Dialog 二次确认
  - 成功后从列表移除；失败恢复并 toast
  - 删除不清理本机 `report_key`（服务端已 404，key 无影响）
- 分页：
  - 首次 `limit=20`
  - “加载更多”传 `cursor=next_cursor`
  - `has_more=false` 隐藏按钮
- 空/错误/加载状态：
  - 骨架屏加载
  - 空状态 CTA 去 `/{lang}/quiz`
  - 401 交给 `apiFetch`；刷新失败后跳登录
  - 其他错误保留现有列表并提供重试

### 6.4 账号页改动

#### 我的报告摘要卡片

- 放在资料/安全之后、本机数据之前。
- 调 `listMyReports({ limit: 3, lang: locale })`。
- 显示最近 3 条，复用报告列表项的精简版。
- 右上角“查看全部” → `/{lang}/account/reports`。
- 空状态：简短文案 + “去测试”。
- 该卡片失败不应阻塞账号页其他模块（独立 loading/error）。

#### 登录设备卡片

替换现有只有“退出登录”的会话卡片：

```text
登录设备
├─ 当前设备（当前徽标）
│  ├─ UA 摘要 / ip_masked / 最近活跃
│  └─ “退出”按钮（撤销当前设备）
├─ 其他设备列表
│  ├─ UA 摘要 / ip_masked / 最近活跃
│  └─ “退出”按钮
├─ “退出其他设备”（二次确认）
└─ “退出登录”（现有逻辑）
```

- `current=true` 的会话显示“当前设备”徽标。
- UA 可原样截断显示；无需引入 UA 解析库。
- 撤销当前设备：
  - 调 `revokeSession(session_id)`
  - 返回 `current=true` → `clearSession()` / `auth.logout()` 本地清理 → 跳登录页
- 撤销其他设备：
  - 成功后移除该行
  - `revokeOtherSessions` 成功后刷新列表或直接过滤掉非当前项
- 429 展示倒计时；404 说明会话已失效，刷新列表。

### 6.5 游客报告认领

触发时机：

- 登录成功、注册成功（自动登录）后；
- 不阻塞跳转，后台执行；
- 若当前在账号页/报告页，认领完成后刷新报告列表。

实现：

1. 在 `utils/reportAccess.ts` 增加：

```ts
export function listStoredReportKeys(): Array<{ reportId: number; key: string; scope: 'self' | 'tp' }>
```

从 `localStorage` 枚举 `mbti_report_key:<scope>:<id>`，校验 key 格式。

2. 按 `report_id` 去重，每 20 条一批调用：

```ts
claimReports(batch.map(x => ({ report_id: x.reportId, report_key: x.key })))
```

3. 忽略 `failed`，不提示用户；成功认领的报告会出现在“我的报告”。
4. 保留本机 key，不影响分享。
5. 若用户没有本机 key，不调用。

> 目的：用户在匿名状态下做完测试后注册，历史报告自动进入账号。

### 6.6 i18n

需要新增两组文案（6 语言）：

`auth.reports.*`：

- `title`、`subtitle`、`backToAccount`
- `tabs.all`、`tabs.self`、`tabs.thirdPerson`
- `selfLabel`、`thirdPersonLabel`、`questionCount`、`duration`
- `view`、`delete`、`deleteConfirm`、`deleteSuccess`、`deleteFailed`
- `emptyTitle`、`emptyDesc`、`goTest`
- `loadMore`、`loading`、`loadFailed`、`retry`
- `resultUnavailable`
- `summaryTitle`、`viewAll`

`auth.sessions.*`：

- `title`、`desc`
- `current`、`other`
- `lastActive`、`expiresAt`
- `revoke`、`revokeCurrentConfirm`、`revokeOtherConfirm`
- `revokeSuccess`、`revokeFailed`
- `revokeOthers`、`revokeOthersSuccess`
- `empty`
- `unknownDevice`

建议 zh-CN：

```json
{
  "auth": {
    "reports": {
      "title": "我的报告",
      "subtitle": "查看、打开或删除你的测试记录。",
      "tabs": { "all": "全部", "self": "自测", "thirdPerson": "测测 Ta" },
      "view": "查看",
      "delete": "删除",
      "deleteConfirm": "确定删除这份报告吗？删除后无法在列表中恢复。",
      "emptyTitle": "还没有报告",
      "emptyDesc": "完成一次测试后，结果会出现在这里。",
      "goTest": "去测试",
      "loadMore": "加载更多",
      "resultUnavailable": "结果不可用"
    },
    "sessions": {
      "title": "登录设备",
      "desc": "查看当前账号登录的设备，并退出不常用的设备。",
      "current": "当前设备",
      "lastActive": "最近活跃",
      "revoke": "退出",
      "revokeOthers": "退出其他设备",
      "revokeOtherConfirm": "确定退出其他所有设备吗？",
      "revokeSuccess": "设备已退出",
      "revokeOthersSuccess": "其他设备已退出",
      "empty": "暂无登录设备"
    }
  }
}
```

英文示例：

```json
{
  "auth": {
    "reports": {
      "title": "My reports",
      "subtitle": "View, open, or delete your test records.",
      "tabs": { "all": "All", "self": "Self", "thirdPerson": "About them" },
      "view": "View",
      "delete": "Delete",
      "deleteConfirm": "Delete this report? It cannot be restored from the list.",
      "emptyTitle": "No reports yet",
      "emptyDesc": "Your results will appear here after you finish a test.",
      "goTest": "Take a test",
      "loadMore": "Load more",
      "resultUnavailable": "Result unavailable"
    },
    "sessions": {
      "title": "Devices",
      "desc": "Review devices signed in to this account and sign out unused ones.",
      "current": "Current device",
      "lastActive": "Last active",
      "revoke": "Sign out",
      "revokeOthers": "Sign out other devices",
      "revokeOtherConfirm": "Sign out all other devices?",
      "revokeSuccess": "Device signed out",
      "revokeOthersSuccess": "Other devices signed out",
      "empty": "No active devices"
    }
  }
}
```

其余 4 语言按现有风格补齐。

### 6.7 安全与隐私

- 不在前端日志/控制台打印 `session_id`、token、report_key。
- `session_id` 不是登录凭证，但仍避免出现在 URL query；撤销用路径参数即可。
- `ip_masked` 只用于展示，不请求完整 IP。
- 删除操作二次确认。
- 认领静默失败，不向用户暴露报告归属。

---

## 7. 验收用例

### 7.1 后端 / 联调

```bash
HOST=http://localhost:8082
ACCESS=...
RID=...
RKEY=...

# 列表
curl -s "$HOST/api/v1/personality/auth/reports?limit=20" \
  -H "Authorization: Bearer $ACCESS"

# 视角筛选
curl -s "$HOST/api/v1/personality/auth/reports?perspective=third_person" \
  -H "Authorization: Bearer $ACCESS"

# 删除（幂等）
curl -s -X DELETE "$HOST/api/v1/personality/auth/reports/$RID" \
  -H "Authorization: Bearer $ACCESS"

# 删除后读取应为 404
curl -s -o /dev/null -w '%{http_code}\n' \
  "$HOST/api/v1/personality/report?report_id=$RID" \
  -H "Authorization: Bearer $ACCESS"

# 认领
curl -s -X POST "$HOST/api/v1/personality/auth/reports/claim" \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d "{\"reports\":[{\"report_id\":$RID,\"report_key\":\"$RKEY\"}]}"

# 会话
curl -s "$HOST/api/v1/personality/auth/sessions" \
  -H "Authorization: Bearer $ACCESS"

# 撤销其他设备
curl -s -X POST "$HOST/api/v1/personality/auth/sessions/revoke-others" \
  -H "Authorization: Bearer $ACCESS"
```

### 7.2 前端场景

| # | 场景 | 期望 |
| -- | -- | -- |
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
| 12 | 429 | 显示倒计时，不自动重试 |
| 13 | 401 旧 token | 自动 refresh 后会话接口成功 |

---

## 8. 上线顺序与回滚

1. 数据库迁移（`upgrade_p1_report_sessions.sh`，低峰期，先备份）。
2. 后端发布。
3. 前端发布（独立报告页、账号页卡片、认领流程）。
4. 观察错误率与 429。

回滚：

- 前端可先回滚（新接口不再调用，旧页面不受影响）。
- 后端回滚后，`answers.deleted_at` 为多余字段，旧代码忽略；可不立即回滚数据库。
- 如需回滚 DB，执行脚本 `--rollback <backup_dir>`。
- 软删除数据不会因回滚恢复；如需恢复报告，需单独 SQL。

---

## 9. 已知限制

- 撤销当前设备后，Access Token 最长 15 分钟仍有效；Refresh Token 立即失效。
- 报告删除是软删，数据仍保留；后续可加清理任务或账号注销联动。
- 跨设备查看报告不需要 `report_key`；但跨设备**分享**仍需要本机保存的 key，P1 不做 key 轮换。
- 报告列表基于 `answers`，独立 `reports` 表重构后需要迁移本设计中的字段。
- 会话列表最多 50 条；超过时只展示最近 50 条。
- 游客认领只处理本机保存了 `report_key` 的匿名报告；key 丢失无法认领。
