# PersonalityMatrix — 后端设计文档

> 与 [requirement.md](requirement.md) 配套：产品需求、业务规则与功能清单见需求文档；本文记录技术设计与实现口径。
> 第三人模块专项设计见 `ref/third_person_test_design.md`、`ref/third_person_relation_analysis_api.md`，题库规范见 `ref/third_person_content_design.md`；用户账号体系（MVP）见 `ref/user_account_mvp_design.md`，P1 报告/会话见 `ref/p1_reports_sessions_design.md`；本文不重复其细节，只保留全局口径与跨模块约定。
> 工程规范（分层约束、Context 传递、事务边界、命名/日志、安全红线、命令）见 `AGENTS.md`，本文不重复。

---

## 1. 技术栈与环境配置

### 1.1 技术栈
| 层 | 技术 |
| -- | -- |
| 语言 | Go 1.25+ |
| HTTP 框架 | Gin v1.11 |
| ORM | GORM v1.31 (MySQL driver) |
| 数据库 | MySQL 8.0+ |
| 配置 | Viper (JSON 配置文件) |
| 部署 | Linux amd64，交叉编译后 scp 上传 |

### 1.2 环境配置
配置文件路径默认为 `../config/test.json`，可通过 `-config` 参数覆盖：

```json
{
    "env": "test",
    "port": 8082,
    "mysql": { "dsn": "user:pass@tcp(host:3306)/personality_db?charset=utf8mb4&parseTime=True&loc=Local" },
    "mongo": "mongodb://localhost:27017/test_db",
    "redis": "redis://localhost:6379/1",
    "auth": {
        "jwt_secret": "",
        "access_ttl_seconds": 900,
        "refresh_ttl_seconds": 2592000,
        "bcrypt_cost": 12,
        "legacy_report_cutoff": "",
        "enforce_report_ownership": true,
        "trusted_proxies": ["127.0.0.1", "::1"]
    }
}
```

- `auth.jwt_secret` 仅为开发占位；生产必须留空并通过环境变量 `PERSONALITY_AUTH_JWT_SECRET` 注入（≥32 字节，缺失/过短启动失败）。
- Viper 使用前缀 `PERSONALITY` 且 `.`→`_`，例如 `auth.legacy_report_cutoff` 可由 `PERSONALITY_AUTH_LEGACY_REPORT_CUTOFF` 覆盖。
- `legacy_report_cutoff` 为 RFC3339；为空表示不启用历史匿名报告兼容。
- `enforce_report_ownership` 默认 `true`，仅新旧前端混跑的过渡期可临时置 `false`。
- `trusted_proxies` 缺省仅信任 loopback，防止 `X-Forwarded-For` 伪造。
- 测试环境可将 `bcrypt_cost` 调低以加速测试；生产必须 ≥10（默认 12）。

### 1.3 部署与密钥注入

- 编译：本地 `cd src && go build -o myapp .`；部署用 `GOOS=linux GOARCH=amd64 go build -o myapp-linux .`。
- 发布：`./scripts/deploy.sh` 编译、打包、rsync 上传并触发远程 `deploy_remote.sh`（`releases/` + `current` 软链 + systemd 重启）。
- 新服务器先执行 `./scripts/bootstrap_server_env.sh`，生成 `shared/mbti-api.env`（`PERSONALITY_AUTH_JWT_SECRET`，权限 600）与 systemd drop-in `EnvironmentFile=`。
- `deploy_remote.sh` 在发布前校验 env 文件与 systemd drop-in，缺失即失败；密钥位于 `shared/`，不随 release 覆盖。
- 应用以 `-config` 指定 JSON 配置；生产密钥不得写入 `config/*.json`。

---

## 2. 架构分层

三层架构：`handler`（传输层：参数解析、参数校验、组装响应）→ `service`（业务层：题目组装、打分、事务）→ `model`（模型层：领域结构、DB 映射、打分算法）。目录与职责映射、约束细则见 `AGENTS.md` §3~§4。

---

## 3. API 设计

### 3.1 获取题目

