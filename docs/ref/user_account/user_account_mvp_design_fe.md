# 用户账号体系（MVP）前端设计

> 状态：`implemented`（前端已实现；本地联调需先执行后端迁移）
> 最后更新：2026-10-24
> 适用范围：`PersonalityMatrixFE/pro-v3-dp`
> 关联文档：
> - 前端需求：[user_account_mvp_requirements_fe.md](./user_account_mvp_requirements_fe.md)
> - 后端设计：[user_account_mvp_design_be.md](./user_account_mvp_design_be.md)
> - 系统架构：[docs/design/architecture.md](../../design/architecture.md)
> - 设计索引：[docs/design/README.md](../../design/README.md)
>
> 事实源：代码与配置 > `architecture.md` > `requirement.md` > `docs/ref/`。本文是 P0 功能设计；P1 见 [p1_reports_sessions_design_fe.md](./p1_reports_sessions_design_fe.md)。

---

## 一、设计原则

1. **不改变现有内容架构**：类型、博客、职业、关系、静态页仍是预渲染内容页；账号功能只增加私有交互页。
2. **不强制登录**：答题、报告查看、内容阅读对匿名用户保持可用。
3. **身份只来自 token**：前端不再生成或信任本地 `uid`；请求体 `uid` 仅作旧后端兼容字段，固定为 `0`。
4. **访问凭证最小暴露**：`report_key` 只存本机，只走请求头，分享时只放 URL fragment。
5. **会话对业务透明**：业务 composable 只调用统一的 `apiFetch`，不关心 token 刷新细节。
6. **失败可降级**：登录态异常不应阻断答题、交卷、内容阅读；报告无权限时给统一、可行动的提示。
7. **复用现有栈**：Nuxt 3 + Pinia + `$fetch` + Tailwind；不新增运行时内容 API、不新增重型依赖。
8. **6 语言同步**：UI 文案、错误、隐私政策、服务条款一次补齐，不做临时单语言。

---

## 二、现状与差距

| 现状 | 代码位置 | 本次设计 |
|---|---|---|
| 无会话、无用户 store | — | 新增 `utils/authSession.ts`、`stores/useAuthStore.ts`、`plugins/auth.client.ts` |
| 前端自造 `mbti_uid` 并随交卷发送 | `stores/useTestStore.ts`、`stores/useThirdPersonStore.ts`、`utils/request.ts` | 移除自造 uid；交卷改用 `apiFetch`，身份由 `Authorization` 决定 |
| 业务请求直接 `$fetch`，无统一鉴权/401 处理 | `composables/useApi.ts`、`composables/useThirdPerson.ts` | 新增 `utils/apiClient.ts`，统一注入 token、单飞刷新、错误归一化 |
| 交卷响应只有 `report_id` | `composables/useApi.ts`、`composables/useThirdPerson.ts` | 接收并持久化 `report_key` |
| 报告读取无访问凭证 | `pages/[lang]/report/[id].vue`、`pages/[lang]/third-person/report/[id].vue` | 自动带 `Authorization` / `X-Report-Key`；404 统一无权限态 |
| 分享链接就是当前 URL | `components/ReportHero.vue` | 用 `#rk=` 组装分享 URL，并在打开时自动保存、清理 |
| 有报告页但无账号页 | `pages/` | 新增 `/{lang}/login`、`/{lang}/register`、`/{lang}/account` |
| 隐私政策未覆盖账号数据 | `pages/[lang]/privacy-policy.vue`、`terms.vue` | 6 语言补充账号、会话、报告归属说明 |

---

## 三、路由与渲染矩阵

### 3.1 新增路由

| 路由 | 渲染 | 说明 | 收录 |
|---|---|---|---|
| `/{lang}/login` | CSR（`ssr:false`） | 登录页 | 否 |
| `/{lang}/register` | CSR（`ssr:false`） | 注册页 | 否 |
| `/{lang}/account` | CSR（`ssr:false`） | 账号设置，需登录 | 否 |
| `/login` | CSR 语言跳转存根 | 按浏览器语言跳转 `/{lang}/login` | 否 |
| `/register` | CSR 语言跳转存根 | 同上 | 否 |
| `/account` | CSR 语言跳转存根 | 同上；若本机有账号偏好语言则优先使用 | 否 |

- 存根沿用现有 `pages/about.vue`、`pages/report/[id].vue` 的客户端语言检测 + `navigateTo` 模式；由于账号页为 CSR，这里是客户端语言跳转而非 HTTP 301。
- 账号页不属于内容页，允许 CSR；这不违反“禁止纯 SPA”，站点整体仍是 SSR/SSG 混合。
- 未登录访问 `/{lang}/account`：
  1. 等待会话初始化；
  2. 未登录则 `navigateTo('/{lang}/login?redirect=/{lang}/account')`；
  3. 登录成功后回到 `redirect`。
