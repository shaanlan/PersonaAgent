# PersonalityMatrix — 需求文档

> MBTI 人格测试系统，支持多问卷、多语言、客观打分与结果解读。
> 技术设计（API 契约、数据库字段、算法、数据流）见 [design.md](design.md)；工程规范见 [AGENTS.md](AGENTS.md)。

---

## 1. 项目概述

### 1.1 定位
在线 MBTI 人格测评系统，用户选择问卷并逐题作答，系统根据选项维度分值自动计算人格类型并生成报告。

产品包含自测、第三人测试（测测 Ta）、双人测试、职业探索、关系探索等模块；本后端承担测评（自测 + 第三人）与「你与 Ta 的关系分析」API，双人测试复用上述接口（零新增），职业/关系探索为 ContentEngine + 前端静态内容（不依赖本后端）。模块总览见 1.2 节。

### 1.2 产品模块总览

| 模块 | 说明 | 归属 | 本后端接口 | 状态 |
| -- | -- | -- | -- | -- |
| 自测 MBTI | 用户自评问卷 → 人格类型报告 | 本后端 + 前端 | 3 个（见 §3） | 已上线 |
| 第三人测试（测测 Ta） | 他评版 MBTI：观察 Ta 并作答，输出 Ta 的类型报告 | 本后端 + 前端 | 4 个（见 §3） | 已上线 |
| 关系分析（你与 Ta） | 第三人报告附加模块：双方类型 + 四维差异 pattern → 预生成解读 | 本后端（只读查表） + ContentEngine 灌数 | 1 个（见 §3） | 已上线 |
| 双人测试 dual_test | 前端流程页：把「自测 → 测测 Ta → 关系分析」显式化为三步入口与结果页 | 前端 | 零新增（复用上述接口） | 已上线 |
| 职业探索 career | MBTI × 职业知识静态内容（列表/详情页，16 型匹配分预计算） | ContentEngine + 前端静态 | 无 | 已上线 |
| 关系探索 relationship | 关系知识库（32 关系 × 7 类，6 语）+ MBTI 分型面板 + 引用溯源页 | ContentEngine + 前端静态 | 无 | 已上线 |

**模块边界**：
- 双人测试**不新增后端接口、不改测试逻辑**，仅复用自测/第三人/关系分析 API；产品红线：**不输出复合匹配分 / 契合度百分比**。
- 关系分析内容由 ContentEngine pairanalysis 管线预生成并灌入 `relationship_analysis` 表（4 角色 × 16×16 类型对 × 16 pattern × 6 语言），本服务只读查询、不生成内容、不写库；`chunk_ids` 与前端 `relationship/citations.json` 引用字典同版本可 join。
- 职业探索、关系探索完全不依赖本后端（运行时仅读前端烘好的静态 JSON）。
- 参考文档：第三人测试 `ref/third_person_test_design.md`；关系分析 `ref/third_person_relation_analysis_api.md`；第三人题库规范 `ref/third_person_content_design.md`；双人测试 `PersonalityMatrixFE/pro-v3-dp/ref/dual_test/dual_test_design.md`；职业探索 `…/ref/career/` 与 `ContentEngine/ref/career/`；关系探索 `…/ref/relationship/` 与 `ContentEngine/ref/relationship/`。

---

## 2. 功能需求

### 2.1 答题模块 (F1)

**F1.1 问卷选择**
- 支持多份问卷，通过 `survey_id` 区分。
- 按题目数量分为简答卷（10 题）、标准答卷（20 题）、完整答卷（40 题）。
- 自测问卷来源：v1、gemini、deepseek、chatgpt，各含 10/20/40 三种规格。
- 第三人问卷来源：third-person，按被测关系分 4 卷（partner/friend/colleague/boss，各 10 题），survey_id 30~33，详见 F4 与 §6.1。