```
GET /api/v1/personality/questions?survey_id={int}&lang={string}
```

| 参数 | 说明 | 默认值 |
| -- | -- | -- |
| survey_id | 问卷 ID | 0 |
| lang | 语言代码，支持 zh-CN / en / ja / ko / es / pt-BR | zh-CN |

**响应**:
```json
{
    "code": 0,
    "data": {
        "questions": [
            {
                "id": 21,
                "text": "大半夜肚子饿得睡不着...",
                "opts": [
                    { "id": 1, "text": "疯狂咽口水...", "dim": "j", "score": 1 },
                    { "id": 2, "text": "管他的！...", "dim": "p", "score": 5 }
                ]
            }
        ]
    }
}
```

### 3.2 提交答案

```
POST /api/v1/personality/submit-answers
```

**请求体**:
```json
{
    "survey_id": 1,
    "uid": 2000,
    "start_time": 20060102150405,
    "end_time": 20060102150405,
    "opt_selections": [
        { "qid": 1, "opt_id": 1 },
        { "qid": 2, "opt_id": 2 }
    ],
    "lang": "zh-CN"
}
```

> `uid` 已废弃：服务端只从 `Authorization: Bearer <access_token>` 取用户身份，匿名为 0；请求体中的 `uid` 一律忽略。

**响应**:
```json
{
    "code": 0,
    "data": { "report_id": 100, "report_key": "rk_9xQ..." }
}
```

> `report_key` 只在交卷响应中出现一次，用于匿名/分享读取报告；客户端必须持久化。

### 3.3 获取报告

```
GET /api/v1/personality/report?report_id={int}
Authorization: Bearer {access_token}   # 可选
X-Report-Key: rk_...                   # 可选
```

访问规则：登录本人，或持有与 `answers.report_key_hash` 匹配的 `report_key`。不满足返回 `404 {"error":"Report not found"}`（不区分不存在与无权，避免探测）。历史匿名报告可在 `auth.legacy_report_cutoff` 之前按 id 访问。已软删除（`answers.deleted_at` 非空）的报告视为不存在。

**响应**:
```json
{
    "code": 0,
    "data": {
        "duration": 1000,
        "result_type": "ENTJ",
        "confidence": 7500,
        "scores": [
            { "dim": "E", "score": 1 },
            { "dim": "I", "score": 0 },
            { "dim": "S", "score": 0 },
            { "dim": "N", "score": 1 },
            { "dim": "T", "score": 1 },
            { "dim": "F", "score": 0 },
            { "dim": "J", "score": 1 },
            { "dim": "P", "score": 0 }
        ]
    }
}
```

### 3.4 第三人问卷目录

```
GET /api/v1/personality/third-person/surveys?lang={string}
```

| 参数 | 说明 | 默认值 |
| -- | -- | -- |
| lang | 语言代码（用于关系文案），支持集合同 3.1 | zh-CN |

**响应**:
```json
{
    "code": 0,
    "data": {
        "surveys": [
            { "survey_id": 30, "target_role": "partner", "target_role_label": "恋人", "question_count": 10 }
        ]
    }
}
```

### 3.5 第三人取题

```
GET /api/v1/personality/third-person/questions?survey_id={int}&lang={string}
```

参数与响应结构同 3.1（`survey_id` 须为第三人卷 30~33）。
- `survey_id` 非法（≤0）→ `400 {"error":"Invalid survey_id"}`。
- 非第三人问卷或未启用 → `404 {"error":"Third person survey not found"}`。

### 3.6 第三人提交答案

```
POST /api/v1/personality/third-person/submit-answers
```

请求体与响应结构同 3.2。
- 非第三人问卷或未启用 → `404 {"error":"Third person survey not found"}`。

### 3.7 第三人报告

```
GET /api/v1/personality/third-person/report?report_id={int}
```

**响应**（3.3 响应字段 + 视角字段）:
```json
{
    "code": 0,
    "data": {
        "duration": 0,
        "result_type": "ENTJ",
        "confidence": 7500,
        "scores": [
            { "dim": "E", "score": 1 },
            { "dim": "I", "score": 0 }
        ],
        "perspective": "third_person",
        "target_role": "partner",
        "target_role_label": "恋人"
    }
}
```

