# 用户账号体系（MVP）设计

> 状态：设计定稿，待实现
> 范围：邮箱 + 密码注册登录、JWT 会话、报告归属校验、基础限流
> 关联文档：`requirement.md` §7.2、`design.md` §3/§4/§9、`AGENTS.md`
> 非目标：邮箱验证、找回密码、第三方登录、短信、注销/导出、角色后台（见 §14）

---

## 1. 背景与目标

### 1.1 现状问题

| 问题 | 位置 | 影响 |
| -- | -- | -- |
| `users` 只有 model，无建表/注册/登录/鉴权 | `src/model/db_personality.go:32` | 账号体系为空壳 |
| `uid` 由前端请求体自报 | `model.PersonalityAnswer.UID` | 可伪造身份，答卷归属不可信 |
| `report_id` 为 `answers` 自增 id，无访问控制 | `GetReport` / `GetThirdPersonReport` | 可枚举、越权读取他人报告（IDOR） |
| `GetReport` 字符串拼接 SQL | `src/service/personality_matrix.go:277` | SQL 注入（`AGENTS.md` 已知风险） |
| 无会话/撤销机制 | — | 无法登出、无法失效凭证 |

### 1.2 MVP 目标

1. 建立真实用户账号（邮箱 + 密码），支持注册、登录、登出、刷新、改密、查看/修改资料。
2. 会话采用 **短效 Access JWT + 长效可撤销 Refresh Token**。
3. 现有答题接口保持**匿名可用**，但 `uid` 只信任 token，不再信任请求体。
4. 报告读取引入归属校验 + 匿名报告访问键，关闭 IDOR；同时修复 SQL 注入。
5. 基础安全：密码哈希、token 轮换、登录限流、日志脱敏、密钥不入库。
6. 不引入新基础设施（不依赖 Redis），单实例可上线；为后续水平扩展留接口。

---

## 2. 范围

### 2.1 MVP 包含

- `users` / `refresh_tokens` 两张新表。
- `answers` 增加 `report_key_hash` 字段与 `uid` 索引。
- 注册、登录、刷新、登出、当前用户、修改密码、修改资料 7 个接口。
- 鉴权中间件（强制 / 可选两种）。
- 现有 4 个交卷/报告接口接入账号与归属校验。
- 匿名报告访问键（`report_key`）与历史报告兼容窗口。
- 登录/注册/刷新/交卷/读报告限流（进程内）。
- 单元测试、集成测试、上线迁移脚本与回滚说明。

### 2.2 MVP 不包含（P1+，见 §14）

- 邮箱验证、找回密码、修改邮箱。
- Google / Apple / 微信等第三方登录。
- 手机号 + 短信验证码。
- 账号注销、数据导出、隐私合规流程。
- 管理后台、角色权限（RBAC）。
- 我的报告列表、跨设备会话管理、分享链接管理。
- Redis 分布式限流/黑名单、JWT 密钥轮换。

---

## 3. 关键决策

| # | 决策 | 取值 | 理由 |
| -- | -- | -- | -- |
| D1 | 登录标识 | 邮箱 + 密码 | 成本最低，后续可扩展手机号/第三方 |
| D2 | 会话方案 | Access JWT（15 min）+ 不透明 Refresh Token（30 天，存 MySQL） | Access 无状态；Refresh 可撤销、可轮换 |
| D3 | 匿名使用 | 交卷可不登录；`uid=0` | 不破坏现有匿名答题流程 |
| D4 | 身份来源 | 仅从 Access Token 取 `uid` | 请求体 `uid` 视为废弃字段，忽略 |
| D5 | 报告访问 | 登录本人 **或** 持有效 `report_key` | 同时支持私有与分享 |
| D6 | 历史报告 | 配置时间点之前的报告允许按 id 访问，设 30 天窗口 | 兼容已分享链接，窗口后关闭 |
| D7 | 密码哈希 | bcrypt cost 12 | `golang.org/x/crypto` 已在依赖中，稳定简单 |
| D8 | 错误信封 | 新增 auth 接口用 `{"code","message"}`；旧接口保留 `{"error"}` | 遵循 `design.md` §9，避免前端大改 |
| D9 | 限流 | 进程内滑动窗口，单实例假设 | MVP 不引入 Redis；接口预留可替换实现 |
| D10 | 数据库外键 | 不新增外键，仅加索引 | 与现有表风格一致，降低迁移风险 |
| D11 | 邮箱验证 | MVP 不做 | 无邮件服务；接受“邮箱归属未验证”的已知限制 |
| D12 | 多端登录 | 每次登录一个 token family，互不影响 | 登出只影响当前设备 |