- `redirect` 必须经过安全校验：只允许以 `/` 开头、不以 `//` 或 `/\` 开头的站内路径；否则回退到 `/{lang}/account`。

### 3.2 `nuxt.config.ts` 变更

```ts
routeRules: {
  // ...现有规则保持不变
  // 账号页为私有交互页，CSR；无前缀与 6 语言均不预渲染
  '/login': { ssr: false },
  '/register': { ssr: false },
  '/account': { ssr: false },
  '/zh-CN/login': { ssr: false },
  '/zh-CN/register': { ssr: false },
  '/zh-CN/account': { ssr: false },
  '/en/login': { ssr: false },
  '/en/register': { ssr: false },
  '/en/account': { ssr: false },
  // ja / ko / es / pt-BR 同理
}
```

实施注意：

- 优先使用**显式 6 语言规则**，避免 `/**/login` 之类 glob 与无前缀存根的匹配歧义。
- 不在 `prerender:routes` 中添加账号页。
- 不在 sitemap `urls()` 中添加账号页；在 `exclude` 增加：

```ts
'/login',
'/register',
'/account',
'/**/login',
'/**/register',
'/**/account',
```

- 构建后核对 `curl -I http://localhost:3000/en/login`：不应返回带账号表单内容的预渲染 HTML；页面在客户端完成渲染。
- 页面内使用 `useHead` 输出 `robots: noindex, nofollow`，canonical 指向自身。
- 账号页不使用 `AdBlock`。

---

## 四、模块设计

### 4.1 新增文件

```text
utils/authSession.ts          # token/用户缓存持久化、单飞刷新、鉴权事件
utils/apiClient.ts            # apiFetch：注入 Authorization、401 刷新重放、错误归一化
utils/reportAccess.ts         # report_key 存取、#rk 解析、分享 URL 组装
utils/safeRedirect.ts         # 站内 redirect 校验、剥离 hash
utils/authErrors.ts            # 账号错误 → i18n key / 字段映射
composables/useAuthApi.ts     # 7 个 auth 接口的类型化封装
stores/useAuthStore.ts        # 登录态、用户资料、初始化与动作
plugins/auth.client.ts        # 客户端启动时恢复会话（不阻塞首屏）
components/AuthMenu.vue       # Header 用户菜单（未登录/已登录）
components/AuthPageShell.vue  # 登录/注册页统一卡片外壳（可选）
components/AccountProfileCard.vue
components/AccountSecurityCard.vue
pages/[lang]/login.vue
pages/[lang]/register.vue
pages/[lang]/account/index.vue
pages/login.vue
pages/register.vue
pages/account/index.vue
```

### 4.2 修改文件

```text
nuxt.config.ts                          # routeRules / sitemap exclude
components/Header.vue                   # 桌面/移动账号入口
components/Footer.vue                   # 可选：账号/登录链接
components/ReportHero.vue               # 分享 URL 使用 reportAccess
composables/useApi.ts                   # apiFetch、report_key、X-Report-Key
composables/useThirdPerson.ts           # apiFetch、report_key、X-Report-Key
composables/useDualTest.ts              # 重置步骤时清理对应 report_key
stores/useTestStore.ts                  # 移除 mbti_uid / uid
stores/useThirdPersonStore.ts           # 移除 mbti_uid / uid
pages/[lang]/quiz.vue                   # 移除 initUid；交卷传 uid:0
pages/[lang]/third-person/quiz.vue      # 同上
pages/[lang]/report/[id].vue            # 清理 #rk、404 无权限态、分享参数
pages/[lang]/third-person/report/[id].vue # 清理 #rk、404 无权限态
utils/request.ts                        # 未被业务引用；移除 mbti_uid 注入或标记废弃
locales/*.json                          # auth 文案、错误、账号页
pages/[lang]/privacy-policy.vue         # 账号与数据条款
pages/[lang]/terms.vue                  # 账号服务条款
docs/design/README.md                   # 登记本功能状态
```

---

## 五、会话设计

### 5.1 存储

客户端 localStorage 键：

| 键 | 内容 |
|---|---|
| `mbti_auth_access_token` | Access JWT |
| `mbti_auth_refresh_token` | Refresh Token 明文（后端只存 hash） |
| `mbti_auth_access_expires_at` | Access 过期时间戳（毫秒） |
| `mbti_auth_user` | 最近一次 `me` / 登录返回的 user 缓存 |

规则：

- 所有读写集中在 `utils/authSession.ts`，页面与业务 composable 不直接碰 localStorage。
- SSR 阶段一律返回空会话；不得在服务端读取 localStorage。
- 用户缓存只用于首屏快速展示；启动后仍以 `GET /auth/me` 结果为准。
- localStorage 写入失败（隐私模式/配额）时降级为模块内内存存储，并保证当前标签页可用。
- 会话存储不包含密码、JWT 密钥、报告键。

```ts
export interface AuthUser {
  id: number
  email: string
  display_name: string
  lang: string
  created_at: string
}

export interface TokenPair {
  access_token: string
  token_type: 'Bearer'
  expires_in: number
  refresh_token: string
}
```

### 5.2 启动恢复

```text
plugins/auth.client.ts
  → useAuthStore().init()
      ├─ 读取 user 缓存 → 立即填充 UI（ready 仍为 false）
      ├─ access 与 refresh 都不存在 → ready=true，未登录
      ├─ access 即将过期 → refreshSession()
      ├─ GET /auth/me（apiFetch required）
      │    ├─ 200 → 更新 user 缓存，ready=true
      │    ├─ 401 → 清理会话，ready=true，未登录
      │    └─ 网络/5xx → 保留缓存会话，ready=true，展示可重试提示
      └─ 监听 storage / mbti:auth-expired / mbti:auth-updated
```