- `report_id` 非法、报告不存在、或非第三人卷 → `404 {"error":"Report not found"}`。

### 3.8 关系分析（你与 Ta）

```
GET /api/v1/personality/third-person/relation-analysis
    ?relation_type={string}&type_a={string}&type_b={string}&pattern={string}&lang={string}
```

| 参数 | 必填 | 说明 |
| -- | -- | -- |
| relation_type | 是 | 关系类型：`partner` / `friend` / `colleague` / `boss` |
| type_a | 是 | 自测方（你）MBTI，16 型之一；入参大小写不敏感，内部转大写 |
| type_b | 是 | 第三人（Ta）MBTI，16 型之一；入参大小写不敏感，内部转大写 |
| pattern | 是 | 四位差异标记，每位仅 `H`（差异大）/`L`（相近）；顺序固定 E/I、S/N、T/F、J/P（计算口径见 §8） |
| lang | 否 | 语言代码，白名单外回退 zh-CN |

**响应（命中）**:
```json
{
    "code": 0,
    "data": {
        "relation_type": "partner",
        "type_a": "INTJ",
        "type_b": "ENFP",
        "locale": "zh-CN",
        "pattern": "HLHH",
        "content": "……（关系总述）",
        "scenarios": [
            { "key": "planning", "title": "计划", "text": "……" }
        ],
        "advice": ["……"],
        "chunk_ids": [6526, 6554, 6863]
    }
}
```

- 未命中（组合不存在或 `content` 为空）→ `200 {"code":0,"data":null}`，前端静默隐藏模块。
- 参数非法（relation_type / type_a / type_b / pattern）→ `400 {"code":400,"message":"invalid ..."}`。
- 数据库或 JSON 解析失败 → `500 {"code":500,"message":"Failed to get relation analysis"}`。

> 错误信封与基础接口不一致的原因与约定详见 §9。

### 3.9 用户账号（MVP）

接口前缀 `/api/v1/personality/auth`，完整契约、表结构与安全设计见 `ref/user_account_mvp_design.md`：

| 方法 | 路径 | 认证 | 用途 |
| -- | -- | -- | -- |
| POST | /register | 无 | 注册并自动登录 |
| POST | /login | 无 | 登录 |
| POST | /refresh | 无（凭 refresh token） | 轮换 refresh token |
| POST | /logout | 无（凭 refresh token） | 登出当前设备 |
| GET | /me | Bearer | 当前用户 |
| POST | /change-password | Bearer | 修改密码并撤销旧会话 |
| PATCH | /profile | Bearer | 修改昵称/语言 |

- 新接口统一使用 `{"code":0,"data":...}` / `{"code":<http>,"message":"..."}` 信封。
- Access Token 15 分钟，Refresh Token 30 天并在 `refresh_tokens` 表中存哈希；轮换与重放检测规则见专项文档。
- Access Token（HS256，显式校验算法）声明：

```json
{
  "iss": "personality-matrix",
  "sub": "10001",
  "uid": 10001,
  "sid": "0123456789abcdef0123456789abcdef",
  "jti": "<16 字节 hex>",
  "iat": 1760000000,
  "exp": 1760000900
}
```

  - `uid` 用于鉴权，`sub` 必须与 `uid` 一致；`sid` 为当前 Refresh Token 的 `family_id`，旧 token 可为空。
  - 会话相关接口遇到无 `sid` 的旧 token 返回 `401`，前端刷新后重试；普通鉴权与报告读取不要求 `sid`。
- 限流为进程内滑动窗口：注册 3 次/小时 + 10 次/天/IP，登录 20 次/分钟/IP 且 5 次/分钟/IP+邮箱，刷新 30 次/分钟/IP，匿名交卷 30 次/分钟/IP（登录用户 120 次/分钟/UID），读报告 60 次/分钟/IP；超限 `429` + `Retry-After`。
- `submit-answers` / `report` / 第三人对应接口接入可选认证；`uid` 只从 token 获取，请求体 `uid` 忽略。