---

## 4. 总体架构

```
Client
  │  Authorization: Bearer <access_token>（可选）
  │  X-Report-Key: <report_key>（匿名/分享读报告时）
  ▼
Gin Router
  ├─ 公开路由：questions / third-person/surveys / relation-analysis
  ├─ OptionalAuth：submit-answers / third-person/submit-answers
  ├─ OptionalAuth + 报告归属校验：report / third-person/report
  └─ RequireAuth：auth/me / auth/profile / auth/change-password
        │
        ▼
handler（参数解析、校验、响应）
        │
        ▼
service/auth（注册、登录、token 轮换、改密）
service/personality（交卷、报告归属）
        │
        ├─ repository（GORM 实现，可替换为测试 fake）
        └─ util/jwt、util/password、util/ratelimit
        │
        ▼
MySQL（users / refresh_tokens / answers）
```

分层约束沿用 `AGENTS.md`：参数校验在 handler；事务在 service；Context 从 `c.Request.Context()` 向下传递；业务代码不 `panic`。

---

## 5. 数据模型

### 5.1 `users`

```sql
CREATE TABLE IF NOT EXISTS `users` (
  `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `email`         VARCHAR(254)    NOT NULL COMMENT '规范化后的小写邮箱',
  `password_hash` VARCHAR(255)    NOT NULL COMMENT 'bcrypt hash',
  `display_name`  VARCHAR(50)     NOT NULL DEFAULT '',
  `status`        TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '1=active 2=disabled 3=deleted',
  `lang`          VARCHAR(8)      NOT NULL DEFAULT 'zh-CN',
  `last_login_at` DATETIME(3)     NULL,
  `created_at`    DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at`    DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户账号';
```

- 旧 `DBUser.UID` 冗余字段废弃，`users.id` 即对外 `uid`。
- `email` 入库前统一 `strings.TrimSpace` + `strings.ToLower`。
- `status` MVP 只使用 `1`；`2/3` 为后续禁用/注销预留。
- 不存明文密码、不存 token。

### 5.2 `refresh_tokens`

