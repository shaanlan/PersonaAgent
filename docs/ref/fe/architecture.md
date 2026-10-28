# 系统架构

> 适用范围：`PersonalityMatrixFE/pro-v3-dp`
> 状态：当前实现快照
> 最后核对：2026-10-26
> 事实源：代码与配置 > 本文档 > [PRD](../../requirement.md) > `docs/ref/` 历史设计
> 相关文档：[设计文档索引](./README.md) · [变更记录](../../CHANGELOG.md) · [AGENTS.md](../../AGENTS.md)

---

# 一、系统概览

站点是 Nuxt 3 的 SSR/SSG 混合应用，面向 6 种语言发布：

```text
浏览器
  │
  ├── 预渲染 HTML（首页 / 类型 / 博客 / 职业 / 关系 / 静态页 / 双人落地页）
  ├── SSR HTML + 客户端水合（quiz / report / third-person / dual result）
  └── 静态 JSON（博客 / 职业 / 关系 / 引用）
        │
        └── Nitro
              ├── /api/type/[type]        类型解读内容
              ├── /api/share/image        私有原图加水印
              └── /api/v1/*  devProxy → localhost:8082
```

核心原则：

1. 内容型页面必须预渲染，保证 HTML 有实质内容。
2. 博客/职业/关系在构建期烘焙为 JSON，运行时不依赖业务 API。
3. 自测与第三人测试是交互流程，报告数据由客户端读取 localStorage + 后端 API。
4. 当前代码是最终事实源；本文档只记录已核对行为。

---

# 二、技术栈

| 层 | 选型 |
|---|---|
| 框架 | Nuxt 3 `^3.15.4` + Vue 3 |
| 样式 | Tailwind CSS |
| 主题 | `@nuxtjs/color-mode` |
| i18n | `vue-i18n` 手动插件（非 `@nuxtjs/i18n` 路由模块） |
| 状态 | Pinia |
| Markdown | `markdown-it` + `markdown-it-anchor` + `gray-matter` |
| HTTP | `$fetch` / Axios 封装 |
| SEO | `@nuxtjs/sitemap` + `useSeoConfig.ts` |
| 图表 | ECharts / `vue-echarts` |
| 构建期图片 | `sharp`、`qrcode` |
| 部署 | Nitro SSR；预渲染产物随 `.output` 发布 |

包管理使用 `package-lock.json`。没有 lint/test 脚本，质量门禁是构建零错误 + 路由冒烟。

---

# 三、模块地图

```text
pages/
  index.vue                       中文首页
  [lang]/                         语言前缀页面
  [lang]/login.vue                登录（CSR）
  [lang]/register.vue             注册（CSR）
  [lang]/account/index.vue        账号设置（CSR，需登录）
  [lang]/account/reports.vue      我的报告（CSR，需登录）
  login.vue register.vue account/index.vue  无前缀 CSR 语言跳转存根
  account/reports.vue             我的报告无前缀 CSR 语言跳转存根
  type/[type].vue                 无前缀类型存根（302）
  result/[type].vue               旧结果存根（301）
  blog/                           无前缀博客存根
  career/                         无前缀职业存根（301）
  third-person/                   无前缀第三人存根（301）
  dual-test/                      无前缀双人存根（301）
  report/                         无前缀报告存根（301）

components/
  Header / Footer / HomeContent / HomeHero
  AdBlock / LanguageSwitcher / ThemeToggle
  QuestionCard / ProgressBar / ResultChart
  ReportHero / TypeHero / TypeShareCard / RadarChart / DimensionBars / TraitsList
  AuthMenu / AccountReportRow / AccountReportsSummary / AccountSessionsCard
  DualTestReportPicker
  MarkdownRenderer / TableOfContents
  BlogCard / BlogCtaCard / CareerCard / RelationshipCard / RelationshipMbtiPanel
  ThirdPersonComparePanel / ThirdPersonRelationInsight / ThirdPersonRelationLinks
  DualTestFlow / DualTestExample / CitationBookCard / CitationText

composables/
  useApi                 自测题目/提交/报告
  useAuthApi             注册/登录/刷新/登出/me/资料/改密
  useAccountApi          我的报告/删除/认领/登录设备
  useCooldown            429 Retry-After 倒计时
  useThirdPerson         第三人 API + 角色固定配置
  useThirdPersonCompare  自测报告 × 第三人报告对比
  useDualTest            localStorage 完成态 + 双人报告
  useCareer              构建期职业 JSON
  useRelationship        构建期关系 JSON / 分型 / 引用
  useCitations           引用字典
  useBlog                构建期博客 JSON + 相关文章
  useSeoConfig           canonical / hreflang / 默认 OG
  useShare               分享 / 剪贴板
  useSharePoster         静态背景 + 数字合成海报
  useAnalytics           GA4
  useImageOptimizer      图片尺寸辅助
  useCategoryLabels      分类标签
  useDimensionBar / useTheme / useI18n

stores/
  useTestStore           自测状态，localStorage.mbti_last_report_id
  useThirdPersonStore    第三人状态，localStorage.mbti_last_tp_report_id
  useAuthStore           账号会话、用户资料、初始化与登出

utils/
  authSession            token/用户缓存、单飞刷新、跨标签页事件
  apiClient              Authorization 注入、401 刷新重放、错误归一化
  reportAccess           report_key 存取/枚举/清除、#rk 解析、分享 URL
  authErrors             账号错误 → i18n key
  safeRedirect           登录回跳站内校验、剥离 hash
  accountFormat          报告/会话日期、时长、置信度格式化
  accountEvents          报告认领完成事件

server/
  api/type/[type].ts     类型内容 API
  api/share/image.get.ts 原图加水印
  api/blog/*.disabled    已停用
  plugins/url-canonicalization.ts
  utils/blog.ts
  utils/watermarkAsset.ts

modules/
  blog-data.ts
  career-data.ts
  relationship-data.ts
  report-images.ts

scripts/
  generate-blog-data.mjs
  generate-career-data.mjs
  generate-relationship-data.mjs
  generate-share-bg.mjs
  generate-report-images.mjs
  lib/reportImage.mjs

middleware/
  locale.global.ts

plugins/
  i18n.ts
  auth.client.ts         客户端启动时恢复会话

lib/
  markdown-it-mbti-autolink.ts
```