**F1.2 逐题作答**
- 逐一展示当前题目的文本和选项（每道题 2 个选项）。
- 用户选择选项后自动切换到下一题（无需点击"下一题"按钮）。

**F1.3 返回上一题**
- 支持回退到前一题，修改选择。

**F1.4 进度展示**
- 展示当前题目序号/总题数（如 3/10）。

### 2.2 结果展示 (F2)

**F2.1 答题用时**
- 记录用户开始时间和结束时间，在报告中展示总用时（毫秒）。

**F2.2 人格类型结果**
- 根据 MBTI 四维打分，输出 4 字母结果（如 ENTJ、INFP 等）。
- 四个维度对比规则：
  - E(外向) vs I(内向) → 分数高者胜出
  - S(实感) vs N(直觉) → 分数高者胜出
  - T(思考) vs F(情感) → 分数高者胜出
  - J(判断) vs P(感知) → 分数高者胜出
- 得分相等时取前者：I>=E 取 I，N>=S 取 N，T>=F 取 T，J>=P 取 J。

**F2.3 维度得分**
- 展示 8 个子维度的原始分数（E、I、S、N、T、F、J、P）。

**F2.4 置信度**
- 展示预测置信度，输出范围约 [3000, 9200]。
- 基于维度归一化边距法 + 区间映射（对每个维度对归一化得分边距取平均，再线性映射避免极端值），算法详见 design.md §5.3。

### 2.3 结果解读 (F3) — 待实现

- 详细解读：人格类型描述。
- 类型-职业-擅长领域推荐。
- 同类型名家名人列举。
- 性格特征、情感模式、事业建议。
- 此模块当前尚未实现，为后续规划功能。

### 2.4 第三人测试（测测 Ta）(F4)

**F4.1 问卷目录**
- 列出所有启用的第三人问卷：`survey_id`、被测关系（`target_role`）、关系文案（按 `lang`）、题目数量。
- 被测关系取值：`partner`（恋人）/ `friend`（朋友）/ `colleague`（同事）/ `boss`（领导）。

**F4.2 取题 / 交卷**
- 复用自测的取题与交卷逻辑（i18n 题目组装、打分、写 `answers`），仅前置校验该 `survey_id` 在 `survey_metas` 中启用。
- 非第三人问卷（无 meta 或未启用）返回 404。

**F4.3 第三人报告**
- 在自测报告字段基础上追加视角字段：`perspective="third_person"`、`target_role`、`target_role_label`。
- 打分与类型判定与自测完全一致（见 design.md §5），仅视角不同（观察 Ta 而非自己）。

### 2.5 关系分析（你与 Ta）(F5)

- 第三人报告的**只读附加模块**：给定关系类型、双方 MBTI、四维差异 pattern，从 `relationship_analysis` 表精确命中一行解读内容（关系总述、相处场景、建议、溯源 `chunk_ids`）。
- 查找键为五元组 `(relation_type, type_a, type_b, pattern, locale)` 精确匹配且 `status='ready'`；`type_a` 为自测方（你）、`type_b` 为第三人（Ta），方向有序。
- pattern 为四位差异标记（顺序 E/I、S/N、T/F、J/P；每位 `H`=差异大 / `L`=相近），由前端根据双方维度占比差计算后传入（口径见 design.md §8），后端仅校验格式并原样回显。
- 未命中或 `content` 为空时返回 `200 data:null`，前端静默隐藏该模块；本服务不生成内容、不写库。
- 产品红线：不输出复合匹配分 / 契合度百分比。

---

### 2.6 账号报告与会话 (F6)

**F6.1 我的报告列表**
- 登录用户可分页查看自己的自测与第三人报告。
- 支持按视角筛选（self / third_person）、游标分页、6 语言角色文案。
- 列表展示类型、题量/角色、MBTI 类型、置信度、用时、创建时间；结果不可用时标记 `result_available=false`。