### 3.10 账号报告与会话（P1）

完整契约与前端设计见 `ref/p1_reports_sessions_design.md`；接口前缀同样为 `/api/v1/personality/auth`：

| 方法 | 路径 | 用途 |
| -- | -- | -- |
| GET | /reports | 我的报告列表（游标分页、视角筛选） |
| DELETE | /reports/{report_id} | 软删除自己的报告 |
| POST | /reports/claim | 认领匿名报告（凭 report_key） |
| GET | /sessions | 登录设备列表 |
| DELETE | /sessions/{session_id} | 撤销指定设备 |
| POST | /sessions/revoke-others | 退出其他设备 |

- 报告列表按 `report_id DESC` 游标分页，`limit` 默认 20、最大 50；支持 `perspective=self|third_person`，返回 `next_cursor` / `has_more`。
- 报告删除为软删除：`answers.deleted_at`，列表与报告读取接口统一过滤；重复删除幂等。
- 会话列表基于 `refresh_tokens` family；JWT 的 `sid` claim 识别当前设备，`session_id` 即 `family_id`（32 位小写 hex）。
- 会话列表只返回未撤销且未过期的活跃会话，最多 50 条并以 `has_more` 标记截断；只返回 `ip_masked`，不返回原始 IP、token 或 report_key。
- 撤销单个设备仅能操作本人会话；`current=true` 表示当前设备，前端需清理本地会话。
- 游客认领只接受 `uid=0`、未删除且 `report_key` 匹配的报告；每批最多 20 条，重复 `report_id` 去重，未删除且已归属当前用户的重复提交视为幂等成功。
- P1 接口按 UID 限流：报告/会话列表 60 次/分钟，删除报告 30 次/分钟，认领 10 次/分钟，撤销会话 20 次/分钟。

---

## 4. 数据库设计

### 4.1 表结构概览

| 表名 | 描述 | 状态 |
| -- | -- | -- |
| `surveys` | 问卷元数据（id, name） | 已实现 |
| `questions` | 题目基础信息 | 已实现 |
| `questions_i18n` | 题目多语言文本 | 已实现 |
| `opts` | 选项维度与分数 | 已实现 |
| `opts_i18n` | 选项多语言文本 | 已实现 |
| `answers` | 用户答卷记录（含 `report_key_hash`、`deleted_at`） | 已实现 |
| `users` | 用户账号 | 已实现（MVP） |
| `refresh_tokens` | Refresh Token（只存哈希） | 已实现（MVP） |
| `survey_metas` | 第三人问卷元数据（survey_id → target_role） | 已实现 |
| `relationship_analysis` | 「你与 Ta 的关系分析」预生成内容（本服务只读） | 已实现 |
| `reports` | 报告独立表（规划中，目标 schema 见 §10） | 待实现 |

### 4.2 核心表定义

#### questions
| 字段 | 类型 | 说明 |
| -- | -- | -- |
| id | bigint unsigned PK | 题目 ID |
| survey_id | int unsigned | 所属问卷 ID |
| seq | int unsigned | 题目顺序号 |
| text | varchar(256) | 题目文本（旧版字段，新版用 i18n 表） |
| opts | json | 选项 JSON（旧版冗余字段） |
| brief | varchar(100) | 题目简要说明 |

#### questions_i18n
| 字段 | 类型 | 说明 |
| -- | -- | -- |
| id | bigint PK | |
| question_id | bigint | 关联 questions.id |
| lang | varchar | 语言代码（zh-CN/en/ja/ko/es/pt-BR） |
| text | text | 题目文本 |
| brief | text | 题目简要说明 |

#### opts
| 字段 | 类型 | 说明 |
| -- | -- | -- |
| id | bigint PK | |
| question_id | bigint | 关联 questions.id |
| seq | tinyint unsigned | 选项排序 |
| dim | varchar | 所属维度（E/I/S/N/T/F/J/P） |
| score | tinyint | 该选项得分（取值 1 或 5） |