`public/data/**` 和 `content/relationship/**` 是构建期生成物，已 gitignore，不提交。

---

# 四、路由与渲染矩阵

## 4.1 语言与 URL

- 中文首页：`/`
- 其他语言首页：`/{lang}`
- 内容页：`/{lang}/...`，包括中文 `/zh-CN/...`
- 无前缀路径由页面存根或 URL 规范化插件跳转。
- `trailingSlash: false`，根路径 `/` 除外。

## 4.2 渲染策略

| 路由 | 当前策略 | 说明 |
|---|---|---|
| `/` | SSG / prerender | 中文首页 |
| `/{lang}` | SSG / prerender | 5 个非中文首页 |
| `/{lang}/type/{type}` | SSG / prerender | 6 × 16 |
| `/{lang}/blog`、`/{lang}/blog/{slug}` | SSG / prerender | 构建期 JSON 枚举 |
| `/{lang}/career`、`/{lang}/career/{slug}` | SSG / prerender | 仅存在内容的语言 |
| `/{lang}/relationship`、`/{slug}`、`/citations` | SSG / prerender | citations 依赖 JSON 存在 |
| `/{lang}/about` 等 4 个静态页 | SSG / prerender | 6 语言 |
| `/{lang}/dual-test` | SSG / prerender | 6 语言落地页 |
| `/{lang}/login`、`/{lang}/register`、`/{lang}/account` | CSR（`ssr:false`） | 账号私有页，noindex，不预渲染 |
| `/{lang}/account/reports` | CSR（`ssr:false`） | 我的报告，noindex，不预渲染 |
| `/{lang}/quiz` | SSR + 客户端交互 | 未加入 prerender |
| `/{lang}/third-person/quiz` | SSR + 客户端交互 | 未加入 prerender |
| `/{lang}/report/**` | 默认 SSR | 服务端输出加载骨架，数据客户端读取 |
| `/{lang}/third-person/report/**` | 默认 SSR | 同上 |
| `/{lang}/dual-test/result` | 默认 SSR | 读 localStorage |
| `/third-person/**`、`/report/**`、`/quiz`、`/dual-test/result` | CSR 存根 | 无前缀跳转 |
| `/type/**` | SSG 存根 | 302 |
| `/test` | 301 | → `/zh-CN/quiz` |
| `/result/**` | 301 | → `/type/**` |

> `routeRules` 中 `ssr:false` 对报告/结果页只匹配无前缀存根；`/{lang}/report/**`、`/{lang}/third-person/report/**`、`/{lang}/dual-test/result` 未显式设为 CSR，实际为默认 SSR。
>
> 账号页是例外：`/login`、`/register`、`/account`、`/account/reports` 及 6 个语言前缀在 `nuxt.config.ts` 中逐条配置为 `ssr:false`，并输出 `X-Robots-Tag: noindex, nofollow`。
>
> `/{lang}/quiz` 与 `/{lang}/third-person/quiz` 虽未预渲染，但被 sitemap 收录。

## 4.3 跳转码（代码现状）

| 路径 | 状态码 | 目标 |
|---|---|---|
| `/type/{type}` | 302 | `/{lang}/type/{type}` |
| `/blog` | 302 | `/{lang}/blog` |
| `/test` | 301 | `/zh-CN/quiz` |
| `/result/{type}` | 301 | `/{lang}/type/{type}` |
| `/quiz` | 301 | `/{lang}/quiz` |
| `/report/{id}` | 301 | `/{lang}/report/{id}` |
| `/third-person/quiz` | 301 | `/{lang}/third-person/quiz` |
| `/third-person/report/{id}` | 301 | `/{lang}/third-person/report/{id}` |
| `/dual-test` | 301 | `/{lang}/dual-test` |
| `/dual-test/result` | 301 | `/{lang}/dual-test/result` |
| `/career`、`/career/{slug}` | 301 | `/{lang}/career...` |
| `/login`、`/register`、`/account`、`/account/reports` | CSR 语言跳转（页面内 `navigateTo`，`redirectCode: 301`） | `/{lang}/...`（优先账号语言，其次浏览器语言） |
| `/about` 等无前缀静态页 | 301 | `/{lang}/about` 等 |