**F6.2 报告删除**
- 仅报告本人可删除；采用软删除（`answers.deleted_at`）。
- 删除后列表不展示，本人 token 与 `report_key` 读取均返回 404。
- 重复删除幂等。

**F6.3 游客报告认领**
- 注册/登录后，前端可将本机保存的匿名报告（`uid=0` + `report_key`）批量认领到当前账号。
- 认领后报告出现在“我的报告”，原 `report_key` 保留，分享链接继续有效。

**F6.4 跨设备会话管理**
- 查看当前账号的活跃登录设备（当前设备标记）。
- 支持撤销单个设备、退出其他设备、撤销当前设备。
- 撤销后 Refresh Token 立即失效；Access Token 最长残留 15 分钟。

**F6.5 注册文案**
- “注册后可保存测试结果，并在不同设备上登录”由 F6.1/F6.3/F6.4 共同支撑。

**F6.6 账号安全与访问控制**
- 邮箱规范化（去空格、转小写）后唯一；密码长度 8~72 字节、不得与邮箱相同，服务端只存 bcrypt 哈希。
- 会话采用短效 Access JWT（15 分钟）+ 可撤销 Refresh Token（30 天，只存哈希）；刷新时轮换，重放则撤销同一设备族。
- 报告默认私有：本人登录 token 或持有 `report_key` 才可读取；已软删除的报告一律视为不存在。
- 匿名交卷时 `uid=0`，登录用户的 `uid` 只信任 token，请求体自报值一律忽略。
- 登录/注册/刷新/交卷/读报告等接口限流；生产 JWT 密钥仅通过环境变量注入，不写入配置文件或仓库。
- MVP 不含邮箱验证、找回密码、第三方登录；相关能力列入后续规划。

---

## 3. 接口一览

| 方法 | 路径 | 用途 |
| -- | -- | -- |
| GET | /api/v1/personality/questions | 获取自测题目 |
| POST | /api/v1/personality/submit-answers | 提交自测答案（返回 report_id） |
| GET | /api/v1/personality/report | 获取自测报告 |
| GET | /api/v1/personality/third-person/surveys | 第三人问卷目录 |
| GET | /api/v1/personality/third-person/questions | 获取第三人题目 |
| POST | /api/v1/personality/third-person/submit-answers | 提交第三人答案 |
| GET | /api/v1/personality/third-person/report | 获取第三人报告 |
| GET | /api/v1/personality/third-person/relation-analysis | 「你与 Ta 的关系分析」查询 |
| POST | /api/v1/personality/auth/register | 注册并自动登录 |
| POST | /api/v1/personality/auth/login | 登录 |
| POST | /api/v1/personality/auth/refresh | 刷新会话 |
| POST | /api/v1/personality/auth/logout | 登出当前设备 |
| GET | /api/v1/personality/auth/me | 当前用户 |
| POST | /api/v1/personality/auth/change-password | 修改密码 |
| PATCH | /api/v1/personality/auth/profile | 修改昵称/语言 |
| GET | /api/v1/personality/auth/reports | 我的报告列表 |
| DELETE | /api/v1/personality/auth/reports/{report_id} | 删除自己的报告（软删） |
| POST | /api/v1/personality/auth/reports/claim | 认领匿名报告 |
| GET | /api/v1/personality/auth/sessions | 登录设备列表 |
| DELETE | /api/v1/personality/auth/sessions/{session_id} | 撤销指定设备 |
| POST | /api/v1/personality/auth/sessions/revoke-others | 退出其他设备 |

请求/响应契约、错误信封与降级约定详见 design.md §3、§9。

---

## 4. 数据实体一览