```sql
CREATE TABLE IF NOT EXISTS `refresh_tokens` (
  `id`         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `uid`        BIGINT UNSIGNED NOT NULL,
  `token_hash` CHAR(64)        NOT NULL COMMENT 'sha256(refresh_token) hex',
  `family_id`  CHAR(32)        NOT NULL COMMENT '一次登录的设备会话族',
  `expires_at` DATETIME(3)     NOT NULL,
  `revoked_at` DATETIME(3)     NULL,
  `user_agent` VARCHAR(255)    NOT NULL DEFAULT '',
  `ip`         VARCHAR(45)     NOT NULL DEFAULT '',
  `created_at` DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_token_hash` (`token_hash`),
  KEY `idx_uid_expires` (`uid`, `expires_at`),
  KEY `idx_family` (`family_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='刷新令牌';
```

- 只存 SHA-256，不存明文；明文只在响应中出现一次。
- `family_id`：登录时随机生成（16 字节 hex，32 字符）；轮换时沿用。
- 过期清理（运维每日执行）：
  ```sql
  DELETE FROM refresh_tokens WHERE expires_at < NOW() - INTERVAL 7 DAY;
  ```

### 5.3 `answers` 变更

```sql
ALTER TABLE `answers`
  ADD COLUMN `report_key_hash` CHAR(64) NULL COMMENT '匿名/分享报告访问键 sha256' AFTER `result`,
  ADD KEY `idx_uid_created` (`uid`, `created_at`);
```

- 新报告（自测 + 第三人）写入 `report_key_hash`；旧报告为 `NULL`。
- `uid` 为 `0` 表示匿名；新代码只从 token 取值。
- 不建外键，避免历史脏数据导致迁移失败。

### 5.4 迁移步骤

> 执行前必须全量备份 `answers` 与 `users`。

1. 检查 `users` 是否存在：
   - 不存在：直接执行 §5.1 DDL。
   - 存在且为空：`RENAME TABLE users TO users_legacy_bak;` 后重建。
   - 存在且有数据：**停止自动迁移**，人工评估旧数据映射（旧表无邮箱/密码，无法自动升级）。
2. 创建 `refresh_tokens`。
3. `answers` 加字段与索引（执行前用 `information_schema.columns` 判断字段是否已存在，保证可重跑）。
4. 将历史匿名 uid 归零：
   ```sql
   UPDATE answers SET uid = 0;
   ```
   旧 `uid` 由客户端自报、并非真实账号，归零可避免与新用户 id 撞号。
5. 配置 `auth.legacy_report_cutoff` 为本次上线时间（RFC3339），作为旧报告免 key 访问的截止点。
6. 部署后端 → 联调前端 → 观察 30 天 → 将 `legacy_report_cutoff` 设为过去时间或移除兼容逻辑。

### 5.5 回滚

- 应用回滚：旧版本不识别新表/新字段，可继续运行；`answers.report_key_hash` 为 `NULL` 不影响旧逻辑。
- 数据回滚：从备份恢复 `answers.uid`。**不要**删除 `users` / `refresh_tokens`，保留无副作用。
- 若新版本已写入 `uid>0` 的答卷，旧版本仍可正常读取，只是不校验归属。

---

## 6. 认证与会话

### 6.1 密码

- 哈希：`bcrypt.GenerateFromPassword(pw, 12)`。
- 校验：`bcrypt.CompareHashAndPassword`。
- 规则：
  - 长度 8~72 **字节**（bcrypt 上限 72 字节）。
  - 不允许与邮箱完全相同。
  - 不强制大小写/符号组合（遵循长度优先）。
- 登录时用户不存在也执行一次 dummy bcrypt 校验，降低邮箱枚举的时间差。
- 密码只在请求生命周期内存在，禁止日志输出。

### 6.2 Access Token（JWT）

- 算法：HS256，显式限定 `jwt.WithValidMethods([]string{"HS256"})`。
- Claims：

```json
{
  "iss": "personality-matrix",
  "sub": "10001",
  "jti": "随机 16 字节 hex",
  "iat": 1760000000,
  "exp": 1760000900
}
```

- TTL：15 分钟（`auth.access_ttl_seconds=900`）。
- 解析后 `sub` 转 `int64` 作为 `uid`；任何解析失败 → `401`。
- Access Token 不查库、不可单独撤销；登出/改密后最长 15 分钟内仍有效，属于可接受窗口。

### 6.3 Refresh Token

- 生成：32 字节随机数 → `base64.RawURLEncoding`（43 字符）。
- 存储：`sha256(token)` 的 hex（64 字符）。
- TTL：30 天（`auth.refresh_ttl_seconds=2592000`）。
- 登录：新建一个 `family_id`，写入一条 refresh token。
- 刷新（轮换）：
  1. 计算 hash，`SELECT ... FOR UPDATE` 查行。
  2. 不存在 / 已过期 → `401`。
  3. 已撤销：
     - 若 `revoked_at` 在 10 秒内 → 视为并发刷新竞争，返回 `401`，**不**撤销 family。
     - 否则判定为重放，撤销该 `family_id` 下全部 token，返回 `401`。
  4. 标记当前 token `revoked_at=now`，插入同 `family_id` 的新 token。
  5. 返回新的 access + refresh。
- 事务：步骤 2~4 在同一个数据库事务中完成。
- 登出：撤销当前 refresh token 所属 family。
- 改密：撤销该用户全部 refresh token，并返回一对新 token 保持当前设备登录。
- 客户端要求：并发请求时**单飞刷新**（single-flight），避免触发重放检测。

### 6.4 中间件与 Context

新增 `RequireAuth` / `OptionalAuth`：

| 中间件 | 无 `Authorization` | 有但非法/过期 |
| -- | -- | -- |
| `RequireAuth` | `401` | `401` |
| `OptionalAuth` | 匿名（`uid=0`） | `401` |

- 从 `Authorization: Bearer <token>` 解析。
- 将 `uid` 放入 `c.Request.Context()`（私有 key 类型），service 通过 `c.Request.Context()` 读取。
- 禁止从 query/body 读取 `uid`。

### 6.5 账号状态

- 登录、刷新时检查 `status=1`；禁用账号返回 `401` 通用错误。
- JWT 中间件不查库，禁用后 Access Token 最多残留 15 分钟。
- `me` / `profile` 查库时再次校验状态。

---

## 7. API 契约

### 7.1 通用约定

- 前缀：`/api/v1/personality/auth`。
- 新增接口统一信封：
  - 成功：`200 {"code":0,"data":...}`
  - 失败：HTTP 4xx/5xx + `{"code":<http>,"message":"..."}`
- `Content-Type: application/json`。
- 请求体上限 1 MB。
- 时间字段 RFC3339。

### 7.2 注册

```
POST /api/v1/personality/auth/register
```

请求：

```json
{
  "email": "alice@example.com",
  "password": "correct horse battery staple",
  "display_name": "Alice",
  "lang": "zh-CN"
}
```

| 字段 | 必填 | 约束 |
| -- | :--: | -- |
| email | ✅ | 合法邮箱，≤254 字符 |
| password | ✅ | 8~72 字节，且不等于邮箱 |
| display_name | ⭕ | ≤50 字符；为空时取邮箱 @ 前部分 |
| lang | ⭕ | 白名单，缺省 `zh-CN` |

成功（自动登录）：

```json
{
  "code": 0,
  "data": {
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
}
```

错误：

| HTTP | message | 场景 |
| :--: | -- | -- |
| 400 | `invalid email` | 邮箱格式错误 |
| 400 | `invalid password` | 长度不合法 / 等于邮箱 |
| 400 | `invalid lang` | 语言不在白名单（也可回退，不报错） |
| 409 | `email already registered` | 唯一键冲突 |
| 429 | `too many requests` | 注册限流 |

### 7.3 登录

```
POST /api/v1/personality/auth/login
```

请求：

```json
{ "email": "alice@example.com", "password": "..." }
```

成功：结构同注册（`user` + 三个 token 字段）。

失败统一：

| HTTP | message |
| :--: | -- |
| 401 | `invalid email or password` |
| 401 | `account disabled`（可选，或统一为上一行） |
| 429 | `too many requests` |

> 不区分“邮箱不存在”和“密码错误”，防止账号枚举。

### 7.4 刷新

```
POST /api/v1/personality/auth/refresh
```

请求：

```json
{ "refresh_token": "3f9k..." }
```

成功：同登录响应的 token 字段（不含 `user`，或附带 `user` 均可；推荐只返回 token）。

| HTTP | message | 场景 |
| :--: | -- | -- |
| 400 | `invalid request body` | 缺少字段 |
| 401 | `invalid refresh token` | 不存在/过期/已撤销/重放 |
| 429 | `too many requests` | 刷新限流 |

### 7.5 登出

```
POST /api/v1/personality/auth/logout
```

请求：

```json
{ "refresh_token": "3f9k..." }
```

- 无论 token 是否有效，均返回 `200 {"code":0,"data":null}`（幂等，避免探测）。
- 缺少字段 → `400`。

### 7.6 当前用户

```
GET /api/v1/personality/auth/me
Authorization: Bearer <access_token>
```

成功：

```json
{
  "code": 0,
  "data": {
    "id": 10001,
    "email": "alice@example.com",
    "display_name": "Alice",
    "lang": "zh-CN",
    "created_at": "2026-10-24T12:00:00+08:00"
  }
}
```

| HTTP | message |
| :--: | -- |
| 401 | `unauthorized` |

### 7.7 修改密码

```
POST /api/v1/personality/auth/change-password
Authorization: Bearer <access_token>
```

请求：

```json
{ "current_password": "...", "new_password": "..." }
```

- 新密码规则同注册，且不得与旧密码相同。
- 成功：撤销该用户全部 refresh token，返回新 token 对。
- 当前密码错误 → `401 invalid current password`。
- 成功后旧密码立即失效；旧 Access Token 最多 15 分钟内仍有效。

### 7.8 修改资料

```
PATCH /api/v1/personality/auth/profile
Authorization: Bearer <access_token>
```

请求（字段均可选，至少一个）：

```json
{ "display_name": "Alice W.", "lang": "en" }
```

成功：返回更新后的 user 对象。

### 7.9 现有接口改造

#### 交卷（自测 / 第三人）

`POST /api/v1/personality/submit-answers`
`POST /api/v1/personality/third-person/submit-answers`

- 接入 `OptionalAuth`。
- 请求体中的 `uid` **忽略**；`uid` 由 token 决定，匿名则为 `0`。
- 响应新增 `report_key`（明文，仅此一次）：

```json
{
  "code": 0,
  "data": {
    "report_id": 100,
    "report_key": "rk_9xQ..."
  }
}
```

- 写库使用事务：`INSERT answers` → 计算结果 → `UPDATE result`，失败整体回滚。
- 匿名交卷保留，但按 IP 限流。

#### 读取报告（自测 / 第三人）

`GET /api/v1/personality/report?report_id=100`
`GET /api/v1/personality/third-person/report?report_id=100`

新增可选请求头：

```
Authorization: Bearer <access_token>   # 可选
X-Report-Key: rk_9xQ...                # 可选
```

保留旧错误信封 `{"error":"..."}`，仅新增状态码：

| HTTP | error | 场景 |
| :--: | -- | -- |
| 400 | `Invalid report_id` | 非法 id（自测接口同步补齐） |
| 401 | `Unauthorized` | 带了非法/过期 token |
| 404 | `Report not found` | 不存在 / 无权访问（不区分，避免探测） |
| 500 | `Failed to get report` | 数据库等内部错误 |

- 不再使用 `fmt.Sprintf` 拼接 SQL。
- 第三人报告仍需校验 `target_role` 非空。

---

## 8. 报告归属模型

### 8.1 访问判定

设 `answer.uid` 为报告归属（0=匿名），`requesterUID` 来自 token（0=匿名），`key` 来自 `X-Report-Key`。

| # | 条件 | 结果 |
| -- | -- | -- |
| 1 | `requesterUID > 0 && requesterUID == answer.uid` | 允许（本人） |
| 2 | `key` 非空且 `sha256(key) == answer.report_key_hash` | 允许（持分享键） |
| 3 | `answer.uid == 0 && answer.created_at < legacy_report_cutoff` | 允许（历史兼容，记 warning 日志） |
| 4 | 其他 | `404 Report not found` |

说明：

- `auth.enforce_report_ownership=false` 时跳过上表校验（仅用于新旧前端混跑的上线过渡期）；前端就绪后必须置为 `true`。
- 登录他人账号但持有效 key → 允许，key 是分享凭证。
- 注册用户的报告默认私有；把 `report_key` 发给他人即可分享。
- 本人访问无需 key；key 丢失不影响本人（注册用户）。
- 匿名报告丢失 key 后无法找回（P1 可做 key 轮换/找回）。

### 8.2 `report_key` 生命周期

- 生成：32 字节随机 → `rk_` + `base64.RawURLEncoding`（总长 46）。
- 存储：`sha256(完整字符串)`，hex 64 位。
- 返回：仅在交卷响应中返回一次。
- 传递：`X-Report-Key` 请求头（**不放 query**，避免被访问日志记录）。
- 比较：`subtle.ConstantTimeCompare`。
- 前端：交卷后必须持久化 `report_key`；分享链接由前端自行携带（建议放在 URL fragment 或分享页参数中，再转为请求头）。
- MVP 不支持轮换/吊销 key；P1 增加 `POST /report/rotate-key`。

### 8.3 历史兼容窗口

- `auth.legacy_report_cutoff` 为 RFC3339 时间。
- 仅对 `uid=0` 且 `created_at < cutoff` 的旧报告放行，避免已发出链接集体失效。
- 建议窗口 30 天；到期后将 cutoff 设为过去时间，旧链接失效。
- 每次命中兼容分支必须打印 `slog.Warn`（含 report_id），便于监控窗口内存量访问。

### 8.4 安全修复

- `GetReport` 改为参数化查询：
  ```go
  gormDB.WithContext(ctx).Raw(
      `SELECT id, uid, result, start_time, end_time, report_key_hash, created_at
       FROM answers WHERE id = ?`, reportID,
  ).Take(&answer)
  ```
- handler 先用 `strconv.ParseInt` 校验 `report_id > 0`，非法直接 400。
- 第三人与自测共用归属判定函数，避免逻辑分叉。

---

## 9. 安全设计

### 9.1 限流

进程内滑动窗口（单实例）。接口抽象为 `RateLimiter`，后续可换 Redis 实现。

| 场景 | Key | 限制 |
| -- | -- | -- |
| 注册 | `register:<ip>` | 3 次/小时，10 次/天 |
| 登录 | `login:<ip>:<email>` | 5 次/分钟 |
| 登录 | `login:<ip>` | 20 次/分钟 |
| 刷新 | `refresh:<ip>` | 30 次/分钟 |
| 交卷（匿名） | `submit:<ip>` | 30 次/分钟 |
| 读报告 | `report:<ip>` | 60 次/分钟 |

- 超限返回 `429` + `Retry-After`。
- IP 取 `c.ClientIP()`；通过 `auth.trusted_proxies` 配置可信代理，默认仅信任 loopback，防止 `X-Forwarded-For` 伪造。

### 9.2 账号枚举与爆破

- 登录失败统一 `invalid email or password`。
- 用户不存在时执行 dummy bcrypt，抹平时间差。
- 不做永久锁定（避免恶意锁号），依赖 IP + 邮箱双维度限流。

### 9.3 日志与敏感信息

- 禁止记录：密码、`Authorization` 头、`X-Report-Key`、refresh token。
- 登录/注册日志记录：`uid`、IP、UA、结果；邮箱只在必要时脱敏（`a***@example.com`）。
- 报告兼容访问：记录 `report_id`，不记录 key。
- GORM logger 开启 `ParameterizedQueries` 与 `IgnoreRecordNotFoundError`，避免把邮箱等参数值写入 SQL 日志。

### 9.4 传输与配置

- 生产必须 HTTPS（反向代理终止 TLS）。
- JWT 密钥 ≥32 字节，来自环境变量 `PERSONALITY_AUTH_JWT_SECRET`，禁止提交仓库。
- 生产环境密钥缺失/过短 → 启动失败（fail-fast）。
- 非生产可回退开发密钥并打印 `slog.Warn`。
- 保持同源部署；当前无 CORS，MVP 不新增 CORS。
- 新增中间件设置 `X-Content-Type-Options: nosniff`，并按需加 `Referrer-Policy`。
- 请求体限制 1 MB。

### 9.5 已知残余风险（MVP 接受）

| 风险 | 说明 | 缓解 / 后续 |
| -- | -- | -- |
| 邮箱未验证 | 可注册他人邮箱 | P1 邮件验证 |
| 无法找回密码 | 忘记密码即无法登录 | P1 重置流程；MVP 提供人工支持 |
| Access Token 不可即时撤销 | 登出/改密后最长 15 分钟有效 | 短 TTL；P1 Redis denylist |
| 前端 token 存储 | localStorage 有 XSS 风险 | 严格 CSP；P1 改 httpOnly cookie |
| 限流为单实例 | 多实例下限额按实例放大 | P1 Redis |
| 历史报告窗口 | 窗口内按 id 可读 | 30 天后关闭并监控 |
| 分享 key 无吊销 | 泄露后无法失效 | P1 key 轮换 |

---

## 10. 配置

`config/test.json` / `config/production.json` 新增（**不放真实密钥**）：

```json
{
  "auth": {
    "jwt_secret": "",
    "access_ttl_seconds": 900,
    "refresh_ttl_seconds": 2592000,
    "bcrypt_cost": 12,
    "legacy_report_cutoff": "",
    "enforce_report_ownership": true,
    "trusted_proxies": []
  }
}
```

- 环境变量覆盖：`PERSONALITY_AUTH_JWT_SECRET`（Viper `SetEnvPrefix("PERSONALITY")` + `AutomaticEnv` + `.`→`_`）。
- 生产 secret 通过 systemd `EnvironmentFile` 或部署平台注入。
- `legacy_report_cutoff` 为空表示不启用历史兼容（旧匿名报告将不可读）。
- `enforce_report_ownership` 默认 `true`；如需新旧前端混跑过渡，可临时置 `false`，联调完成后立即恢复。
- 上线 runbook 必须显式设置 cutoff 与 ownership 开关。

---

## 11. 分层与代码结构

| 文件 | 职责 |
| -- | -- |
| `src/db/user_account.sql` | 建表 + `answers` 变更 + 迁移说明 |
| `src/model/user.go` | `User`、`RefreshToken`、请求/响应模型、状态常量 |
| `src/model/db_user.go` | GORM 映射（替换旧 `DBUser`） |
| `src/util/password.go` | bcrypt 哈希/校验、dummy hash |
| `src/util/jwt.go` | 签发/解析 Access Token，claims 校验 |
| `src/util/ratelimit.go` | `RateLimiter` 接口 + 进程内滑动窗口实现 |
| `src/service/auth.go` | 注册/登录/刷新/登出/改密/资料，事务边界 |
| `src/service/auth_repo.go` | `AuthRepository` 的 GORM 实现 |
| `src/handler/auth.go` | 7 个 auth 接口：绑定、校验、响应 |
| `src/handler/middleware.go` | `RequireAuth`、`OptionalAuth`、`GetUIDFromContext`、请求体限制 |
| `src/handler/routes.go` | 注册路由、挂载中间件 |
| `src/service/personality_matrix.go` | 交卷事务、`report_key`、报告归属、SQL 注入修复 |
| `src/service/third_person.go` | 第三人交卷/报告接入同一套归属逻辑 |
| `src/model/personality.go` | `UID` 标记废弃；交卷响应增加 `report_key` |
| `src/main.go` | 配置加载、auth 初始化、生产密钥校验 |

新增依赖：

- `github.com/golang-jwt/jwt/v4`（v4.5.1；当前离线环境未缓存 v5）
- `golang.org/x/crypto`（由 indirect 提升为 direct）

接口设计（便于无 DB 单测）：

```go
type AuthRepository interface {
    CreateUserWithToken(ctx context.Context, u *model.User, t *model.RefreshToken) error
    GetUserByEmail(ctx context.Context, email string) (*model.User, error)
    GetUserByID(ctx context.Context, uid int64) (*model.User, error)
    UpdateProfile(ctx context.Context, uid int64, displayName, lang *string) error
    TouchLastLogin(ctx context.Context, uid int64) error

    CreateRefreshToken(ctx context.Context, t *model.RefreshToken) error
    GetRefreshTokenByHash(ctx context.Context, hash string) (*model.RefreshToken, error)
    RotateRefreshToken(ctx context.Context, oldID int64, newToken *model.RefreshToken, now time.Time) (bool, error)
    RevokeFamily(ctx context.Context, familyID string, now time.Time) error
    RevokeAllUserTokens(ctx context.Context, uid int64, now time.Time) error
    ChangePasswordAndIssueToken(ctx context.Context, uid int64, passwordHash string, newToken *model.RefreshToken, now time.Time) error
}
```

> 事务封装在 repository 内：注册、轮换、改密各自原子完成；`RotateRefreshToken` 用条件更新（`revoked_at IS NULL AND expires_at > now`）保证并发只成功一次。

---

## 12. 测试与验收

### 12.1 单元测试（不依赖外部 DB）

- `util/password`：哈希/校验、72 字节边界、错误密码。
- `util/jwt`：签发、解析、过期、错误签名、`alg=none`、错误 issuer。
- `service/auth`（fake repository）：
  - 注册：邮箱规范化、重复邮箱、弱密码。
  - 登录：正确/错误/不存在（统一错误）、禁用账号。
  - 刷新：正常轮换、过期、撤销、重放撤销 family、10 秒并发宽限。
  - 改密：旧密码校验、撤销全部 refresh。
- `service/personality`：归属判定四种分支、report_key 常量时间比较。
- handler：参数校验与状态码。

### 12.2 集成测试（独立测试库）

- 完整链路：注册 → me → 交卷 → 读报告 → 刷新 → 登出。
- `uid` 注入测试：请求体传 `uid=999`，落库仍为 token 用户。
- 越权测试：用户 B 读用户 A 的报告 → 404。
- 匿名测试：交卷拿 key → 带头读成功；不带头 → 404（cutoff 之后）。
- 历史兼容：`created_at < cutoff` 的 uid=0 报告不带 key 可读。
- SQL 注入：`report_id=1 OR 1=1` → 400，无数据库错误。
- 限流：连续失败登录触发 429。
- 并发刷新：两个请求同时刷新，不误伤 family（10 秒宽限）。

### 12.3 验收 curl 示例

```bash
HOST=http://localhost:8082

# 注册
curl -s -X POST "$HOST/api/v1/personality/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"password123"}'

# 登录
curl -s -X POST "$HOST/api/v1/personality/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"password123"}'

# 当前用户
curl -s "$HOST/api/v1/personality/auth/me" -H "Authorization: Bearer $ACCESS"

# 带身份交卷
curl -s -X POST "$HOST/api/v1/personality/submit-answers" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS" \
  -d '{"survey_id":1,"uid":999,"opt_selections":[]}'

# 匿名报告带 key 读取
curl -s "$HOST/api/v1/personality/report?report_id=$RID" -H "X-Report-Key: $RKEY"

# 越权读取（应为 404）
curl -s -o /dev/null -w '%{http_code}\n' \
  "$HOST/api/v1/personality/report?report_id=$RID" -H "Authorization: Bearer $OTHER_ACCESS"
```

### 12.4 Definition of Done

- 所有新增接口有单测；关键链路有集成测试。
- `gofmt -s`、`goimports`、`go vet`、`go test ./...` 通过。
- 迁移脚本在数据库副本演练通过，含回滚。
- 前端完成 token 存取、刷新单飞、`report_key` 持久化与分享传参。
- `design.md` / `requirement.md` / `AGENTS.md` 同步：
  - 移除“SQL 注入未修复”红线；
  - 用户系统标记为 MVP 已实现（上线后）；
  - 补充 auth 接口与表结构。
- 生产 JWT 密钥通过环境变量注入，仓库无密钥。
- 监控：登录失败率、429 数量、401 数量、历史兼容访问量。

---

## 13. 实施计划

按 1 名后端 + 1 名前端估算。

| 阶段 | 内容 | 后端人日 |
| -- | -- | :--: |
| P0 | DDL、模型、配置、repo 接口与 GORM 实现 | 1.5 |
| P1 | password / jwt / refresh token 工具与单测 | 1.5 |
| P2 | auth service + 7 个接口 + 中间件 | 2.0 |
| P3 | 现有交卷/报告接口接入、report_key、归属校验、SQL 注入修复 | 1.5 |
| P4 | 限流、日志脱敏、请求体限制、启动密钥校验 | 1.0 |
| P5 | 单元/集成测试、验收脚本 | 1.5 |
| P6 | 迁移演练、前端联调、上线与观察 | 1.0 |
| **合计** | | **10** |

前端：4~6 人日（登录/注册页、token 管理、刷新单飞、报告 key 持久化与分享、错误处理）。

日历周期：

- 顺利：**2 周**（前后端并行）。
- 含联调与迁移演练：**2.5~3 周**。

上线顺序：

1. 数据库迁移（低峰期，先备份）。
2. 后端发布（若旧前端仍在跑，先将 `auth.enforce_report_ownership` 置 `false`，避免旧前端读不出报告）。
3. 前端发布（保存 `report_key`、带 token/key 读报告）。
4. 将 `auth.enforce_report_ownership` 恢复为 `true`。
5. 观察 30 天后关闭历史兼容窗口。

> `auth.enforce_report_ownership` 默认 `true`，只在必要的短窗口内临时关闭。

---

## 14. 后续（P1+）

1. 邮箱验证 + 找回密码（需邮件服务与 6 语言模板）。
2. 第三方登录（Google / Apple / 微信）。
3. 手机号 + 短信验证码。
4. 账号注销、数据导出、隐私合规。
5. 我的报告列表、报告删除、跨设备会话管理。
6. `report_key` 轮换/吊销、注册用户分享管理。
7. Redis 分布式限流、Access Token 黑名单、JWT 密钥轮换。
8. 管理后台与 RBAC。

---

## 15. 产品/运维需确认

1. 历史报告兼容窗口是否接受 30 天后旧分享链接失效（推荐接受）。
2. 注册用户分享报告是否接受“分享 `report_key`”这一能力（MVP 无独立分享页）。
3. 匿名交卷是否长期保留（本设计保留）。
4. 上线窗口与数据库备份责任人。