---

# 五、数据流

## 5.1 自测

```text
/{lang}/quiz
  → useApi.fetchQuestions(short|standard|full)
  → GET /api/v1/personality/questions?survey_id=3|4|5&lang=
  → 答题，useTestStore 保存选项
  → useApi.submitAnswers()
  → POST /api/v1/personality/submit-answers
  → report_id
  → localStorage.mbti_last_report_id = id
  → /{lang}/report/{encodeReportId(id)}
  → useApi.fetchReport(id)
  → GET /api/v1/personality/report?report_id=
```

- 问卷映射：`short=3`、`standard=4`、`full=5`。
- 报告 URL 使用 Base62 + `r` 前缀；`decodeReportId` 兼容旧纯数字 ID。
- `duration` 在自测报告展示；第三人报告不展示时长。

## 5.2 类型解读

```text
/[lang]/type/[type].vue
  → GET /api/type/{type}?lang={locale}&version=v3
  → content/type-v3/{lang}/{type}.md
  → gray-matter
  → frontmatter + Markdown 正文
  → MarkdownRenderer
```

- 无 `version=v3` 时：优先 `content/type/{lang}/{type}_v2.md`，回退 `{type}.md`。
- 图片相对路径拼接 `NUXT_PUBLIC_OSS_IMAGE_BASE_URL`。
- API 缓存：`max-age=120, s-maxage=120, must-revalidate`。

## 5.3 博客

```text
NUXT_BLOG_CONTENT_PATH
  → modules/blog-data.ts (build:before)
  → scripts/generate-blog-data.mjs
  → public/data/blog/{lang}.json
  → public/data/blog/detail/{lang}/{slug}.json
  → useBlog / loadBlogJson
  → 列表 / 详情 / 首页 / 类型页 / 报告页
```

- 无运行时博客 API。
- 旧 `server/api/blog/*.ts` 已 `.disabled`。
- 相关文章由本地 JSON 匹配。
- 当前 JSON **不含** `availableLocales`；`lang_map.json` 已废弃。
- `LanguageSwitcher` 的文章级语言灰显当前无数据支撑。

## 5.4 职业

```text
NUXT_CAREER_CONTENT_PATH（默认 content/career）
  → modules/career-data.ts
  → scripts/generate-career-data.mjs
  → public/data/career/{lang}.json + detail/{lang}/{slug}.json
  → useCareer
```

- 无运行时职业 API。
- 匹配分数在内容构建期预计算。
- 分类：医疗保健、商业与金融、工程、技术、法律、社会服务、科学、管理、艺术与媒体。

## 5.5 关系

```text
NUXT_RELATIONSHIP_CONTENT_PATH（默认 content/relationship）
  → modules/relationship-data.ts
  → scripts/generate-relationship-data.mjs
  → public/data/relationship/{lang}.json
  → public/data/relationship/detail/{lang}/{slug}.json
  → public/data/relationship/type/{lang}/{TYPE}.json
  → public/data/relationship/citations.json
  → useRelationship / useCitations
```

- 无运行时关系 API。
- 7 大分类：亲密关系、友谊、家庭、教育、照护、社交、职场。
- 索引 JSON 含 `availableLocales`。
- 参考文献页与语言无关，citations.json 存在时全语言生成。

## 5.6 第三人测试

```text
/{lang}/third-person/quiz
  → 选择角色
  → survey_id: partner=30 / friend=31 / colleague=32 / boss=33
  → GET /api/v1/personality/third-person/questions
  → POST /api/v1/personality/third-person/submit-answers
  → localStorage.mbti_last_tp_report_id
  → /{lang}/third-person/report/{encodedId}
  → GET /api/v1/personality/third-person/report
  → useThirdPersonCompare 读取自测报告
  → 前端计算四维对比 + relation pattern
  → GET /api/v1/personality/third-person/relation-analysis
  → 关系探索入口 + 引用
```

- 角色显示名以前端 i18n 为准，后端 `target_role_label` 仅兜底。
- `confidence` 语义为“观察一致度”，不展示答题时长。
- 关系分析三态：
  - 有内容：渲染模块
  - 400/404/空 data：隐藏模块
  - 网络/超时/5xx：显示加载失败 + 手动刷新
- 对比区在自测报告不存在/过期/失败时静默隐藏，不阻断第三人报告。

## 5.7 双人测试

```text
/{lang}/dual-test
  → localStorage.mbti_last_report_id
  → localStorage.mbti_last_tp_report_id
  → 两步完成态
  → /{lang}/dual-test/result
  → useApi.fetchReport(自测)
  → useThirdPerson.fetchReport(第三人)
  → useThirdPersonCompare
  → useThirdPerson.fetchRelationInsight
```