| 表名 | 描述 | 状态 |
| -- | -- | -- |
| `surveys` | 问卷元数据（id, name） | 已实现 |
| `questions` / `questions_i18n` | 题目基础信息 / 多语言文本 | 已实现 |
| `opts` / `opts_i18n` | 选项维度与分数 / 多语言文本 | 已实现 |
| `answers` | 用户答卷记录（含 result、report_key_hash、deleted_at） | 已实现 |
| `users` | 用户账号（邮箱 + 密码） | 已实现（MVP） |
| `refresh_tokens` | Refresh Token（只存哈希） | 已实现（MVP） |
| `survey_metas` | 第三人问卷元数据（survey_id → target_role） | 已实现 |
| `relationship_analysis` | 「你与 Ta 的关系分析」预生成内容（本服务只读） | 已实现 |
| `reports` | 报告独立表（目标 schema 见 design.md §10） | 待实现 |

字段定义与 ER 图详见 design.md §4。

---

## 5. 国际化 (I18n)

支持的语言：
- zh-CN（中文简体，默认）
- en（English）
- ja（日本語）
- ko（한국어）
- es（Español）
- pt-BR（Português do Brasil）

不指定或指定不支持的语言时回退 zh-CN；按语言存储与组装的实现方式见 design.md §6。

---

## 6. 问卷数据

### 6.1 问卷清单

| 版本标记 | survey_id | 题数 | 说明 |
| -- | -- | -- | -- |
| v1 | 1 | 10 | |
| v1 | 2 | 10 | |
| gemini | 3 | 10 | 简答卷 |
| gemini | 4 | 20 | 标准答卷 |
| gemini | 5 | 40 | 完整答卷 |
| deepseek | 6 | 10 | 简答卷 |
| deepseek | 7 | 20 | 标准答卷 |
| deepseek | 8 | 40 | 完整答卷 |
| chatgpt | 9 | 10 | 简答卷 |
| chatgpt | 10 | 20 | 标准答卷 |
| chatgpt | 11 | 40 | 完整答卷 |
| third-person | 30 | 10 | 测测 Ta · 恋人 partner |
| third-person | 31 | 10 | 测测 Ta · 朋友 friend |
| third-person | 32 | 10 | 测测 Ta · 同事 colleague |
| third-person | 33 | 10 | 测测 Ta · 领导 boss |

### 6.2 选项分值规则
- 每个选项的 `score` 取值 1 或 5，分数高低代表该选项倾向维度的强度。
- 每道题 2 个选项，分别对应**同一维度对**的两个方向（E↔I、S↔N、T↔F、J↔P），其中一个 `score=5`、另一个 `score=1`。
- **平衡约束（必须满足）**：同一维度对内，`score=5` 落在两极（如 E 与 I）的题数差 ≤ 1。
  - 原因：后端计分是「选哪个选项就给哪个 `dim` 累加它的 `score`」。若 5 分总是落在同一极，选这一极会加 5、选另一极只加 1，结果会被系统性偏向拿 5 分的那一侧。
  - 例：EI 对 3 题 → 5 分落 E 侧与 I 侧的题数应为 2:1 或 1:2；TF 对 2 题 → 1:1。

### 6.3 第三人题库
- 每角色一卷共 10 题，中文源 JSON：`data/third_person/tp_{partner,friend,colleague,boss}.json`；SQL 灌入脚本见 `src/db/gen_third_person_sql.py`、`src/db/third_person*.sql`。
- 题目只描述**可观察行为**、禁止内心揣测；选项价值中性（不能一好一坏）；6.2 的分值与平衡约束同样适用。
- 内容与多语言翻译规范见 `ref/third_person_content_design.md`。

---

## 7. 当前状态与待办