#### opts_i18n
| 字段 | 类型 | 说明 |
| -- | -- | -- |
| id | bigint PK | |
| opt_id | bigint | 关联 opts.id |
| lang | varchar | 语言代码 |
| text | text | 选项文本 |

#### answers
| 字段 | 类型 | 说明 |
| -- | -- | -- |
| id | bigint PK | 答卷 ID（也用作 report_id） |
| survey_id | bigint | 关联问卷 ID |
| uid | bigint | 用户 ID |
| opt_selections | json / text | 用户选项选择列表 `[{qid, opt_id}]` |
| result | json / text | 计算结果 JSON（MBTI 分数+类型） |
| report_key_hash | char(64) | 匿名/分享报告访问键哈希（`sha256(report_key)`） |
| deleted_at | datetime(3) | 软删除时间；NULL=未删除 |
| start_time | datetime | 开始答题时间 |
| end_time | datetime | 提交答题时间 |

- 索引：`idx_uid_created (uid, created_at)`、`idx_uid_deleted_id (uid, deleted_at, id)`。
- 报告列表/读取只使用 `deleted_at IS NULL` 的记录。

#### users
| 字段 | 类型 | 说明 |
| -- | -- | -- |
| id | bigint unsigned PK | 用户 ID，对外即 `uid` |
| email | varchar(254) | 规范化后的小写邮箱，唯一键 `uk_email` |
| password_hash | varchar(255) | bcrypt 哈希，不存明文 |
| display_name | varchar(50) | 昵称，空时取邮箱 @ 前部分 |
| status | tinyint unsigned | 1=active 2=disabled 3=deleted（MVP 只用 1） |
| lang | varchar(8) | 语言，默认 `zh-CN` |
| last_login_at | datetime(3) | 最近登录时间 |
| created_at / updated_at | datetime(3) | |

#### refresh_tokens
| 字段 | 类型 | 说明 |
| -- | -- | -- |
| id | bigint unsigned PK | |
| uid | bigint unsigned | 关联 `users.id`（不建外键） |
| token_hash | char(64) | `sha256(refresh_token)` hex，唯一键 `uk_token_hash` |
| family_id | char(32) | 一次登录的设备会话族，即对外 `session_id` |
| expires_at | datetime(3) | 过期时间（默认 30 天） |
| revoked_at | datetime(3) | 撤销时间，NULL=有效 |
| user_agent / ip | varchar | 登录/刷新时的客户端信息（原始 IP 仅存库） |
| created_at | datetime(3) | 同时作为会话最近活跃时间 |

- 索引：`idx_uid_expires (uid, expires_at)`、`idx_family (family_id)`。
- 轮换沿用 `family_id`；撤销 family 即撤销该设备全部 token。
- 过期清理：`DELETE FROM refresh_tokens WHERE expires_at < NOW() - INTERVAL 7 DAY;`
- 迁移：账号 MVP 使用 `src/db/user_account.sql` / `scripts/upgrade_user_account.sh`；P1 的 `answers.deleted_at` 使用 `src/db/p1_report_sessions.sql` / `scripts/upgrade_p1_report_sessions.sh`。脚本均支持 dry-run、备份与失败回滚。

#### survey_metas
| 字段 | 类型 | 说明 |
| -- | -- | -- |
| id | bigint unsigned PK | |
| survey_id | bigint unsigned | 关联 questions.survey_id，唯一键 `uk_survey_id` |
| target_role | varchar(16) | 被测关系：partner/friend/colleague/boss |
| enabled | tinyint unsigned | 0=下线 1=上线 |
| created_at / updated_at | datetime(3) | |