- 无独立双人后端 API。
- 不生成综合匹配度分数。
- `from=dual` 保持“重测 / 测测 Ta”流程上下文。
- 第一/第二步可通过 `DualTestReportPicker` 从“我的报告”选择已有报告，选择结果仍写入上述两个 localStorage key。
- 选择器只列登录账号报告；未登录展示登录引导，不请求列表；按当前步骤固定 `perspective`（`self` / `third_person`），不展示 `report_id`。
- 结果页不进 sitemap。

## 5.8 用户账号（MVP）

```text
plugins/auth.client.ts
  → useAuthStore.init()（幂等单飞）
  → authSession: 读取 localStorage 会话
  → Access 过期 ? refreshSession()（单飞）
  → GET /api/v1/personality/auth/me
  → 后台认领本机匿名报告
  → Header 展示登录态

跨标签页
  → storage / mbti:auth-updated 同步登录态
  → mbti:auth-expired 清理 UI 登录态

注册/登录
  → POST /auth/register | /auth/login
  → 保存 access/refresh/expires_at/user
  → 跳转 redirect 或 /{lang}/account

业务请求
  → utils/apiClient.apiFetch（auth: none | optional | required）
  → Authorization: Bearer
  → 401：刷新一次并重放；optional 失败降级匿名

改密
  → POST /auth/change-password
  → 替换本机 token 对，当前设备保持登录

登出
  → 先清理本地会话
  → 后台 POST /auth/logout 撤销当前 family（失败不影响登出）

交卷
  → 响应 data.report_key
  → reportAccess 保存 mbti_report_key:{self|tp}:{id}
  → 报告读取带 X-Report-Key

分享
  → buildReportShareUrl 生成 /report/{id}#rk=...
  → 报告页保存 key 后 history.replaceState 清理 fragment
```

- 匿名答题保持可用；前端不再生成 `mbti_uid`，交卷请求体 `uid` 固定为 `0`（废弃字段）。
- 会话恢复不阻塞首屏：先读缓存用户，再刷新/拉取 `me`；刷新 401/400 清理会话，网络/5xx 保留缓存等待重试。
- `apiFetch` 的 `optional` 模式用于交卷/报告，刷新失败会匿名重试；`required` 用于账号子接口，失败抛出。修改密码时“当前密码错误”的 401 是业务错误，不触发刷新或登出。
- 429 由 `ApiError.retryAfter` 暴露；登录、注册、报告列表/删除、设备撤销均进入本地冷却，不自动重试。
- 登出只撤销账号会话，不清理本机报告访问键；账号页“本机数据”可 `clearAllReportKeys()` 手动清除。
- 账号页 CSR + `X-Robots-Tag: noindex, nofollow`，不进 sitemap。
- 报告 404 统一展示无权限态；第三人对比区在自测报告不可访问时静默隐藏。
- 账号相关功能设计见 `docs/ref/user_account/`。

## 5.9 报告管理与登录设备（P1）

```text
/{lang}/account/reports
  → GET /auth/reports?limit=20&perspective=&cursor=&lang=
  → 列表 / 筛选 / 加载更多
  → DELETE /auth/reports/{report_id}（软删）
  → 读取统一 404

账号页
  → GET /auth/reports?limit=3      最近报告摘要
  → GET /auth/sessions             登录设备
  → DELETE /auth/sessions/{sid}    撤销单设备
  → POST /auth/sessions/revoke-others

登录/注册/会话恢复
  → listStoredReportKeys()
  → POST /auth/reports/claim（20 条/批）
  → 广播 mbti:reports-updated
```

- 报告列表默认 20 条/页（后端上限 50），`cursor` 传上一页 `next_cursor`；切换 tab 清空列表/游标重拉。
- 报告行展示视角、类型、第三人角色、题量、用时、创建时间；`result_available=false` 时隐藏类型/置信度，不阻塞列表。
- 删除/撤销失败保留当前列表；报告 404 移除该项，当前设备撤销返回 404 视为会话失效并登出；429 展示 `Retry-After` 倒计时；5xx/网络错误提供重试。
- 账号页最近报告摘要（limit=3）与登录设备卡片各自独立 loading/error/empty，不阻塞资料/安全模块；最近报告摘要监听 `mbti:reports-updated` 刷新。
- 报告删除使用 `answers.deleted_at` 软删；token/key 读取均 404，重复删除幂等。
- 双人测试第一/第二步可打开 `DualTestReportPicker`，按 perspective 读取 `listMyReports`，选择后写回 `mbti_last_report_id` / `mbti_last_tp_report_id`，并重新拉取双方报告更新完成态。
- 报告选择器不展示 `report_id`；仅登录账号报告可选；未登录只展示登录引导，不发请求。
- 会话当前设备由 Access Token 的 `sid` 识别；旧 token 无 `sid` 时 `apiFetch` 自动刷新重试；列表最多 50 条。
- 撤销当前设备返回 `current=true` 后调用 `auth.logout()` 并跳转登录；其他设备 Refresh Token 立即失效，Access Token 最长残留 15 分钟。
- 游客认领：本机 key 按 `reportId` 去重，每批 20 条，单飞 promise；任何失败停止后续批次并静默，保留本机 `report_key`。
- 账号报告页 CSR + `noindex`，不进 sitemap。

