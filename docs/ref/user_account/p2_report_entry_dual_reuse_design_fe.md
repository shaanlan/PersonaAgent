# P2 前端设计：报告入口前置 + 双人测试复用已有报告

> 状态：`implemented`（前端已实现；纯前端，无后端接口变更）
> 最后更新：2026-10-25
> 关联文档：
> - P1 我的报告/登录设备：[p1_reports_sessions_design_fe.md](./p1_reports_sessions_design_fe.md)
> - 双人测试设计：[docs/ref/dual_test/dual_test_design.md](../dual_test/dual_test_design.md)
> - 系统架构：[docs/design/architecture.md](../../design/architecture.md)
>
> 事实源：代码与配置 > 系统架构 > PRD > `docs/ref/`。

---

## 一、背景与目标

P1 已经提供“我的报告”列表，但入口藏在账号设置页面的“最近报告”里，用户需要先进入账号设置。双人测试也确实依赖“自测报告 + 第三人报告”，但当前只能通过重新测试产生，无法复用账号中已有报告。

本次目标：

1. 在右上角用户菜单中，把“我的报告”提升为与“账号设置”并列的入口，点击直达 `/{lang}/account/reports`。
2. 双人测试三步流程中，第一步、第二步增加“选择已有报告”动作。
3. 选择器直接读取 P1 的“我的报告”列表，按视角筛选：
   - 第一步只列出 `perspective=self`；
   - 第二步只列出 `perspective=third_person`。
4. 选择后写入现有 localStorage 完成态，刷新卡片类型与第三步锁定态。
5. 不展示 `report_id`。报告靠类型、视角、角色、时间区分；ID 仅内部使用。
6. 纯前端改动，不新增后端接口，不影响匿名测试原有流程。

---

## 二、范围

### 2.1 包含

- `AuthMenu` 桌面下拉 + Header 移动菜单增加“我的报告”。
- `DualTestFlow` 第一/第二步新增“选择已有报告”动作。
- 新增报告选择弹窗组件：加载、分页、空/错误状态、选择。
- `useDualTest` 增加 `selectReport(scope, reportId)`。
- 选择后刷新完成态、结果类型和第三步可用性。
- 6 语言文案。
- 设计索引、架构、PRD、CHANGELOG 同步。

### 2.2 不包含

- 新增/修改后端接口。
- 未登录本机匿名报告的列表化选择。
- 报告重命名、收藏、标签、恢复。
- 双人综合匹配度评分。
- 自动清除旧报告访问键。

---

## 三、关键决策

| # | 决策 | 说明 |
|---|------|------|
| D1 | “我的报告”入口 | 用户菜单中与“账号设置”并列，桌面 + 移动菜单 |
| D2 | 报告 ID | 不展示。列表/选择器用类型、视角、角色、时间区分 |
| D3 | 选择数据源 | 只使用登录账号的 P1 报告列表；匿名本机报告不进入选择器 |
| D4 | 未登录用户 | 点击“选择已有报告”展示登录引导；原有开始/重测流程不受影响 |
| D5 | 选择结果 | 写入 `mbti_last_report_id` / `mbti_last_tp_report_id`，覆盖当前完成态 |
| D6 | 选择后刷新 | 重新拉取双方报告，更新类型、步骤 3 锁定状态与错误态 |
| D7 | 选择器分页 | 首次 20 条，支持“加载更多”；按当前步骤固定 perspective |
| D8 | 删除/分享 | 本次不改变；选择器不提供删除操作 |

---

## 四、交互设计

### 4.1 用户菜单

桌面 `AuthMenu` 登录后下拉：

```text
用户信息
├─ 我的报告      → /{lang}/account/reports
├─ 账号设置      → /{lang}/account
└─ 退出登录
```

移动端 Header 登录区域同样增加“我的报告”，位于“账号设置”之前/之后均可，统一放在同一组。

- 仅登录后显示；未登录不显示。
- 点击后关闭菜单。
- 不新增 Header 主导航项，避免挤压现有导航。

### 4.2 双人测试三步卡片

第一、第二步卡片动作区：

- 未完成：
  - 主操作：开始测试
  - 次操作：选择已有报告
- 已完成：
  - 主操作：重新测试
  - 次操作：选择已有报告、重置
- 第三步保持原样：仅当两步完成才可点击。

按钮点击不能触发卡片自身的跳转：使用 `@click.prevent.stop`，并保持卡片主 CTA 可用。

### 4.3 报告选择器

新增 `DualTestReportPicker.vue`：

- `Teleport` 到 body，固定遮罩 + 居中弹层。
- Header：标题、说明、关闭按钮。
- 已登录：
  - 加载对应 perspective 的报告（`limit=20`）。
  - 列表复用 `AccountReportRow` 的 `selectable` 模式。
  - 每行展示：视角、第三人角色（如有）、类型、置信度、题量、用时、创建时间。
  - 底部“加载更多”使用 `next_cursor`。
- 未登录：
  - 不请求列表，展示登录说明 + “去登录”（带 redirect 回当前 dual-test）。
- 空状态：
  - 自测：还没有自测报告 → 去自测。
  - 第三人：还没有测 TA 报告 → 去测测 Ta。
- 错误：显示错误 + 重试；429 展示限流提示。
- 选择后：
  1. 关闭弹层；
  2. 调 `selectReport(scope, reportId)`；
  3. 重新拉取双方报告；
  4. 卡片类型更新，第三步按 `bothDone` 重新计算。

### 4.4 选择后的状态