#### relationship_analysis
| 字段 | 类型 | 说明 |
| -- | -- | -- |
| id | bigint unsigned PK | |
| relation_type | varchar(16) | partner/friend/colleague/boss |
| type_a | char(4) | 自测方（你）MBTI |
| type_b | char(4) | 第三人（Ta）MBTI |
| locale | varchar(8) | 语言代码 |
| pattern | char(4) | 四维差异标记（H/L，顺序 EI、SN、TF、JP） |
| content | mediumtext | 关系总述正文 |
| scenarios | json | 相处场景 `[{key,title,text}]` |
| advice | json | 建议列表 `["...", "..."]` |
| chunk_ids | json | 溯源知识库 chunk id 列表 |
| gen_model / tier / words | | 内容生成元信息（生成模型、模板/LLM 层级、字数） |
| source_version / content_version | varchar(64) | 内容版本 |
| status | varchar(16) | 内容状态，查询仅取 `ready` |
| created_at / updated_at | datetime | |

- 唯一键 `uk_combo (relation_type, type_a, type_b, pattern, locale)`，五元组精确命中一行。
- 本服务**只读**；内容由 ContentEngine pairanalysis 管线预生成灌入（DDL 见 `ContentEngine/ref/third_person/relationship_analysis.sql`）。

### 4.3 ER 图
见 [personality_db.png](personality_db.png)。（注：ER 图暂未含 `users` / `refresh_tokens` / `survey_metas` / `relationship_analysis`）

---

## 5. 打分与置信度算法

### 5.1 计分流程
1. 查询指定问卷的所有题目及选项。
2. 遍历用户的选项选择列表 `opt_selections`。
3. 对每个选择的选项，累加其 `dim` 维度的 `score` 值。
4. 得到 8 个维度的总分（E/I/S/N/T/F/J/P）。

### 5.2 类型判定
| 对比维度 | 胜出条件 |
| -- | -- |
| E vs I | 分高者为最终类型中的该字母 |
| S vs N | 同上 |
| T vs F | 同上 |
| J vs P | 同上 |

得分相等时，取前者（如 I>=E 取 I，N>=S 取 N，T>=F 取 T，J>=P 取 J）。

### 5.3 置信度算法

置信度衡量人格类型结果的明确程度。算法基于**维度归一化边距法**，并做区间映射避免极端值：

1. 对每个维度对（E/I、S/N、T/F、J/P），统计该对的总题数 N。
2. 计算该对的得分边距：`margin = |dim1_score - dim2_score|`
3. 归一化：`dim_confidence = margin / (5 × N)`，取值范围 [0, 1]。
   - 5 是单题最高得分。5×N 代表用户全部选择同一极且每次都命中强力选项的理论最大边距。
4. 原始置信度 `rawAvg = avg(4 个 dim_confidence)`（无答题数据的维度对不参与平均）。
5. 区间映射（避免输出 0 或 10000 这类不可信的极端值）：`adjusted = 0.30 + rawAvg × (0.92 − 0.30)`
6. 最终置信度 = `round(adjusted × 10000)`，输出范围约 **[3000, 9200]**。

**示例**（10 题问卷，JP 对 4 题，用户 JP 得分 J=1, P=18）：
```
dim_confidence(JP) = |1 - 18| / (5 × 4) = 17/20 = 0.85
若四个维度对的 dim_confidence 均为 0.85：
final = (0.30 + 0.85 × 0.62) × 10000 ≈ 8270
```

**特征**：
- 选择越一致（总选同一极），边距越大 → 置信度越高。
- 选择强度越大（总是选 score=5 的选项），边距越大 → 置信度越高。
- 题数越少，最大边距 5×N 越小 → 置信度上限降低，反映信息量不足。
- 不同问卷间通过除以 5×N 归一化，结果可比；区间映射为统一线性变换，不破坏可比性。
- 若某维度对用户无任何答题数据，该对不参与平均。

> 注：在「1 或 5 + 平衡」取值下（见 requirement.md §6.2），用户即使在一个维度对内完全一致，实际边距上限也约为 `3×N`（低于理论最大 `5×N`），故单对 `dim_confidence` 通常落在 0.6 附近、很少接近 1.0。这是既有算法以 `5` 作为统一分母的固有特性，并非缺陷；只要所有问卷统一遵循「1 或 5 + 平衡」，跨问卷置信度即可保持可比。

---

## 6. i18n 实现方式