### 7.1 已完成
- [x] Go 后端框架搭建（Gin + GORM + MySQL）
- [x] 三层架构：handler → service → model
- [x] 获取题目接口（含 i18n 按语言组装）
- [x] 提交答案接口（含打分计算）
- [x] 获取报告接口
- [x] MySQL 数据库初始化与连接池
- [x] 多语言支持（6 种语言）
- [x] 多问卷支持（v1 + 3 个来源 × 3 种规格，自测 survey_id 1~11）
- [x] **置信度算法** — 基于维度归一化边距法 + 区间映射的置信度计算，替代硬编码
- [x] **第三人测试（测测 Ta）** — 目录/取题/交卷/报告 4 接口，`survey_metas` 元数据校验，survey_id 30~33
- [x] **关系分析（你与 Ta）** — `relationship_analysis` 五元组精确命中查询接口（只读）
- [x] **用户账号体系（MVP）** — 邮箱+密码注册登录、JWT 会话、报告归属校验、基础限流
- [x] **账号报告与会话（P1）** — 我的报告列表、软删除、游客报告认领、跨设备会话管理
- [x] 单元测试（model/service/handler：打分、第三人、关系分析、账号、报告与会话）

### 7.2 待实现

> 以下为已规划但尚未实现的功能。**7.2 仅反映「尚未实现」的项目**，已实现功能请见 7.1。

- [ ] **结果解读模块 (F3)** — 类型描述、职业推荐、名人匹配、性格情感事业分析
- [ ] **报告独立表** — 当前 result 存储在 answers 表的 JSON 字段中，后续需独立为 reports 表（目标 schema 见 design.md §10）
- [ ] **前端界面** — 当前仅有后端 API，缺少用户交互界面
- [ ] **参数校验增强** — handler 层一些参数校验有 TODO 标记
- [ ] **旧版数据迁移** — questions 表中的 opts JSON 字段为旧版冗余数据，新版已迁移至 opts/opts_i18n 表

### 7.3 已知问题
- `questions` 表的 `text` 和 `opts` 字段为旧版设计（直接存储文本和选项 JSON），新版改为通过 `questions_i18n` + `opts` + `opts_i18n` 三表关联，目前两套方案并行。
- `answers` 表的 `result` 字段为临时字段，后续需独立成 `reports` 表。
- MySQL DSN 依赖配置文件中的明文密码。
- 错误信封不统一：基础/第三人接口返回 `{"error":"..."}`，关系分析与账号/报告/会话接口返回 `{"code":..,"message":..}`（前端已按两套适配；约定与降级矩阵见 design.md §9）。
- 第三人报告 `duration` 当前暂返回 0（起止时间解析待优化）；`target_role_label` 在报告中暂回退 zh-CN 文案，仅目录接口按 `lang` 返回。自测报告 `duration` 正常（毫秒）。
- `relationship_analysis` 内容由 ContentEngine 侧灌入，本服务只读；缺失组合按「无内容」降级（`data:null`）。
- 账号 MVP 与 P1 代码已实现；线上库若仍为旧 `users` 结构（`uid`/`name`，无邮箱/密码），启用账号功能前需执行 `scripts/upgrade_user_account.sh`，P1 需再执行 `scripts/upgrade_p1_report_sessions.sh`；两者均自动备份、失败自动回滚。
- 邮箱未验证，且 MVP 不提供找回密码；注册他人邮箱或忘记密码需人工支持（P1+ 邮件验证与重置流程）。
- 限流为进程内滑动窗口，仅适用于单实例；多实例部署时需替换为 Redis 等共享实现。
- 报告删除为软删除（`answers.deleted_at`），数据仍保留；后续需补清理任务或与账号注销联动。
- 撤销登录设备后 Refresh Token 立即失效，但 Access Token 最长仍有效 15 分钟；如需即时失效需引入黑名单。
- 历史匿名报告兼容依赖 `auth.legacy_report_cutoff` 时间窗（建议 30 天），到期后旧分享链接失效。
- 跨设备查看报告不需要 report_key；跨设备分享仍依赖本机保存的 report_key，P1 不做 key 轮换。
- 游客认领只处理本机保存了 `report_key` 的匿名报告；key 丢失或报告已删除则无法认领。
- 登录设备列表最多返回 50 条，超过时以 `has_more` 标记截断。
- 我的报告列表当前基于 `answers` 表；独立 `reports` 表落地后需迁移列表口径。