## 5.10 分享与海报

```text
自测报告分享
  → buildReportShareUrl({ scope:'self', reportId, locale })
  → /{lang}/report/{encodedId}#rk=<report_key>
  → 报告页 adoptReportKeyFromHash('self', id)
  → 保存 key + history.replaceState 清理 fragment

第三人报告分享
  → /{lang}/third-person/report/{encodedId}#rk=<report_key>
  → 当前无独立分享 UI，但报告页同样支持 #rk= 读取

海报
  → ReportHero
  → composeSharePoster(type, scores)
  → public/img/share/{type}-bg.webp
  → canvas 绘制 4 个百分比
  → JPEG Blob
  → Web Share(files) 或下载
```

- `report_key` 只放 URL fragment，不进入 query、日志或 Referer；格式为 `rk_` + 43 位 URL-safe 字符，非法 key 忽略。
- 本机 key 存 `localStorage.mbti_report_key:{self|tp}:{id}`，并保留内存副本；隐私模式/配额失败不阻断本轮分享，其他标签页通过 `storage` 事件同步。
- 本机无对应 key 时分享 URL 不带 fragment，`ReportHero` 通过 `hasReportKey` 提示接收者可能无法访问。
- 复制分享与社交分享使用同一 URL；第三人报告暂无独立分享按钮。
- 海报尺寸 960 × 1280，JPEG 质量 0.9。
- 不使用 html2canvas / html-to-image。
- 私有原图在 `server/assets/originals/`，通过 `/api/share/image` 加水印输出。

---

# 六、接口契约

## 6.1 代理

- dev：`/api/v1/*` → `http://localhost:8082/api/v1/*`。
- 生产：由部署环境反向代理到后端。
- 前端封装：`useApi.ts`、`useThirdPerson.ts`。

## 6.2 自测

### 获取题目

`GET /api/v1/personality/questions?survey_id={3|4|5}&lang={locale}`

```json
{
  "code": 0,
  "data": {
    "questions": [
      {
        "id": 21,
        "text": "题目文本",
        "opts": [
          { "id": 1, "text": "选项 A", "dim": "j", "score": 1 },
          { "id": 2, "text": "选项 B", "dim": "p", "score": 5 }
        ]
      }
    ]
  }
}
```

### 提交答案

`POST /api/v1/personality/submit-answers`

```json
{
  "survey_id": 3,
  "uid": 2000,
  "start_time": 20060102150405,
  "end_time": 20060102150405,
  "opt_selections": [
    { "qid": 1, "opt_id": 1 },
    { "qid": 2, "opt_id": 2 }
  ]
}
```

```json
{ "code": 0, "data": { "report_id": 100, "report_key": "rk_..." } }
```

- `report_key` 仅返回一次，前端保存后用于匿名/分享读取报告。
- 请求体 `uid` 为废弃字段；前端固定发送 `0`，身份只来自 `Authorization`。

### 获取报告

`GET /api/v1/personality/report?report_id={id}`

```json
{
  "code": 0,
  "data": {
    "duration": 1000,
    "result_type": "ENTJ",
    "confidence": 10000,
    "scores": [
      { "dim": "E", "score": 1 },
      { "dim": "I", "score": 0 }
    ]
  }
}
```

## 6.3 第三人测试

Base：`/api/v1/personality/third-person`

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/surveys` | `lang` | 可选；角色选择使用本地固定配置 |
| GET | `/questions` | `survey_id`, `lang` | 角色题目 |
| POST | `/submit-answers` | `survey_id`, `uid`, `start_time`, `end_time`, `opt_selections` | 返回 `report_id` + `report_key` |
| GET | `/report` | `report_id` + 可选 `Authorization` / `X-Report-Key` | 第三人报告 |
| GET | `/relation-analysis` | `relation_type`, `type_a`, `type_b`, `pattern`, `lang` | 关系分析内容 |

第三人报告核心字段：

```json
{
  "result_type": "ENFP",
  "confidence": 82,
  "scores": [{ "dim": "E", "score": 7 }],
  "target_role": "partner",
  "target_role_label": "伴侣"
}
```

`relation-analysis` 错误语义：

- `400/404` 或无 content：视为无内容，隐藏模块。
- 网络错误、超时、5xx：展示失败态并允许重试。
- 超时阈值：15 秒。

## 6.4 类型内容

`GET /api/type/{type}?lang={locale}&version=v3`

- `version=v3`：`content/type-v3/{lang}/{type}.md`
- 无 version：`content/type/{lang}/{type}_v2.md` → `{type}.md`
- 返回 frontmatter 结构化字段 + Markdown 正文
- 图片路径按 OSS 前缀解析
- 缓存 120 秒

## 6.5 分享图

`GET /api/share/image?type={TYPE}&w={width}&q={quality}&wm={0|1}`

- `type` 必填，16 型校验。
- 默认宽 800、质量 82、水印开启。
- 原图位于 `server/assets/originals/`，不在 `public/`。
- 输出 `image/webp`。
- 缓存：`public, max-age=86400, s-maxage=604800, immutable`。

## 6.6 用户账号（MVP + P1 + P2）

Base：`/api/v1/personality/auth`

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| POST | `/register` | 无 | 邮箱 + 密码注册，成功返回 user + token 对（自动登录） |
| POST | `/login` | 无 | 邮箱 + 密码登录 |
| POST | `/refresh` | 无 | Refresh Token 轮换 |
| POST | `/logout` | 无 | 幂等撤销当前 family |
| GET | `/me` | 必须 | 当前用户 |
| PATCH | `/profile` | 必须 | 修改 `display_name` / `lang` |
| POST | `/change-password` | 必须 | 修改密码并返回新 token 对 |

请求体：

```text
POST /register
{ "email": "alice@example.com", "password": "password123", "display_name": "Alice", "lang": "en" }