- 题目文本和选项文本通过 `questions_i18n` 和 `opts_i18n` 表按语言存储。
- 接口通过 `lang` 参数指定语言。
- 不指定或指定不支持的语言时，回退到 zh-CN。

---

## 7. 核心数据流

### 7.1 交卷 → 打分 → 落库
```
POST /submit-answers（自测）或 /third-person/submit-answers（第三人）
  handler:  OptionalAuth 解析 uid（匿名=0），绑定 PersonalityAnswer
            （survey_id/start_time/end_time/opt_selections/lang，请求体 uid 忽略）；
            校验 survey_id；第三人卷先查 survey_metas（无 meta/未启用 → 404）
  service:  ① 查该 survey 的全部题目与选项（i18n 组装）
            ② 遍历 opt_selections，按所选项 dim 累加 score → 8 维总分 MBTIScore
            ③ countDimQuestions 统计各维度对题数（EI/SN/TF/JP）
            ④ ToResult(dimPairCount)：类型判定（5.2）+ 置信度（5.3）
            ⑤ 生成 report_key，sha256 后与 result JSON、uid 一并写入 answers
            ⑥ 返回 answers.id 作为 report_id + 明文 report_key（仅此一次）
```

### 7.2 报告读取
```
GET /report（自测）或 /third-person/report（第三人）
  handler:  OptionalAuth 取 uid；解析 report_id；读取 X-Report-Key
  service:  按 id 查 answers（第三人卷 JOIN survey_metas，target_role 为空视为 404）
            归属校验：本人 token 或 report_key 哈希匹配，否则 404
            历史兼容：uid=0 且 created_at < legacy_report_cutoff 时允许按 id 访问
            ParseMBTIResult 解析 result JSON → ReportResp
            duration = end_time − start_time（毫秒；第三人报告当前暂返回 0，见 requirement.md §7.3）
```

### 7.3 关系分析查询
```
GET /third-person/relation-analysis
  handler:  校验 relation_type / type_a / type_b / pattern 格式（非法 → 400）
  service:  五元组精确查 relationship_analysis（status='ready'）
            未命中或 content 空 → (nil, nil) → 200 + data:null（前端静默隐藏）
            解析 scenarios/advice/chunk_ids JSON → 响应
```

### 7.4 注册 / 登录 / 刷新 / 登出
```
POST /auth/register | /auth/login
  handler:  限流、邮箱/密码/昵称/语言校验
  service:  规范化邮箱 → 查重/校验密码 →
            生成 refresh token（新 family_id，存 sha256）→ 签发 access（含 uid+sid）
            注册在同一事务内写 users + refresh_tokens
  response: user + access_token + refresh_token + expires_in
POST /auth/refresh
  service:  sha256 查 token → 校验过期/撤销 → 重放检测（10 秒宽限）→
            条件更新旧 token revoked_at + 插入同 family 新 token → 新 access+refresh
POST /auth/logout
  service:  按 refresh token 找到 family → 撤销该 family（幂等）
```

### 7.5 我的报告 / 删除 / 认领 / 会话
```
GET /auth/reports
  service:  answers WHERE uid=? AND deleted_at IS NULL
            [AND id < cursor] [perspective 过滤] ORDER BY id DESC LIMIT limit+1
            LEFT JOIN surveys / survey_metas / questions 题量统计
            result JSON 可解析才返回 result_type/confidence，否则 result_available=false
DELETE /auth/reports/{id}
  service:  UPDATE answers SET deleted_at=now WHERE id=? AND uid=? AND deleted_at IS NULL
            已删除再删：确认归属后返回成功（幂等）；非本人/不存在 → 404
POST /auth/reports/claim
  service:  仅 uid=0 + 未删除 + report_key 哈希匹配 → 更新 uid 为当前用户
            已归属当前用户视为成功；其他失败项不返回原因
GET /auth/sessions
  service:  查 refresh_tokens 中未撤销未过期记录，按 family 去重，最多 50 条
            current = family_id == token.sid；IP 脱敏后返回
DELETE /auth/sessions/{sid}
  service:  仅撤销本人 family；返回被撤销的是否当前设备
POST /auth/sessions/revoke-others
  service:  撤销除当前 family 外全部活跃会话，返回撤销数量
```