```text
选择 self 报告
  → localStorage.mbti_last_report_id = report_id
  → refreshStatus()
  → loadReports()
  → selfType 更新

选择 third_person 报告
  → localStorage.mbti_last_tp_report_id = report_id
  → refreshStatus()
  → loadReports()
  → targetType / role 更新
```

- 覆盖当前完成态，不保留旧报告 ID。
- 不删除旧报告的本机 `report_key`；旧 key 只是不再被当前双人流程使用。
- 第三步仍由 `bothDone = selfDone && targetDone` 决定。
- 用户仍可使用“重置”清除完成态。

---

## 五、代码设计

### 5.1 `useDualTest`

新增：

```ts
async function selectReport(scope: 'self' | 'target', reportId: number): Promise<void>
```

实现：

1. 校验 `reportId > 0` 且客户端。
2. 写入对应 localStorage key。
3. `refreshStatus()`。
4. `await loadReports()`（内部重新拉取双方报告）。
5. 若当前正在加载，等待/忽略重复调用由调用方控制；选择器一次只提交一次。

暴露 `selectReport`。

### 5.2 `AccountReportRow`

扩展 props：

```ts
selectable?: boolean
```

新增 emits：

```ts
select: []
```

- `selectable=true`：
  - 隐藏“查看/删除”；
  - 显示“选择”按钮；
  - 点击 emit `select`；
  - 不渲染跳转链接，避免误跳转。
- 其余场景保持 P1 行为。

### 5.3 `DualTestReportPicker.vue`

Props：

```ts
open: boolean
perspective: 'self' | 'third_person'
```

Emits：

```ts
close: []
select: [item: ReportListItem]
```

行为：

- `watch(open)`：打开且已登录时加载第一页；关闭时重置列表/游标。
- `load(reset)`：调用 `useAccountApi().listMyReports({ perspective, limit:20, cursor, lang })`。
- 未登录时直接展示登录引导，不发起请求。
- 选择按钮 emit 当前 `ReportListItem`。
- 关闭：遮罩点击、关闭按钮、Escape。
- 打开时锁定 body 滚动（可选，建议实现）。

### 5.4 `DualTestFlow`

新增 emit：

```ts
select: [scope: 'self' | 'target']
```

- 第一/第二步卡片增加“选择已有报告”按钮。
- 点击 `emit('select', 'self'|'target')`。
- 不区分登录态，按钮始终显示；未登录时由弹层展示登录引导（不直接跳走）。
- 重置按钮继续保留。

### 5.5 `pages/[lang]/dual-test/index.vue`

新增状态：

```ts
const pickerStep = ref<'self' | 'target' | null>(null)
```

流程：

1. 点击卡片“选择已有报告” → `pickerStep = 'self' | 'target'`。
2. 弹层 perspective：`self → self`，`target → third_person`。
3. 选择 → `await selectReport(scope, item.report_id)` → 关闭。
4. 弹层关闭 → `pickerStep = null`。

- 不改动双人落地页的 SEO/预渲染结构。
- 弹层仅在客户端挂载（页面本身 SSG，弹层 `v-if` + Teleport）。

---

## 六、i18n

新增 `dualTest.picker.*`（6 语言）：

- `selfTitle`、`targetTitle`
- `selfDesc`、`targetDesc`
- `select`、`selected`（可选）
- `loginRequired`、`loginCta`
- `emptySelf`、`emptyTarget`
- `goSelf`、`goTarget`
- `loadMore`、`loading`、`loadFailed`、`retry`
- `close`

新增 `auth.menu.reports`（用户菜单“我的报告”）。

- 报告行继续复用 `auth.reports.*`。
- 无新增报告 ID 文案。

---

## 七、测试与验收

| # | 场景 | 期望 |
|---|---|---|
| 1 | 登录后打开用户菜单 | 显示“我的报告”，点击直达列表 |
| 2 | 移动端菜单 | 同样显示“我的报告” |
| 3 | 双人测试第一步点击“选择已有报告” | 只列出自测报告 |
| 4 | 第二步点击“选择已有报告” | 只列出第三人报告 |
| 5 | 选择自测报告 | 第一步完成态/类型更新 |
| 6 | 选择第三人报告 | 第二步完成态/类型更新 |
| 7 | 两步都选择完成 | 第三步解锁 |
| 8 | 重置后重新选择 | 完成态按新报告更新 |
| 9 | 未登录点击选择 | 展示登录引导，不请求列表 |
| 10 | 空报告/接口失败/429 | 空态/重试/限流提示 |
| 11 | 加载更多 | 追加下一页，不重复 |
| 12 | 6 语言 | 菜单、弹层、报告行文案完整 |
| 13 | 构建与冒烟 | `npm run build` 通过，dual-test 页面正常 |

---

## 八、文件清单

新增：

```text
components/DualTestReportPicker.vue
docs/ref/user_account/p2_report_entry_dual_reuse_design_fe.md
```

修改：

```text
components/AuthMenu.vue
components/Header.vue
components/DualTestFlow.vue
components/AccountReportRow.vue
composables/useDualTest.ts
plugins/auth.client.ts（延后会话恢复到 hydration 后）
pages/[lang]/dual-test/index.vue
locales/*.json
requirement.md
docs/design/architecture.md
docs/design/README.md
CHANGELOG.md
```

---

## 九、限制

- 选择器只覆盖登录账号中的报告；匿名本机报告仍按原流程使用。
- 选择账号报告后，如果用户退出登录，后续双人结果读取依赖账号 token；没有本机 `report_key` 时会无权限。
- 不展示 `report_id`；同类型同时间报告依靠创建时间和角色区分。
- 不新增报告恢复/删除能力。