- `init()` 必须幂等，多个组件调用只执行一次。
- 插件不 `await` 初始化，避免阻塞内容页首屏；Header 用 `ready` 控制登录区占位。
- 网络失败不立即清会话，避免弱网把用户登出；只有明确 401 才清理。

### 5.3 单飞刷新

`utils/authSession.ts` 持有模块级 `refreshPromise`：

```ts
let refreshPromise: Promise<string> | null = null

export function refreshSession(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => { refreshPromise = null })
  }
  return refreshPromise
}
```

- `doRefresh()` 使用**裸 `$fetch`** 调 `/api/v1/personality/auth/refresh`，避免再次进入 `apiFetch` 造成递归。
- 成功后写入新 access + refresh，并广播 `mbti:auth-updated`。
- 401 → 清理会话并广播 `mbti:auth-expired`。
- 网络错误/5xx → 抛出错误但**不清理会话**。
- 同标签页并发请求共享同一个 `refreshPromise`；跨标签页并发由后端 10 秒宽限处理。
- 建议在请求前检查 `expires_at - now < 60_000` 时主动刷新，减少 401。

### 5.4 `apiFetch`

```ts
type AuthMode = 'none' | 'optional' | 'required'

interface ApiFetchOptions extends FetchOptions {
  auth?: AuthMode // 默认 optional
}
```

行为：

| 模式 | 使用场景 | 401 处理 |
|---|---|---|
| `none` | login / register / refresh / logout | 直接抛错，不刷新 |
| `optional` | 交卷、读报告、公开内容接口 | 尝试刷新；刷新 401 → 清会话，重试一次匿名请求 |
| `required` | me / profile / change-password | 尝试刷新；刷新 401 → 清会话并抛 401 |

- 每个请求最多刷新一次、最多重放一次，禁止无限循环。
- 请求头：
  - 有 access token → `Authorization: Bearer <token>`；
  - 报告读取由调用方额外传 `X-Report-Key`。
- 错误归一化：

```ts
class ApiError extends Error {
  status: number
  code?: number
  serverMessage?: string
}
```

  - 新 auth 接口：`{ code, message }`；
  - 旧报告接口：`{ error }`；
  - 统一转成 `ApiError`，UI 只根据 `status` / 业务 key 展示 i18n 文案，不直接展示服务端 message。
- 超时沿用现有默认（10 秒）；关系分析仍使用自身 15 秒超时。
- 不在控制台打印请求头、body 或 token。

### 5.5 跨标签页同步

- 监听 `window.storage` 事件：
  - access/refresh/user 变化 → `useAuthStore().syncFromStorage()`；
  - token 被移除 → 清空 store 用户态。
- 登出时先移除 token 再广播；其他标签页收到后切换为未登录。
- 刷新 token 后广播 `mbti:auth-updated`，其他标签页按需拉取 `me`，避免各自使用旧 access 触发后端重放检测。

### 5.6 Pinia Store

`stores/useAuthStore.ts`：

```ts
state:
  user: AuthUser | null
  ready: boolean       // 会话初始化完成
  busy: boolean        // 登录/注册/保存中
  sessionError: string | null // 网络问题等可重试错误

getters:
  isAuthenticated -> !!user
  displayName -> user.display_name || email 前缀

actions:
  init()
  syncFromStorage()
  login(email, password)
  register(payload)
  logout()
  updateProfile(patch)
  changePassword(current, next)
  refreshUser()
  clearSession()
  handleExpired()
```

- 登录/注册成功：写会话 → 设置 `user` → 写 user 缓存 → 广播。
- 登出：先本地 `clearSession()` 并清空用户态，再后台调用 logout 撤销 refresh family（失败忽略），避免网络异常导致无法退出。
- 登出不清理本机报告访问键；需要更强隐私时由账号页“本机数据”手动调用 `clearAllReportKeys()`。
- 修改密码成功：保存后端返回的新 token 对，`user` 不变。
- 修改资料成功：更新 `user` 与缓存。
- 所有 action 抛出 `ApiError` 供页面展示字段级/表单级错误。

---

## 六、API 封装

### 6.1 接口清单

Base：`/api/v1/personality/auth`

| 方法 | 路径 | 认证 | 前端封装 |
|---|---|---|---|
| POST | `/register` | 无 | `register()` 成功即登录 |
| POST | `/login` | 无 | `login()` |
| POST | `/refresh` | 无 | 仅 `authSession` 内部使用 |
| POST | `/logout` | 无 | `logout(refresh_token)` 幂等 |
| GET | `/me` | 必须 | `me()` |
| POST | `/change-password` | 必须 | `changePassword()` 返回新 token 对 |
| PATCH | `/profile` | 必须 | `updateProfile()` 返回 user |

### 6.2 请求/响应约定

- 请求体上限 1 MB；`Content-Type: application/json`。
- 成功：`{ "code": 0, "data": ... }`。
- 失败：HTTP 4xx/5xx + `{ "code": <http>, "message": "..." }`。
- 注册/登录成功数据：