POST /login
{ "email": "alice@example.com", "password": "password123" }

POST /refresh | POST /logout
{ "refresh_token": "..." }

PATCH /profile
{ "display_name": "Alice", "lang": "zh-CN" }

POST /change-password
{ "current_password": "...", "new_password": "..." }
```

- 新接口成功：`{ "code": 0, "data": ... }`；失败：HTTP 4xx/5xx + `{ "code": <http>, "message": "..." }`。
- 请求头：`Authorization: Bearer <access_token>`；报告读取额外使用 `X-Report-Key`。
- Access Token 默认 15 分钟；Refresh Token 默认 30 天，后端只存 hash。
- 登录/注册/刷新受后端限流；超限返回 `429` + `Retry-After`，前端进入冷却，不自动重试。
- 修改密码时“当前密码错误”返回 401，但属于业务错误，前端不按会话失效处理。
- 前端封装：`utils/apiClient.ts`、`utils/authSession.ts`、`stores/useAuthStore.ts`、`composables/useAccountApi.ts`。
- 匿名交卷仍可用；登录态失效时 optional 请求会降级匿名（交卷/报告）。
- 报告归属判定按后端设计：本人、有效 `report_key`、历史兼容窗口，其他 404。

P1 账号接口（均需登录）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/reports` | 我的报告列表（cursor/perspective/lang） |
| DELETE | `/reports/{report_id}` | 软删除本人报告，幂等 |
| POST | `/reports/claim` | 凭 report_key 认领游客报告（≤20/批） |
| GET | `/sessions` | 登录设备列表（最多 50） |
| DELETE | `/sessions/{session_id}` | 撤销指定设备，返回 `current` |
| POST | `/sessions/revoke-others` | 退出其他设备 |

`GET /reports`：

- Query：`limit`（默认 20，最大 50）、`cursor`（上一页最后一条 `report_id`）、`perspective`（`self` / `third_person`，不传为全部）、`lang`（第三人角色文案语言）。
- 只返回本人未删除报告，按 `report_id DESC` 排序；匿名未认领报告不出现。

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
      }
    ],
    "next_cursor": 106,
    "has_more": true
  }
}
```

- `result_available=false` 时 `result_type` 为空，前端展示“结果不可用”，不阻塞列表。
- `DELETE /reports/{report_id}` 返回 `{ "code": 0, "data": { "report_id": 106 } }`；已删除再删仍 200。
- 删除后列表不再返回；本人 token 与分享 `report_key` 读取均 404；`answers` 数据保留（软删）。

`POST /reports/claim`：

```text
POST /reports/claim 请求
{ "reports": [{ "report_id": 100, "report_key": "rk_..." }] }

