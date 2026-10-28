# 安全策略

## 支持版本

安全修复会应用到默认分支上的最新版本。

## 报告漏洞

请勿为安全问题创建公开 Issue。请通过 GitHub 的
[安全公告](https://github.com/shaanlan/PersonaAgent/security/advisories/new)
流程私下报告。

报告中请尽量包含：

- 受影响的端点或组件；
- 复现步骤；
- 影响范围（例如鉴权绕过、数据泄露、Prompt 注入）；
- 建议的修复方式（如有）。

我们会在几个工作日内确认收到。在修复发布前，请不要公开披露该问题。

## 运维注意事项

- 不要提交 `.env` 或真实密钥（`AUTH_JWT_SECRET`、`INTERNAL_SERVICE_TOKEN`、
  `LLM_API_KEY`、`EMBEDDING_API_KEY`、数据库密码）。`.env.example` 只包含占位
  值。
- 生产环境设置 `DB_AUTO_CREATE=false`，并在应用外执行迁移。
- 内部服务令牌仅限内网使用，绝不能暴露给浏览器。
- 限流是进程内状态；如需水平扩容，请先改为共享存储方案。