```json
{
  "user": {
    "id": 10001,
    "email": "alice@example.com",
    "display_name": "Alice",
    "lang": "zh-CN",
    "created_at": "2026-10-24T12:00:00+08:00"
  },
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "3f9k..."
}
```

- 刷新只返回 token 字段；前端不得因缺少 `user` 清空本地用户，应保留当前 user。
- 登出始终 `200 { code: 0, data: null }`。
- 修改资料 `PATCH` 至少一个字段：`display_name`、`lang`。
- 昵称与语言校验在前端先做一遍，后端错误仍映射到字段。

### 6.3 错误映射

| 状态 | 业务场景 | i18n key 建议 |
|---|---|---|
| 400 | 邮箱/密码/语言/请求体非法 | `auth.errors.invalidEmail` / `invalidPassword` / `invalidRequest` |
| 401 | 登录失败 / 当前密码错误 / 会话失效 | `auth.errors.invalidCredentials` / `invalidCurrentPassword` / `sessionExpired` |
| 409 | 邮箱已注册 | `auth.errors.emailTaken` |
| 429 | 限流 | `auth.errors.rateLimited` |
| 5xx | 服务端错误 | `auth.errors.serverError` |
| 网络/超时 | 网络错误 | `auth.errors.network` |

- 登录失败统一 `invalidCredentials`，不区分邮箱不存在。
- 报告 404 使用 `report.accessDeniedTitle` / `accessDeniedDesc`，不显示后端 message。
- `Retry-After` 存在时展示倒计时；倒计时结束前禁用提交。

---

## 七、页面与组件设计

### 7.1 登录页 `pages/[lang]/login.vue`

结构：

1. 居中卡片（`max-w-md`，复用现有圆角/边框/暗色 token）。
2. 标题、说明。
3. 表单：
   - 邮箱（`type="email"`、`autocomplete="email"`）；
   - 密码（`autocomplete="current-password"`，支持显示/隐藏）；
   - 提交按钮（loading、disabled）。
4. 错误摘要（`role="alert"`）。
5. 底部：注册链接。
6. 无广告。

逻辑：

```ts
const redirect = computed(() => safeRedirect(route.query.redirect, localePath(locale.value, '/account')))
async function submit() {
  await auth.login(form.email.trim().toLowerCase(), form.password)
  await navigateTo(redirect.value)
}
```

- 已登录用户访问登录页：直接跳转 `redirect || /{lang}/account`，避免重复登录。
- 登录按钮提交期间禁用，防重复请求。
- 不展示“忘记密码”死链接；可提示通过 `/contact` 联系支持。

### 7.2 注册页 `pages/[lang]/register.vue`

- 字段：邮箱、密码、确认密码、昵称（可选）。
- 密码规则实时提示（长度 8~72 字节、不得等于邮箱）。
- 确认密码只做前端一致性校验。
- 条款说明 + `/terms`、`/privacy-policy` 链接。
- 成功自动登录并跳转 `redirect || /{lang}/account`。
- 409 展示“邮箱已注册”，提供登录链接，并保留邮箱输入。
- 已登录用户访问注册页：跳转账号页。

### 7.3 账号页 `pages/[lang]/account/index.vue`

未登录：等待 `auth.init()` → 跳转登录，`redirect` 为当前账号页。

已登录布局：

```text
账号设置（h1）
├─ 资料卡片
│  ├─ 邮箱（只读）
│  ├─ 昵称（可编辑，≤50）
│  ├─ 语言偏好（6 语言下拉）
│  ├─ 注册时间（Intl.DateTimeFormat(locale)）
│  └─ 保存按钮
├─ 安全卡片
│  ├─ 修改密码（当前 / 新 / 确认）
│  └─ 成功后提示“其他设备已退出登录”
├─ 本机数据卡片
│  ├─ 说明：浏览器保存报告访问键，登出不自动清除
│  └─ “清除本机报告访问权限”（二次确认）
└─ 会话卡片
   ├─ 当前登录账号
   ├─ 提示：登出不清理报告访问键
   └─ 退出登录
```

- 修改昵称/语言成功后就地更新 Header 显示名，不刷新页面。
- 语言偏好只写账号资料，不强制改变当前 URL locale；页面语言仍由 `/{lang}/` 决定。
- P0 账号页不展示报告列表；P1 新增“最近报告”摘要与独立 `/{lang}/account/reports`。
- 账号页提供“清除本机报告访问权限”：调用 `clearAllReportKeys()`，清除 `mbti_report_key:*` 与内存缓存；不删除服务器报告，不影响其他设备。
- 账号页不放广告，不做长内容。
- 表单错误与成功提示使用可访问的 live region。

### 7.4 Header 与 `AuthMenu.vue`

- Header 右侧工具区新增账号入口；桌面端放在语言/主题切换旁，移动端放入现有菜单与快捷入口区域。
- 未登录：显示“登录”（`:to="/{lang}/login"`）。
- 已登录：显示头像（昵称首字符）+ 昵称/邮箱下拉：
  - 账号设置 → `/{lang}/account`
  - 退出登录 → `auth.logout()`