响应
{ "code": 0, "data": { "claimed": [100], "failed": [101] } }
```

- 每次最多 20 条；只认领 `uid=0`、未删除、`report_key` 匹配的报告。
- 已归属当前用户的报告再次提交视为成功；失败不返回原因，部分成功是正常结果。
- 认领成功后保留 `report_key_hash`，分享链接继续有效。

`GET /sessions`：

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

- `session_id` 是 refresh family_id（32 位 hex），不是登录凭证。
- 当前设备通过 Access Token 的 `sid` 识别；旧 token 无 `sid` 返回 401，前端自动 refresh。
- `DELETE /sessions/{session_id}` 返回 `{ "current": true|false }`；`current=true` 时前端清理本地会话并跳登录。
- `POST /sessions/revoke-others` 返回 `{ "revoked_count": 2 }`，只保留当前设备。
- 会话最多返回 50 条，`has_more` 标记截断。
- 登录/注册/会话恢复后，前端枚举本机 report_key 并后台认领匿名报告。

## 6.7 已停用

| 接口 | 状态 |
|---|---|
| `/api/blog` | `.disabled` |
| `/api/blog/:slug` | `.disabled` |
| 职业运行时 API | 不存在 |
| 关系运行时 API | 不存在 |
| `relatedArticles` 运行时接口 | 不存在 |

---

# 七、SEO 与路由规范化

## 7.1 页面 SEO

- `useSeoConfig.ts` 提供站点 URL、canonical、hreflang、默认 OG。
- 每页必须有 `title`、`description`、Open Graph、canonical。
- 登录/注册/账号页/我的报告页输出 `noindex, nofollow` + `X-Robots-Tag`，不加入 sitemap。
- 语义化：唯一 `h1`，`h2/h3` 递进。
- JSON-LD：
  - 首页：`WebSite`
  - 博客列表：`ItemList`
  - 博客详情：`Article + BreadcrumbList`
  - 类型页：`BreadcrumbList`、有 FAQ 时加 `FAQPage`
  - 双人页：`HowTo + FAQPage`
  - 其他内容页按需 `BreadcrumbList` / `FAQPage`

## 7.2 sitemap

- `@nuxtjs/sitemap`，`zeroRuntime: true`，预渲染生成。
- 收录：
  - 5 个非中文首页 + 中文 `/`
  - 16 型 × 6
  - 静态页 × 6
  - 博客、职业、关系、citations
  - `/{lang}/quiz`
  - `/{lang}/third-person/quiz`
  - `/{lang}/dual-test`
- `exclude` 列表包含：
  - `/report/**`、`/third-person/**`、`/blog/**`、`/result/**`
  - `/quiz`
  - `/dual-test/result` 与 `/**/dual-test/result`
  - `/dual-test`
  - `/login`、`/register`、`/account`、`/account/reports`
  - `/**/login`、`/**/register`、`/**/account`、`/**/account/reports`
  - `/intj`、`/mbti-intro`
  - `/about`、`/contact`、`/privacy-policy`、`/terms`
  - `/career`、`/career/**`
- 真实语言页由 `sitemap.urls()` 显式加入，例如 `/{lang}/third-person/quiz`、`/{lang}/career/**`、`/{lang}/relationship/**`，不受无前缀 exclude 影响。

## 7.3 URL 规范化

- `middleware/locale.global.ts`：
  - locale 别名归一
  - route params 与 vue-i18n locale 同步
- `server/plugins/url-canonicalization.ts`：
  - `/zh-CN` → `/`
  - 非根路径去尾斜杠
  - 旧路径/旧博客链接规范化
  - 无前缀路径按语言跳转

---

# 八、国际化

- 语言：`zh-CN`、`en`、`ja`、`ko`、`es`、`pt-BR`。
- 默认/回退：`zh-CN`。
- `plugins/i18n.ts` 手动加载 6 个 JSON。
- `LanguageSwitcher.vue` 切换当前页语言。
- UI 文案在 `locales/*.json`；长内容在 `content/` 或外部内容路径。
- 当前博客不做文章级语言可用性判断，原因见 §10。

---

# 九、构建、配置与发布

## 9.1 构建期模块

| 模块 | 产物 |
|---|---|
| `modules/blog-data.ts` | `public/data/blog/{lang}.json`、`detail/` |
| `modules/career-data.ts` | `public/data/career/{lang}.json`、`detail/` |
| `modules/relationship-data.ts` | `public/data/relationship/{lang}.json`、`detail/`、`type/`、`citations.json` |
| `modules/report-images.ts` | 报告/分享图 |
| `scripts/generate-share-bg.mjs` | `public/img/share/{type}-bg.webp` |

- 通过 `build:before` 在 `dev/build/generate` 前自动执行。
- 发布内容 = 重新构建 + 部署。
- 构建期生成物不提交。

## 9.2 环境变量

| 变量 | 用途 |
|---|---|
| `NUXT_BLOG_CONTENT_PATH` | 博客 Markdown 源路径 |
| `NUXT_CAREER_CONTENT_PATH` | 职业 Markdown 源路径，默认 `content/career` |
| `NUXT_RELATIONSHIP_CONTENT_PATH` | 关系 Markdown 源路径，默认 `content/relationship` |
| `NUXT_PUBLIC_OSS_IMAGE_BASE_URL` | 内容图 CDN 前缀 |
| `NUXT_PUBLIC_BLOG_HERO_BG` | 博客 Hero 背景 |
| `NUXT_PUBLIC_ADSENSE_CLIENT_ID` | AdSense client ID |
| `NUXT_PUBLIC_AD_ENABLED_LABELS` | 广告位白名单，默认 `home-bottom` |
| `NUXT_PUBLIC_GA_MEASUREMENT_ID` | GA4 ID |
| `NUXT_PUBLIC_GA_DEV_MODE` | GA4 开发模式 |

只有 `NUXT_PUBLIC_*` 会进入浏览器端。

## 9.3 命令

| 命令 | 用途 |
|---|---|
| `npm run dev` | 开发 |
| `npm run build` | SSR 构建 |
| `npm run generate` | SSG 生成 |
| `npm run preview` | 预览 generate 产物 |

## 9.4 发布检查

1. 构建零错误。
2. 关键路由 200。
3. 新路由已加入 prerender/sitemap 或明确排除。
4. 6 语言内容无空白页。
5. 无横向滚动、无广告遮挡。
6. 关键页面 canonical/description/OG 完整。
7. 未提交 `.env`、密钥、构建期生成物。

---

# 十、广告与统计

## 10.1 AdBlock

- 组件：`components/AdBlock.vue`
- 位置通过 `label` 区分。
- 默认白名单：`home-bottom`
- `NUXT_PUBLIC_AD_ENABLED_LABELS`：
  - 逗号分隔 label
  - `*` 开启全部
- 广告脚本仅客户端加载。
- 广告位不得在首屏，不得遮挡正文。

## 10.2 当前引用清单

共 **15 个文件、28 处引用** = 27 个固定引用 + 1 个动态模板。

| 文件 | 标签 |
|---|---|
| `components/HomeContent.vue` | `home-section2-3`、`home-bottom` |
| `pages/[lang]/about.vue` | `about-bottom` |
| `pages/[lang]/blog/index.vue` | `blog-hero` |
| `pages/[lang]/blog/[slug].vue` | `blog-article`、`blog-article-{idx}` |
| `pages/[lang]/type/[type].vue` | `type-top`、`type-middle` |
| `pages/[lang]/type/[type]-v1.vue` | `type-top`、`type-middle`、`type-bottom` |
| `pages/[lang]/report/[id].vue` | `report-middle`、`report-bottom` |
| `pages/[lang]/third-person/report/[id].vue` | `third-person-report-middle`、`third-person-report-bottom` |
| `pages/[lang]/career/index.vue` | `career-list-mid`、`career-list-bottom` |
| `pages/[lang]/career/[slug].vue` | `career-top`、`career-mid`、`career-bottom` |
| `pages/[lang]/relationship/index.vue` | `relationship-list-mid`、`relationship-list-bottom` |
| `pages/[lang]/relationship/[slug].vue` | `relationship-top`、`relationship-mid`、`relationship-bottom` |
| `pages/[lang]/relationship/citations.vue` | `relationship-citations-bottom` |
| `pages/[lang]/dual-test/index.vue` | `dual-test-bottom` |
| `pages/[lang]/dual-test/result.vue` | `dual-test-result-bottom` |

## 10.3 统计

- GA4 通过 `composables/useAnalytics.ts` 客户端加载。
- 仅在配置了 `NUXT_PUBLIC_GA_MEASUREMENT_ID` 时启用。
- 开发模式由 `NUXT_PUBLIC_GA_DEV_MODE` 控制。

---

# 十一、已知实现差异与技术债

以下为代码现状，不是产品目标。修改代码时需同步更新本文档。

1. **语言前缀报告页默认 SSR**
   - `/{lang}/report/**`、`/{lang}/third-person/report/**`、`/{lang}/dual-test/result` 服务端只输出加载骨架。
   - 报告/结果页只有无前缀存根配置了 `ssr:false`；账号页按语言逐条配置为 CSR（见第 8 条）。
   - `docs/ref/` 中部分设计文档仍写 CSR，已过期。

2. **博客语言可用性未实现**
   - 博客 JSON 无 `availableLocales`。
   - `lang_map.json` 不再生成/消费。
   - `LanguageSwitcher` 不会按文章实际语言灰显。

3. **quiz 未预渲染但被 sitemap 收录**
   - `/{lang}/quiz`、`/{lang}/third-person/quiz` 是 SSR + 客户端交互。
   - 页面内容需保证首屏有实质内容。

4. **无前缀跳转码不统一**
   - `/type/{type}`、`/blog` 为 302。
   - 其余多数无前缀路径为 301。
   - 以 §4.3 为准。

5. **`mbti-intro` 为遗留页面**
   - 只有裸路径 `/mbti-intro`，无语言前缀。
   - sitemap 已排除。

6. **`docs/ref/` 设计文档可能过期**
   - 不直接作为实施依据。
   - 状态见[设计文档索引](./README.md)。

7. **没有 lint/test 脚本**
   - 构建与冒烟是唯一自动化门禁。

8. **账号页为 CSR**
   - `/{lang}/login`、`/{lang}/register`、`/{lang}/account`、`/{lang}/account/reports` 使用 `ssr:false`，服务端只输出 Nuxt 外壳；`noindex` 由客户端 head 与 `X-Robots-Tag` 共同保证。
   - 本地联调账号接口前，后端需先执行 `user_account.sql` 迁移。

9. **P1 报告删除为软删除**
   - `answers.deleted_at` 标记；读取统一 404，数据仍保留。
   - 撤销当前设备后 Access Token 最长 15 分钟仍有效；Refresh Token 立即失效。

10. **P2 双人测试复用账号报告依赖登录态**
    - `DualTestReportPicker` 只列登录账号报告；匿名本机报告不可选。
    - 选择只写 localStorage `report_id`；退出登录后若本机无对应 `report_key`，结果页读取可能 404。

---

# 十二、文档维护

- 修改渲染策略、路由、API 契约、构建产物、环境变量、广告位时，必须同步本文档。
- 每次更新填写“最后核对”日期；必要时记录代码基线提交。
- 功能级设计放 `docs/ref/`，系统级设计放本文件，产品需求放 `requirement.md`。
- 版本历史放 `CHANGELOG.md`，不要写回本文件。