---

## 8. relation pattern 计算口径

pattern 为四位差异标记（如 `HHLH`），是关系分析内容的查找键之一。**运行时由前端计算、后端仅校验格式**（`[HL]{4}`）并原样回显。

| 项 | 口径 |
| -- | -- |
| 顺序 | 固定 E/I、S/N、T/F、J/P 四个维度对 |
| 单对计算 | 取双方在该维度对的**左极占比** `left / (left + right)`（换算为百分点 0~100；两极总分 ≤0 时记 50%） |
| 判定 | 两份报告左极占比差的绝对值 `> 20`（百分点，阈值为产品可调常量）→ `H`（差异大），否则 `L`（相近） |
| 实现参考 | 前端 `utils/thirdPersonReport.ts` 的 `computeRelationPattern` / `RELATION_PATTERN_THRESHOLD` |

> 注意：这是**占比差**口径，而非原始分差。早期注释（如 ContentEngine DDL 备注 `H=|scoreA-scoreB|>20`）为简化描述，以本表为准。

---

## 9. 错误处理与响应信封

系统并存两套错误信封（历史演进所致，前端已按两套适配）：

| 接口族 | 成功 | 参数非法 | 未命中 | 服务/DB 错误 |
| -- | -- | -- | -- | -- |
| 基础三接口（3.1~3.3） | `200 {"code":0,"data":...}` | `400 {"error":"..."}` | 报告不存在/无权：`404 {"error":"Report not found"}` | `500 {"error":"..."}` |
| 第三人目录/取题/交卷/报告（3.4~3.7） | 同上 | `400 {"error":"..."}` | `404 {"error":"..."}`（无 meta / 报告不存在 / 无权） | `500 {"error":"..."}` |
| 关系分析（3.8） | `200 {"code":0,"data":...}` | `400 {"code":400,"message":"invalid ..."}` | `200 {"code":0,"data":null}`（静默降级） | `500 {"code":500,"message":"..."}` |
| 用户账号（3.9） | `200 {"code":0,"data":...}` | `400 {"code":400,"message":"..."}` | `401/409`（见专项文档） | `500 {"code":500,"message":"..."}` |
| 账号报告/会话（3.10） | `200 {"code":0,"data":...}` | `400 {"code":400,"message":"..."}` | `401/404`（不存在或无权） | `500 {"code":500,"message":"..."}` |

约定原则：
- 关系分析模块**任何异常不得阻塞报告页**：内容缺失一律 `200 data:null`，仅参数非法/系统错误才返回非 200。
- 新增接口优先采用 `{"code":..,"message":..}` 信封；改造旧接口需与前端同步，不在本服务单侧切换。
- 所有限流超限统一返回 `429` + `Retry-After`（基础/第三人旧接口沿用 `{"error":"Too many requests"}`，账号接口用新信封）。
- 报告/会话不存在与无权访问统一返回 `404`，避免通过状态码探测资源归属。

---

## 10. 规划中：reports 表（未定稿）

当前计算结果临时存 `answers.result` JSON 字段。目标是独立 `reports` 表，草案字段方向：

| 字段 | 类型 | 说明 |
| -- | -- | -- |
| id | bigint PK | 报告 ID（对外 report_id） |
| answer_id | bigint | 关联 answers.id |
| survey_id | bigint | 所属问卷 |
| uid | bigint | 用户 ID |
| perspective | varchar(16) | self / third_person |
| target_role | varchar(16) | 第三人卷的被测关系（自测为空） |
| result_type | char(4) | MBTI 类型 |
| confidence | int | 置信度（映射后） |
| scores | json | 8 维得分 |
| duration_ms | bigint | 答题用时 |
| created_at | datetime | |

迁移路径：双写过渡（写 answers.result 的同时写 reports）→ 读切 reports → 废弃 `answers.result`。schema 与迁移方案定稿后再更新本文档与需求文档。