- 未完成初始化（`ready=false`）：渲染固定尺寸占位，避免布局跳动；不渲染“已登录”内容，避免 hydration mismatch。
- 菜单支持点击外部关闭、Escape 关闭；沿用 Header 现有下拉交互方式。
- SSR 输出未登录占位；客户端恢复会话后替换。禁止在服务端读取 localStorage。

### 7.5 报告页改动

`pages/[lang]/report/[id].vue`：

1. 解码 `route.params.id`；非法仍走现有错误态。
2. 调 `adoptReportKeyFromHash('self', reportId)`：
   - 读取 `#rk=`；
   - 校验 `^rk_[A-Za-z0-9_-]{43}$`；
   - 保存；
   - `history.replaceState` 清理 fragment，保留 `?from=dual` 等 query。
3. 调 `api.fetchReport(reportId)`；`useApi` 自动带 token + `X-Report-Key`。
4. 错误分支：
   - `ApiError.status === 404` → 无权限卡片；
   - 其他 → 现有通用错误 + 重试。
5. `ReportHero` 传入数字 `reportId` 与 `reportScope="self"`，分享 URL 由 `buildReportShareUrl` 生成。

`pages/[lang]/third-person/report/[id].vue`：

1. 同样在 fetch 前 `adoptReportKeyFromHash('tp', reportId)`。
2. `useThirdPerson.fetchReport` 自动带 token + 对应 key。
3. 404 展示无权限卡片，重测按钮指向第三人测试。
4. 不新增分享 UI；页面支持 `#rk=` 手动分享。

无权限卡片内容：

- 标题：报告不存在或无权访问。
- 说明：若为分享链接，请确认链接完整；登录本人账号后可直接访问自己的报告。
- 操作：
  - 未登录 → 登录（`redirect` 为当前报告路径）；
  - 重测（自测/第三人对应入口）；
  - 可选：返回首页。
- 不展示报告 ID 是否存在、属于哪个账号等信息。

---

## 八、报告访问键设计

### 8.1 存储

`utils/reportAccess.ts`：

```ts
export type ReportScope = 'self' | 'tp'

const PREFIX = 'mbti_report_key'
const KEY_RE = /^rk_[A-Za-z0-9_-]{43}$/

// 账号页“本机数据”使用：清除全部本机报告键
clearAllReportKeys(): number

// localStorage key: mbti_report_key:{scope}:{reportId}
// 模块内 Map 作为 localStorage 不可用时的当前标签页兜底
```

导出：

```ts
saveReportKey(scope, reportId, key): void
getReportKey(scope, reportId): string | null
removeReportKey(scope, reportId): void
adoptReportKeyFromHash(scope, reportId): string | null
buildReportShareUrl({ scope, reportId, locale, query? }): string
```

规则：

- 只保存通过 `KEY_RE` 校验的 key；非法 key 忽略。
- 写入失败不抛错；内存 Map 保证当前页面分享仍可用。
- 读取时内存优先，其次 localStorage。
- 不在 URL query 中读写 key。
- 不在日志/埋点输出 key。

### 8.2 URL fragment 协议

分享链接：

```text
https://www.xiaoceshi.xyz/zh-CN/report/r2f#rk=rk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

第三人报告可保留 query：

```text
https://www.xiaoceshi.xyz/zh-CN/third-person/report/r3a?self_report=r2f&from=dual#rk=rk_...
```

打开时：

```ts
const params = new URLSearchParams(window.location.hash.slice(1))
const key = params.get('rk')
if (key && KEY_RE.test(key)) {
  saveReportKey(scope, reportId, key)
}
history.replaceState(history.state, '', window.location.pathname + window.location.search)
```

- fragment 不发送到服务端，不进入访问日志，也不通过 Referer 泄露。
- 清理 fragment 后，用户刷新页面仍可从 localStorage 取 key。
- 若浏览器/社交平台丢弃 fragment，接收者将看到无权限态；分享 UI 应尽量使用能保留 fragment 的方式，复制链接优先。
- `#rk` 使用新 key 覆盖本机旧 key。

### 8.3 `ReportHero` 分享改造

- 新增 props：

```ts
reportId?: number
reportScope?: ReportScope // 默认 'self'
```

- `shareUrl` 从 `window.location.href` 改为：

```ts
const shareUrl = computed(() => {
  if (!import.meta.client) return ''
  if (props.reportId) {
    return buildReportShareUrl({
      scope: props.reportScope || 'self',
      reportId: props.reportId,
      locale: locale.value,
    })
  }
  return window.location.href
})
```

- 复制链接、Web Share、社交分享、海报分享文本全部使用同一个 `shareUrl`。
- 无 key 时仍可分享普通 URL，但展示一次轻提示：接收者可能需要登录或重新测试。
- 不把 key 放进 `title`、`text` 或海报图片。

### 8.4 交卷与读取接入

`composables/useApi.ts`：

```ts
export interface SubmitAnswersResponse {
  code: number
  data: {
    report_id: number
    report_key?: string
  }
}
```

- `submitAnswers`：
  - 使用 `apiFetch(..., { auth: 'optional' })`；
  - 请求体保留 `uid: 0`（兼容旧后端，标记废弃）；
  - 成功后若存在 `report_key` → `saveReportKey('self', report_id, report_key)`；
  - 存储失败不影响返回。
- `fetchReport`：
  - `getReportKey('self', reportId)` 存在时加 `X-Report-Key`；
  - 使用 `apiFetch`。

`composables/useThirdPerson.ts`：同上，作用域为 `tp`。

`stores/useTestStore.ts` / `useThirdPersonStore.ts`：

- 删除 `uid`、`generateUid`、`initUid`；
- 删除 `mbti_uid` 读写；
- 报告 ID 持久化键保持不变：
  - `mbti_last_report_id`
  - `mbti_last_tp_report_id`
- `pages/[lang]/quiz.vue`、`pages/[lang]/third-person/quiz.vue` 删除 `initUid()` 调用与 `uid` 传参。

`utils/request.ts`：

- 当前未被业务引用；保留时移除 `mbti_uid` 注入，改为从 `authSession.getAccessToken()` 注入 `Authorization`，并标记废弃。
- 新代码统一使用 `apiFetch`，不要继续扩散 axios 实例。

> MVP 不支持历史匿名报告认领：注册/登录不会把 `uid=0` 的旧报告改为当前用户所有。旧报告只能依赖本机 key 或后端兼容窗口。

### 8.5 双人测试与第三人对比

- `useDualTest` / `useThirdPersonCompare` 继续调用 `useApi().fetchReport` 与 `useThirdPerson().fetchReport`，自动获得 key 注入能力，无需新增参数。
- 自测报告不可访问 → 对比区保持现有“静默隐藏”，不阻断第三人报告。
- `useDualTest.reset(scope)` 清理完成态时同时 `removeReportKey('self'|'tp', reportId)`，避免旧 key 残留。
- 双人结果页不新增后端接口，不生成综合匹配度分数（沿用产品红线）。

---

## 九、状态与交互细节

### 9.1 登录/注册表单状态

```ts
status: 'idle' | 'submitting' | 'success' | 'error'
fieldErrors: Record<string, string>
formError: string | null
retryAfter: number // 429 倒计时秒数
```

- 提交中禁用所有输入与按钮。
- 429 启动倒计时，倒计时结束前不发送请求。
- 成功跳转前不重复触发。
- 浏览器自动填充触发 `input` 事件时同步校验。

### 9.2 账号页保存状态

- 分卡片独立 loading，避免修改昵称时密码表单也被禁用。
- 保存成功显示 2 秒成功提示；失败保留输入并展示错误。
- 修改密码成功后更新 token，不跳转。
- 登出立即清理并跳转，不等待后端（后端失败也继续）。

### 9.3 初始化与路由守卫

- 不在全局 middleware 中做鉴权，避免影响预渲染内容页。
- 只在账号页做客户端守卫；登录/注册页对已登录用户做反向跳转。
- 报告页不强制登录；无权限由 404 状态驱动。
- 避免重定向循环：登录失败不跳转；账号页未登录只跳一次；登录页检测到已登录才反向跳转。

### 9.4 错误文案与字段映射

- 400 邮箱/密码错误映射到字段；
- 401 登录失败映射到表单级；
- 401 修改密码当前密码错误映射到 `current_password` 字段；
- 409 映射到 `email` 字段；
- 429 映射到表单级 + 倒计时；
- 5xx/网络映射到表单级，可重试。

---

## 十、国际化设计

### 10.1 `locales/*.json`

新增顶层 `auth`：

```json
{
  "auth": {
    "login": {
      "title": "",
      "subtitle": "",
      "email": "",
      "password": "",
      "submit": "",
      "noAccount": "",
      "registerLink": ""
    },
    "register": {
      "title": "",
      "subtitle": "",
      "displayName": "",
      "confirmPassword": "",
      "submit": "",
      "hasAccount": "",
      "loginLink": "",
      "termsPrefix": "",
      "termsLink": "",
      "privacyLink": ""
    },
    "account": {
      "title": "",
      "profile": "",
      "email": "",
      "displayName": "",
      "language": "",
      "createdAt": "",
      "save": "",
      "saved": "",
      "security": "",
      "currentPassword": "",
      "newPassword": "",
      "confirmNewPassword": "",
      "changePassword": "",
      "passwordChanged": "",
      "session": "",
      "logout": "",
      "logoutDesc": ""
    },
    "menu": {
      "login": "",
      "account": "",
      "logout": ""
    },
    "errors": {
      "invalidEmail": "",
      "invalidPassword": "",
      "passwordMismatch": "",
      "passwordSameAsEmail": "",
      "passwordSameAsOld": "",
      "invalidCredentials": "",
      "invalidCurrentPassword": "",
      "emailTaken": "",
      "rateLimited": "",
      "network": "",
      "serverError": "",
      "sessionExpired": "",
      "invalidRequest": ""
    }
  }
}
```

- 6 个语言文件同时补齐；不把账号文案写死在组件里。
- 现有 `nav` 可增加 `login` / `account`，或统一从 `auth.menu` 取，避免重复 key。
- 报告无权限文案放入 `report` 命名空间，自测与第三人共用。
- 隐私政策、服务条款按现有页面结构增加账号段落，6 语言同步。

### 10.2 日期与语言

- 注册时间用 `Intl.DateTimeFormat(locale.value, { dateStyle: 'medium' })`。
- 语言下拉的选项名称使用各语言自称（中文、English、日本語、한국어、Español、Português (BR)），与 `LanguageSwitcher` 保持一致。
- 登录后不使用 `user.lang` 自动改写当前 URL；只作为账号偏好保存。
- “本机数据”相关文案（说明、清除按钮、二次确认、成功提示、登出提示）6 语言同步。

---

## 十一、SEO、隐私与安全

### 11.1 SEO / 渲染

- 账号页 `ssr:false` + `robots: noindex, nofollow`。
- 不加入 prerender / sitemap。
- 无前缀存根为 CSR 语言跳转，不收录。
- 内容页、类型页、博客、职业、关系、双人落地页的预渲染策略不变。
- 账号页标题/描述仍需本地化，便于直接访问时浏览器标签可读。
- 不新增 JSON-LD。

### 11.2 隐私政策与服务条款

需新增/补充的要点（6 语言）：

- 收集的数据：邮箱、昵称、语言偏好、密码哈希、登录时间、Refresh Token 哈希与设备信息（UA/IP）、报告归属与报告访问键哈希。
- 用途：账号登录、报告归属与访问控制、账号安全、必要的安全审计。
- 保留期限：账号存续期间；Refresh Token 过期清理；报告键不存明文。
- 用户权利：联系支持；MVP 暂不支持自助注销/导出，需在条款中说明。
- 不向第三方出售账号数据；第三方脚本（GA4/AdSense）仅在配置时加载，账号页不加载广告。
- 报告分享：分享链接携带访问键，获得链接者可查看报告；用户应谨慎分享。

### 11.3 安全清单

- token 只存 localStorage（MVP 已知风险），不存 cookie 副本。
- 不把 token/密码/报告键写入 `console`、GA4、错误上报。
- 昵称按文本渲染，禁止 `v-html`。
- 报告键只走 `X-Report-Key`，分享只走 fragment。
- 生产 HTTPS；同源代理；不新增 CORS。
- 不在前端硬编码任何后端密钥。
- 建议部署侧补充 CSP、`X-Content-Type-Options: nosniff`、`Referrer-Policy: strict-origin-when-cross-origin`。
- 分享 URL 的 fragment 不会进入服务端日志，但可能留在浏览器历史；页面加载后立即清理。

---

## 十二、测试与验收

### 12.1 手工测试矩阵

| # | 场景 | 操作 | 期望 |
|---|---|---|---|
| 1 | 注册 | 6 语言各注册一次 | 自动登录，跳账号页，Header 显示昵称 |
| 2 | 重复邮箱 | 同邮箱再注册 | 409，登录引导，邮箱保留 |
| 3 | 登录失败 | 错误密码 | 统一“邮箱或密码错误” |
| 4 | 登录成功 | 正确凭证 | 跳转 `redirect` 或账号页 |
| 5 | 登出 | Header/账号页 | 本地会话清除，其他标签页同步登出 |
| 6 | 自动刷新 | DevTools 将 access 设为过期/删除 access | 请求自动 refresh 并成功重放 |
| 7 | 并发刷新 | 同页触发多个需鉴权请求 | 只发一次 refresh，全部成功 |
| 8 | 刷新失败 | 将 refresh 改为非法 | 清会话，页面不白屏，不循环 |
| 9 | 匿名交卷 | 未登录完成自测 | 返回 report_id + report_key，可查看报告 |
| 10 | 登录交卷 | 登录后完成自测 | 报告归属当前账号，本人无 key 可读 |
| 11 | 匿名分享 | 复制/分享链接 | URL 含 `#rk=`；无痕窗口可打开 |
| 12 | fragment 清理 | 打开分享链接 | key 存入本机，地址栏 fragment 消失，query 保留 |
| 13 | 越权读取 | 用户 B 打开用户 A 的报告 | 404 统一无权限态，无信息泄露 |
| 14 | 历史兼容 | 打开兼容窗口内旧链接 | 可读；窗口外 404 提示 |
| 15 | 修改密码 | 当前密码错误/正确 | 错误字段提示；成功后当前设备仍登录，其他设备 refresh 失效 |
| 16 | 修改资料 | 改昵称/语言 | Header 即时更新；刷新后仍保留 |
| 16b | 清除本机报告键 | 账号页点击“清除本机报告访问权限”并确认 | 本机 `mbti_report_key:*` 清空；本人报告需重新登录；匿名/分享报告需重新打开链接 |
| 17 | 限流 | 连续错误登录 | 429 + 倒计时，提交禁用 |
| 18 | 网络失败 | 断网保存资料 | 保留输入，展示网络错误，不登出 |
| 19 | 移动端 | 375px 宽操作登录/账号/Header | 无横向滚动，表单可操作 |
| 20 | SEO | 查看页面源码/sitemap | 账号页 noindex，不在 sitemap；内容页仍预渲染 |

### 12.2 构建与冒烟

```bash
npm run build
npm run generate   # 内容/路由改动后补充验证
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/zh-CN/login
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/en/register
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/ja/account
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/en/report/r1Z
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/en/third-person/report/r1Z
```

检查：

```bash
# sitemap 不应包含 login/register/account
curl -s http://localhost:3000/sitemap.xml | grep -E 'login|register|account' || echo 'ok: not in sitemap'

# 账号页应含 noindex
curl -s http://localhost:3000/en/login | grep -i 'noindex' || echo 'CSR: noindex set client-side'
```

> 账号页为 CSR，服务端 HTML 可能只有 Nuxt 外壳；`noindex` 在客户端 head 生效。若需服务端也输出 `noindex`，可在 `routeRules` 增加 `headers: { 'X-Robots-Tag': 'noindex, nofollow' }`。

### 12.3 Definition of Done

- 登录/注册/账号页在 6 语言下可用。
- 会话自动刷新、单飞、跨标签页同步可用。
- 匿名与登录答题均可用；不再生成 `mbti_uid`。
- 新报告保存并携带 `report_key`；分享 fragment 链路可用。
- 报告 404 统一无权限态；历史兼容链路验证通过。
- 账号页 `noindex`，sitemap/prerender 未收录。
- 隐私政策、服务条款 6 语言更新。
- `npm run build` 零错误；关键路由冒烟通过。
- 无横向滚动、无广告遮挡、无控制台敏感信息。

---

## 十三、上线与回滚

### 13.1 上线顺序

1. 后端迁移并发布，`auth.enforce_report_ownership=false`，设置 `legacy_report_cutoff`。
2. 前端发布：
   - Header 登录入口；
   - 登录/注册/账号页；
   - `apiFetch` 与会话恢复；
   - 交卷保存 key、报告带 key；
   - 分享 URL fragment。
3. 联调验证：
   - 新匿名报告不带 key 读取 → 404；
   - 带 key 读取 → 200；
   - 登录本人报告 → 200；
   - 旧匿名报告在窗口内 → 200。
4. 后端将 `enforce_report_ownership` 置为 `true`。
5. 观察 30 天后关闭历史兼容窗口。

### 13.2 回滚

- 先让后端恢复 `enforce_report_ownership=false`，再回滚前端。
- 前端回滚不会删除用户本地报告键；重新发布后可继续使用。
- 不删除 `users` / `refresh_tokens` 表；不影响旧逻辑。

### 13.3 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| localStorage token 被 XSS 读取 | 账号会话泄露 | 严格 CSP、纯文本渲染昵称、无第三方不可信脚本；P1 评估 httpOnly Cookie |
| 匿名用户丢失报告键 | 无法再看报告 | 报告页说明 + 重测引导；P1 支持登录后认领/key 轮换 |
| 社交平台丢弃 URL fragment | 接收者无权限 | 优先复制链接；分享文案提示；P1 独立分享页 |
| 跨标签页同时刷新触发重放检测 | 被登出 | 单飞 + storage 事件同步 + 后端 10 秒宽限 |
| 只改前端未改后端 | 交卷仍信任 body uid | 上线顺序固定为后端先行；前端 `uid` 固定 0 |
| 账号页 glob 规则匹配失败 | 账号页被 SSR 预渲染 | 使用显式 6 语言 routeRules，构建后 curl 验证 |
| 网络抖动导致误登出 | 用户体验差 | 只有 401 清会话；网络/5xx 保留缓存并允许重试 |
| 旧前端与新后端混跑 | 旧前端读不出匿名报告 | 过渡期 `enforce_report_ownership=false`，前端发布后立即恢复 |
| 报告键进入浏览器历史 | 本机他人可查看 | 打开后立即 `replaceState` 清理；提示用户不要在公共设备分享 |

---

## 十四、实施顺序（建议）

| 阶段 | 内容 | 产出 |
|---|---|---|
| F1 | `authSession` / `apiClient` / `useAuthApi` / `useAuthStore` / 插件 | 会话与请求底座，可单测（手动） |
| F2 | 登录 / 注册 / 账号页 + Header `AuthMenu` | 可完成注册登录登出改密 |
| F3 | 业务接口接入：移除 `mbti_uid`、交卷保存 key、报告带 token/key | 匿名与登录答题、报告访问闭环 |
| F4 | `reportAccess` + 分享 URL fragment + 报告无权限态 | 分享链路 |
| F5 | 6 语言文案、隐私政策、服务条款 | 国际化与合规 |
| F6 | routeRules / sitemap / build / 手工冒烟 / 联调 | 发布就绪 |

前端预估与后端文档一致：**4~6 人日**（不含联调等待）。

---

## 十五、待确认

1. 登录/注册默认落点是否确认为账号页（有 `redirect` 时回跳）。
2. 注册是否需要显式勾选“同意条款”（当前设计为文字说明 + 链接）。
3. 第三人报告是否在 MVP 增加分享 UI（当前只支持手动链接 + `#rk=`）。
4. ~~账号页是否需要“清除本机报告访问键”入口~~（已实现：账号页“本机数据”卡片）。
5. 登录后是否根据 `user.lang` 自动切换 UI 语言（当前设计：不切换，只保存偏好）。
6. 部署侧能否在本次上线同步配置 CSP 与 `X-Robots-Tag`。
