
# Content Engine 技术设计文档
## MBTI 性格评测内容自动化生成流水线 · 架构与实现设计

| 文档信息 | 内容 |
|---------|------|
| 产品名称 | MBTI Content Engine（MCE） |
| 版本 | v1.1 |
| 创建日期 | 2026-10-23（自 requirement.md v1.1 拆分而来） |
| 文档类型 | 技术设计文档（Design） |
| 关联文档 | `requirement.md`（PRD，做什么）；本文档回答怎么做 |

> **职责边界**：`requirement.md` 描述产品需求（做什么、产出什么、验收标准）；本文档描述技术设计（架构、Agent 工作流、CLI、配置、数据流）。垂直流水线的**命令级操作细节**以 `ref/` 下各 runbook 为单一事实源，本文档只保留概览与链接。

---

## 1. 系统架构

```
┌──────────────┐      ┌───────────────────┐      ┌──────────────┐
│  Input File  │────▶│  mce import       │────▶│    MySQL     │
│ (keywords)   │      │   写入任务/关键词/   │      │ (状态/元数据)  │
└──────────────┘      │   文章记录          │      └──────┬───────┘
                      └───────────────────┘               │
                             ┌────────────────────────────┘
                             ▼
                      ┌───────────────────┐
                      │  mce run          │
                      │   流水线执行 + 中间快照 │
                      │   --phase --article│
                      └──────────┬────────┘
                                 │
                      ┌──────────┴──────────┐
                      ▼                     ▼
             ┌──────────────┐      ┌───────────────┐
             │  LLM Services│      │  Local/OSS    │
             │ (OpenAI/     │      │  File Storage │
             │  Claude/     │      │               │
             │  Kimi/       │      │               │
             │  DeepSeek)   │      │               │
             └──────────────┘      └───────────────┘

    离线部署扩展流程：
    ┌───────────────────┐      ┌───────────────────┐
    │  mce export       │────▶│  article_seed.json │────▶ SCP 到生产环境
    │  从 done 文章导出   │      │  (便携元数据)       │
    │  元数据为 JSON     │      └───────────────────┘
    └───────────────────┘
                                     ┌───────────────────────┐
                                     │  mce import-seed      │
                                     │  在空库上导入种子数据    │
                                     │  设置 status=done     │
                                     └───────────────────────┘
```

### 1.1 组件说明

- **mce import**：读取本地关键词文件，写入 MySQL（创建 Task、Keyword 和 Article 记录）。
- **mce run**：从 MySQL 读取待处理文章，顺序执行 Agent Pipeline，每步更新状态到 MySQL，同时将每阶段的输入输出保存为 JSON 快照到 `data/intermediate/{article_id}/`。支持 `--phase` 参数从指定阶段启动（从快照加载之前阶段的输出），以及 `--article` 参数指定单篇文章调试。
- **Agent Workers**：顺序调用 LLM API 执行具体生成步骤。
- **MySQL**：存储任务、关键词、文章元数据（状态、OSS 路径、SEO 信息、评分等）。
- **LLM Services**：支持 OpenAI GPT-4o、Claude、Kimi、DeepSeek、智谱，以及 Ollama / LM Studio 本地 OpenAI 兼容端点，统一接口，可配置 fallback 和模型切换。
- **File Storage**：本地文件系统（默认），可选阿里云 OSS。
- **其他内容流水线 CLI**（与 `mce` 共用 llm / prompt / config / storage 等 internal 包，但不走文章流水线）：
  - `cmd/career`：职业探索数据流水线（§4.5）
  - `cmd/relationship`：关系探索内容流水线（§4.6）
  - `cmd/thirdperson`：第三人测试题库流水线（§4.7）
  - `cmd/knowledge`：知识库 CLI（手册切块 + SQLite FTS5 索引，`ingest` / `index` / `search`）
  - `cmd/gen-image`：图片批量生成工具（§4.4）
  - `cmd/gen-prompt`：图片生成提示词批处理工具

---

## 2. Agent 工作流

工作流采用**线性顺序执行**，共 10 个核心 Agent（Image Matcher 作为第 11 个，默认不接入）：

```mermaid
graph LR
    A[Topic Planner] --> B[Outliner]
    B --> C[Writer]
    C --> D[Rewriter]
    D --> E[Humanizer]
    E --> F[Visual Builder]
    F --> G[SEO Meta Generator]
    G --> H[Final Assembler]
    H --> I[Translator]
```

### 2.1 Topic Planner Agent
- **输入**：关键词（如 "INTJ careers"），可选传入预定的 `article_type`
- **职责**：
  - 分析搜索意图（信息型/商业型/导航型）
  - 在 `article_type_source: db` 模式下，文章类型由 CSV 或 CLI 参数预先指定，LLM 直接基于该类型规划内容策略（标题、角度、受众等）
  - 在 `article_type_source: topic_planner` 模式下，LLM 自行判断最佳文章类型（指南/列表/对比/分析/故事/人格剧场等）
  - 确定目标受众（MBTI 初学者/进阶者）
  - 生成文章核心角度和 3-4 个备选标题
- **文章类型来源**：通过配置 `pipeline.article_type_source` 控制，支持两种模式：
  - `db`（冷启动默认）：文章类型由 CSV 第二列或 `--article-type` CLI 参数指定，Topic Planner LLM 按固定类型规划内容策略
  - `topic_planner`（多类型模式）：Topic Planner LLM 根据关键词自主判断文章类型
- **LLM 调用参数**：
  - model: 可配置（默认跟随全局 `llm.default_model`）
  - temperature: 0.3
  - response_format: `json_object`
- **输出结构**：
```json
{
  "keyword": "INTJ careers",
  "search_intent": "informational",
  "article_type": "listicle",
  "target_audience": "INTJ personality type individuals seeking career guidance",
  "title_variants": ["Top 10 Careers for INTJ Personalities in 2026", ...],
  "angle": "Exploring the best career paths that align with INTJ strengths in analysis and strategy"
}
```

### 2.2 Outliner Agent
- **输入**：Topic Planner 输出 + 关键词
- **职责**：
  - 生成文章大纲（H2/H3 标题）
  - 每个章节包含 1-2 句核心要点
  - 确保逻辑递进，避免 AI 重复模式
- **约束**：最少 5 个 H2 章节，每个 H2 下 2-3 个 H3
- **输出**：JSON 格式大纲

### 2.3 Writer Agent

- **输入**：大纲 + 关键词 + 风格指南
- **职责**：
  - 根据大纲生成 Markdown 格式文章
  - **personality_drama类型文章内部结构固定为：**
    1. **5% Hook**：引发兴趣、快速吸引用户注意
    2. **10% 人格设定**：介绍主要角色 MBTI 类型、认知功能、性格特点
    3. **70% 故事**：人格关系剧场，围绕角色 MBTI 特质展开互动故事
    4. **10% 心理解析**：结合 MBTI 理论解析故事角色行为、动机和冲突
    5. **5% FAQ**：回答用户常见问题，提供现实建议
  * 初始生成允许有一定"AI痕迹"，Humanizer 后续处理
* **输出示例结构**：

```markdown
## Hook
一句引起兴趣的开场

## 人格设定
- 角色：ENFP
- 核心功能：Ne, Fi
- 简短性格描述

- 角色：INTJ
- 核心功能：Ni, Te
- 简短性格描述

## 故事
第一幕：图书馆相遇……
第二幕：小组项目……
第三幕：阳光融冰……
第四幕：共同的星空……

## 心理解析
- ENFP为何被INTJ吸引
- INTJ为何欣赏ENFP
- 主要冲突和解决方式

## FAQ
- ENFP和INTJ适合恋爱吗？
- 谁更可能主动表白？
- 现实相处建议
```

### 2.4 Rewriter Agent（E-E-A-T 内容增强）

- **输入**：Writer 生成的原始文章
- **职责**：
  - 增加实体信息（具体人名、地名、品牌名、场景、时间）
  - 注入"坏细节"：不体面、尴尬、奇怪、低级失误等真实人类场景
  - 增加经验信息：个人经历、亲身感受、实战经验
  - 注入有偏见、有情绪、有强烈观点的表达，打破 AI 四平八稳的语气
  - 引入不完整感和口语化表达（如"说实话……"、"反正我是……"）
- **与 Humanizer 的职责区分**：
  - Rewriter：专注于**内容深度**，解决 "Scaled Content / Thin Originality / Template-heavy" 等 SEO 质量问题
  - Humanizer：专注于**统计特征**，解决困惑度、burstiness、AI 短语替换等反检测问题
- **LLM 调用参数**：
  - model: 可配置（默认跟随全局配置）
  - temperature: 0.8（较高的随机性有利于产生多样化表达）
  - response_format: text
- **输出**：增强后的 Markdown 文章

### 2.5 Humanizer Agent（核心防 AI 检测）
- **输入**：Writer 生成的原始文章
- **职责**：
  - 引入人类写作特征：句式长度波动、少量语法不完美、口语化表达
  - 注入"个人经历"片段（如 "When I first discovered I was an INTJ…"）
  - 使用困惑度（Perplexity）检测并优化：调用内部评估模型，确保文本困惑度接近人类写作范围（50-150）
  - 替换掉 20% 的常见 AI 短语（如 "delve into", "in conclusion"）
  - **Markdown 结构保护**：随机注入错误时自动识别并跳过 Markdown 语法标记（标题 `#`、列表 `- / 1.`、引用 `>`、代码块等），确保拼写错误仅作用于正文内容，不破坏文档结构
- **技术实现**：
  - 先调用 LLM 进行"逆向人性化"改写，提示词要求模拟母语者写作风格
  - 然后通过外部评估器计算 PPL（使用 GPT-2 或 LLaMA 小模型），若超出阈值，则增加随机性重新生成
  - 整个 Agent 支持循环，最多 3 次迭代
- **输出**：人性化后的 Markdown

### 2.6 Visual Builder Agent
- **输入**：Humanizer 输出（完整 Markdown 文章）+ 关键词
- **职责**：
  - 分析文章中所有场景，评估每个场景的画面张力、点击吸引力和封面适配性
  - 选择最适合作为封面图片的场景
  - 生成结构化的 LLM 图片生成提示词，包含两部分：
    1. **故事场景描述**：详细刻画人物（MBTI类型、外貌、表情、动作）、环境（时间、地点、光线、色调）、情感张力
    2. **通用描述**：画质词、风格词、构图词、色调光影 + Negative Prompt
- **输出结构**：
  ```json
  {
    "scene_title": "深夜的情感对峙",
    "scene_prompt": {
      "story_scene": "INFJ女性与ENTP男性情侣，经历激烈争执后的情感对峙时刻...",
      "general_description": "杰作，最佳画质，半写实动漫插画，电影级布光..."
    }
  }
  ```
- **LLM 调用参数**：
  - model: 可配置（默认跟随全局配置）
  - temperature: 0.7
  - response_format: `json_object`
- **与后续阶段的衔接**：生成的提示词通过快照持久化，Image Matcher 从中读取场景描述作为封面图 alt 文本；预留 VisualPrompt 字段，后续可对接 DALL-E 等图片生成 API

### 2.7 SEO Meta Generator
- **输入**：完整文章（含关键词、文章类型、封面图）
- **职责**：
  - 生成 SEO Title（55-60 字符）、Meta Description（150-160 字符）、URL Slug
  - 生成结构化数据（JSON-LD），**不直接使用 LLM 原始输出**，后续由 Service 层统一规范化
  - 检查关键词密度（1-2%），输出建议
- **输出**：JSON（title, meta_description, slug, jsonld, keyword_density, word_count）
- **LLM 失败处理**：LLM 调用失败或返回格式解析失败时自动降级为规则化 fallback（基于关键词生成 title/description/slug，硬编码 JSON-LD）
- **Slug 二次验证**：LLM 返回的 slug 需经清理（全小写、空格→连字符、去除非 `[a-z0-9-]` 字符），空 slug 时 fallback 到 `util.Slugify(keyword)`

#### JSON-LD 结构化数据规范

SEO Meta Agent 生成的 JSON-LD 需在 Service 层经过 `fixSEOMetaJSONLD()` 规范化处理，包含以下增强：

1. **@graph 包裹结构**：所有实体放入 `@graph` 数组（而非单个 `@type`），便于扩展多个实体类型
2. **URL 规范化**：`url` 使用 `site_url + /{lang}/{article_type}/{slug}` 绝对路径
3. **图片绝对路径**：`image` 字段若非 `http` 开头则拼接 `site_url` 前缀
4. **作者本地化**：根据文章语言自动选择本地化作者名——当前支持 6 种语言映射（zh-CN "MBTI关系研究员"、en "MBTI Relationship Researcher"、ja "MBTI関係研究者"、ko "MBTI 관계 연구원"、es "Investigador de Relaciones MBTI"、pt-BR "Pesquisador de Relacionamentos MBTI"）
5. **FAQPage 增强**：当文章类型为 `personality_drama` 时，自动从 `## FAQ` 章节提取 Q&A 对（格式支持 `**Q：**` / `**Q:**`），生成 `FAQPage` 实体追加到 `@graph` 数组中

示例输出结构：
```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Article",
      "headline": "Top 10 Careers for INTJ Personalities in 2026",
      "description": "Discover the best career paths...",
      "keywords": "INTJ careers",
      "url": "https://www.example.com/en/listicle/intj-careers",
      "image": "https://cdn.example.com/intj-careers-cover.jpg",
      "datePublished": "2026-06-09",
      "dateModified": "2026-06-09",
      "author": {
        "@type": "Person",
        "name": "MBTI Relationship Researcher"
      }
    },
    {
      "@type": "FAQPage",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "Are INTJ and ENFP compatible?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "Yes, they often form an idealist-realist dynamic..."
          }
        }
      ]
    }
  ]
}
```

### 2.8 Final Assembler
- **输入**：Humanizer/Markdown 输出 + SEO 元数据 + Visual Builder 封面图
- **职责**：
  - 组合为最终交付物：在 Markdown 头部插入 YAML Front Matter（title, description, slug, date, lang, category, cover, tags）
  - **自动标签生成**：`buildTags()` 从关键词中提取有意义单词（正则 `[\p{L}\p{N}_]+` 匹配 Unicode 字母/数字），过滤长度 < 2 或纯数字/纯符号的 token，始终包含 "MBTI" 和文章类型（如 "Listicle"）
  - **H1 标题剥离**：因 Front Matter 已有 `title` 字段，自动剥离正文首行的 `# H1 标题`，避免与前端渲染的页面标题重复（SEO 优化）
  - 注入广告占位符 `<!-- AD_SLOT_1 -->` 至第 2、5 段后（可通过 task config 自定义位置）
  - **内部链接（相关内容）**：自动从 MySQL 查询同类文章（`WHERE article_type = ? AND lang = ? AND status = 'done'`），取最新 3 篇生成 "### 相关内容" 模块，含标题、URL 路径（`/{lang}/{article_type}/{slug}`）、描述
  - 底部追加 JSON-LD 结构化数据（`<script type="application/ld+json">`）
  - 保存至本地目录（或 OSS），路径规则：`{lang}/{article_type}/{slug}.md`
- **输出**：最终 Markdown 文件内容

> **标签生成示例**：关键词 "INTJ careers for entrepreneurs" → tags: `["Careers", "Entrepreneurs", "INTJ", "Listicle", "MBTI"]`（过滤介词 "for" 等短词）

### 2.9 Translator Agent（多语言翻译）

- **输入**：Assembler 输出的完整 Markdown（含 Front Matter）+ SEO 元数据 + 源语言 + 目标语言
- **职责**：
  - 将文章内容从源语言（zh-CN）翻译成目标语言（en / ja / ko / es / pt-BR）
  - 生成本地化的 SEO 元数据：标题、描述、URL Slug
  - 保留所有 Markdown 结构、广告占位符、图片标签
  - 自然翻译而非字面直译，适配目标语言的文化背景和表达习惯
- **调用方式**：每个目标语言一次 LLM 调用，response_format = `json_object`
- **截断恢复**：LLM 输出因 token 限制被截断时（`finish_reason="length"`），自动尝试 `recoverTruncatedJSON()` 修复不完整 JSON（去尾逗号、平衡花括号、补全未闭合字符串），恢复失败则标记为错误
- **LLM 调用参数**：
  - model: 可配置（默认跟随全局配置）
  - temperature: 0.7
  - response_format: `json_object`
  - max_tokens: 65536（给足够空间的较大值）
- **输出结构**：
  ```json
  {
    "lang": "en",
    "title": "Top 10 Careers for INTJ Personalities in 2026",
    "meta_description": "Discover the best career paths for INTJ types...",
    "slug": "intj-careers",
    "markdown": "If you're an INTJ like me..."
  }
  ```
- **图片复用**：直接复用 Visual Builder 生成的 `featured_image`，无需重新生成
- **Slug 策略**：翻译文章的 slug 统一复用源文（zh-CN）的 slug，不同语言通过路径前缀 `/{lang}/` 区分。import 时创建翻译记录使用 `{baseSlug}-{targetLang}` 临时 slug 保证唯一性，翻译完成后覆盖为源文 slug
- **存储**：上传至 `{target_lang}/{article_type}/{slug}.md`
- **调用位置**：在 Assembler 之后、Upload 之前执行，作为流水线第 10 阶段

### 2.10 Image Matcher Agent（默认不接入）

- 由于外部图片 API（Unsplash/Pexels）需要额外的 Key 配置且并非内容生产必需，默认**不启用**真实图片匹配。
- 预留占位符格式 `{{IMG: description}}` 保持不变，输出时替换为本地路径 `/images/{article_type}/{slug}-{n}.jpg`。
- Featured Image 在 Front Matter 中留空或写入占位路径。
- 若配置了 `image.unsplash_access_key` 或 `image.pexels_api_key`，则自动启用真实图片搜索和上传至 OSS。
- 图片匹配失败不会中断流水线（非致命错误），直接使用占位路径继续。

---

## 3. 执行流程与 Slug 规则

### 3.1 执行流程

```
1. mce import --input keywords.txt：读取本地文件 → 写入 MySQL（创建 Task + Keywords + Articles，status=queued）
2. mce import --input keywords.txt --target-langs "en,ja,ko,es,pt-BR"：导入时为目标语言创建翻译文章记录
   每个关键词创建 6 条记录（1 条 zh-CN 原始 + 5 条翻译），status=pending_translation
   Task.total_items = keywords × (1 + 目标语言数)
3. mce run：从 MySQL 读取 status=queued 的文章 → 顺序执行 Pipeline Agent → 每步更新 MySQL 状态并保存 JSON 快照
   - zh-CN 文章走完完整流水线（Topic Planner → ... → Assembler）
   - Translator 阶段自动将文章翻译到目标语言并上传
4. mce run --task 1 --skip-translation：跳过翻译阶段，中文文章完成后状态为 done，翻译副本保持 pending_translation，待人工编辑润色后再执行翻译
5. mce run --article 42 --phase writer：从 writer 阶段开始处理指定文章（从快照加载 topic_planner 和 outliner 输出）
6. mce run --article 42 --phase translator：跳过前面的阶段，只执行翻译（与 --skip-translation 配合使用，先跳过翻译，编辑后再单独翻译）
7. 最终输出 Markdown 文件（本地或 OSS），路径规则：{lang}/{article_type}/{slug}.md
8. `mce export --output data/export/article_seed.json`：从本地 DB 导出所有 `status=done` 的文章元数据为可移植 JSON 文件，用于给空库的生产环境做种子数据，使生产 pipeline 能生成相关文章。支持 `--lang` 和 `--article-type` 过滤。
9. `mce import-seed --input data/export/article_seed.json`：将 export 导出的 seed JSON 导入生产 DB，每条记录设为 `status=done`。幂等操作（按 slug+lang 去重），重复执行安全。
```

### 3.2 Slug 生成规则

Slug 在多个阶段生成和验证，确保 URL 友好和唯一性：

1. **import 阶段**：关键词通过共享工具 `util.Slugify()` 生成基础 slug：全小写 → 非 `[a-z0-9-]` 字符替换为 `-` → 连续 `-` 合并 → 最多保留 6 个 segment → 尾部去 `-`
2. **import slug 去重**：若 slug 在 `(slug, lang)` 组合上已存在，则追加计数后缀 `-2`、`-3`...
3. **SEO Meta 验证**：LLM 返回的 slug 经过二次清理（去空格、空格→连字符、祛除非字母数字、去首尾连字符）；空 slug 时 fallback 到 `util.Slugify(keyword)`
4. **翻译文章**：import 时创建 `{baseSlug}-{targetLang}` 作为临时 slug；翻译完成后由 service 统一覆盖为源文 slug，不同语言通过 URL 路径前缀 `/{lang}/` 区分
5. **数据库约束**：`articles` 表通过 `(slug, lang)` 复合唯一索引 `idx_slug_lang` 保证同一语言内 slug 唯一

### 3.3 数据库状态与多语言分组

`articles.status` 枚举：`queued → planning → outlining → writing → rewriting → humanizing → visual_building → imaging → seo → assembling → translating → uploading → done/failed`，翻译文章初始状态为 `pending_translation`，翻译中为 `translating`

> **状态说明**：zh-CN 原始文章走完整流水线（queued → ... → done）；翻译文章以 `pending_translation` 状态创建，由 translator 阶段统一处理为 `translating → done/failed`

#### GroupID 多语言分组机制

- `group_id` 在 import 时设置：源文（zh-CN）的 `group_id = article.id`，翻译文章的 `group_id` 指向源文 ID
- 当源文经过 Assembler 完成后，`handleTranslations()` 通过 `group_id` 查询所有 `status=pending_translation` 的翻译文章，逐条翻译
- `pending_translation` 文章在 `ProcessArticle()` 中被直接跳过（`return nil`），避免独立执行流水线
- 翻译完成后沿用源文 slug、复用 `featured_image`，内容上传至 `{target_lang}/{article_type}/{slug}.md`

#### 数据库索引

- `(slug, lang)` 复合唯一索引 `idx_slug_lang`：保证同一语言内 slug 唯一，跨语言允许重复 slug

---

## 4. 技术架构

### 4.1 整体架构

- **语言**：Golang 1.22+
- **运行方式**：CLI 命令行工具（`go run cmd/mce/main.go --input keywords.txt`）
- **配置管理**：Viper，支持环境变量和 `config.yaml`
- **ORM**：GORM v2 + MySQL 8.0（存储任务、关键词、文章元数据、状态）
- **LLM 客户端**：自定义封装，支持 OpenAI / Anthropic / Kimi / DeepSeek API，统一接口
- **文件存储**：本地文件系统（默认），可选阿里云 OSS
- **无 Redis、无 Web 框架、无任务队列**

### 4.2 目录结构

```
mce/
├── cmd/
│   ├── mce/            # 文章流水线 CLI（main.go + run_import.go + run_task.go + export.go + import_seed.go）
│   ├── career/         # 职业探索流水线 CLI（import / score / generate / inject / translate / seed*）
│   ├── relationship/   # 关系探索内容流水线 CLI（catalog / metadata / concepts / profile / page / evidence / mbti / digest / translate / run）
│   ├── thirdperson/    # 第三人测试题库 CLI（gen / translate / validate / sql / run）
│   ├── pairanalysis/   # 双人关系分析内容 CLI（modules / select / assemble / qc / run / translate / batch / export / import-seed）
│   ├── knowledge/      # 知识库 CLI（ingest / index / search，SQLite FTS5）
│   ├── gen-image/      # 图片批量生成工具（main.go）
│   └── gen-prompt/     # 图片生成提示词批处理工具（main.go）
├── internal/
│   ├── config/       # 配置
│   ├── model/        # GORM 模型（文章 + career + relationship）
│   ├── agent/        # Agent 接口与实现（含 topics/outliner/writer/rewriter/humanizer/visual_builder/seo_meta/assembler/translator）
│   ├── career/       # 职业流水线：seed / import / score / generate / inject / glossary / translate / frontmatter
│   ├── relationship/ # 关系流水线：catalog / steps / evidence / mbti / frontmatter / translate
│   ├── thirdperson/  # 第三人测试题库：roles / generate / translate / validate / sql
│   ├── pairanalysis/ # 双人关系分析：modules / select / assemble / qc / translate / citation / seed
│   ├── knowledge/    # 知识库：切块 + 打标 + SQLite FTS5 检索
│   ├── service/      # 业务编排（顺序执行 + 中间结果快照）
│   ├── llm/          # LLM 客户端封装
│   ├── prompt/       # Prompt 模板管理：PromptManager 从 YAML 文件加载提示词，支持 Go template 渲染和版本切换
│   │   ├── loader.go  # PromptManager 加载与渲染逻辑
│   │   ├── zh-CN/     # 中文 prompt 集（mce 各 Agent + career_* / relationship_* / third_person_* / pairanalysis_*）
│   │   └── en/        # 英文 prompt 集（translator 类与 pairanalysis 等）
│   ├── imggen/       # 图片生成客户端（types.go + client.go）
│   ├── storage/      # 文件存储操作（本地 / OSS）
│   └── util/         # 工具（PPL 计算等）
├── configs/
│   └── config.yaml
├── scripts/          # 辅助脚本（career / relationship / pairanalysis 运行、翻译与同步前端）
├── data/
│   ├── banned_phrases.txt
│   ├── career/       # 职业内容页产物（{lang}/{slug}.md，被 .gitignore 忽略）
│   ├── career_glossary/ # 职业翻译术语表（{lang}.json）
│   ├── relationship/ # 关系探索产物（catalog.json / {lang}/pages/ / handbook/digests/）
│   ├── third_person/ # 第三人题库（tp_{role}[.{lang}].json / tp_third_person.sql）
│   ├── pairanalysis/ # 双人关系分析产物（modules / scenes.yaml / 批量输入输出）
│   ├── knowledge/    # 知识库（kb.sqlite）
│   ├── intermediate/ # 各 Agent 阶段中间结果快照
│   └── output/       # 最终 Markdown 输出（默认目录）
├── ref/              # 设计文档与语料（career / relationship / third_person 等）
├── Dockerfile
├── go.mod
└── go.sum
```

### 4.3 关键接口定义

```go
// agent/interface.go
type Agent interface {
    Name() string
    Process(ctx context.Context, input interface{}) (interface{}, error)
}

// llm/client.go
type LLMClient interface {
    ChatCompletion(ctx context.Context, messages []Message, options ...CallOption) (*ChatResponse, error)
}
```

### 4.4 gen-image: 图片批量生成工具

gen-image 是一个独立的 CLI 工具，用于调用 LLM 图片生成 API（OpenAI 兼容接口）批量生成图片。与主流水线解耦，不依赖 MySQL 或其他内部包。

#### 4.4.1 功能概述

- 读取文本输入文件，按行解析图片生成请求
- 支持多个国内服务商：**硅基流动**（SiliconFlow）、**火山方舟**（Ark）、**智谱**（Zhipu），以及 OpenAI DALL-E 3
- 顺序生成，每张图片独立调用 API
- 支持 URL 下载（siliconflow / openai）和 base64 解码（火山方舟）两种响应格式

#### 4.4.2 输入格式

输入文件为 TAB 分隔的文本文件，首行作为公用提示词拼接到每个请求前面：

```
半写实动漫插画风格，电影级布光…（公用提示词）
intj_m.png\t深夜，一栋现代极简风格的高层公寓书房…（具体提示词）
intj_f.png\t黄昏时分，一座顶层私人会所的露台上…（具体提示词）
```

完整 prompt = `公用提示词\n\n具体提示词`

输出路径：`{output_dir}/{filename}`

#### 4.4.3 命令行用法

```
gen-image [flags]

  --input string      输入文件路径（默认 data/card_images/input）
  --output string     输出目录（默认 data/card_images/output）
  --provider string   服务商（siliconflow / ark / openai / zhipu / custom）
  --base-url string   API 地址
  --api-key string    API 密钥
  --model string      模型名
  --size string       图片尺寸（默认 1024x1024）
```

配置优先级：CLI flag > config.yaml > 默认值

#### 4.4.4 支持的服务商

| 服务商 | provider 值 | base_url | 模型示例 |
|-------|------------|---------|---------|
| 硅基流动 | `siliconflow` | `https://api.siliconflow.cn/v1` | `black-forest-labs/FLUX.1-dev` |
| 火山方舟 | `ark` | `https://ark.cn-beijing.volces.com/api/v3` | `ep-xxxxxxxxxxxx`（推理接入点 ID） |
| OpenAI | `openai` | `https://api.openai.com/v1` | `dall-e-3` |
| 智谱 | `zhipu` | `https://open.bigmodel.cn/api/paas/v4` | `cogview-3` |

#### 4.4.5 架构设计

```
cmd/gen-image/
  main.go              CLI 入口（flag 解析 + 配置加载 + 主流程）

internal/imggen/
  types.go             Config 结构体、Provider 常量、API 请求/响应类型
  client.go            Client 结构体 + Generate() 方法
```

**Client.Generate() 流程：**

1. 根据 Provider 构造请求体（ark 追加 `response_format: b64_json`，openai 追加 `quality: standard`）
2. POST `{base_url}/images/generations`，Bearer Token 认证
3. 解析响应：优先取 `b64_json` base64 解码，其次取 `url` HTTP GET 下载
4. 返回图片 bytes

**配置加载：** 复用项目已有的 Viper 配置，在 `config.yaml` 的 `image:` 节新增 `gen_provider` / `gen_base_url` / `gen_api_key` / `gen_model` / `gen_size` 字段，支持 `IMG_GEN_KEY` 环境变量覆盖。

### 4.5 career: 职业探索内容流水线（概览）

career 从 O*NET 职业数据库出发，产出职业探索页（16 型匹配分数、人格适配解读、FAQ），不走文章流水线的 MySQL 状态机，输入是人工维护的 seed 文件。

**流水线**：`seed 校准（可选）→ import（onet_db + seed → career_db）→ score（16 型打分）→ generate（en 内容页）→ inject（match_scores 注入所有语言）→ translate（术语表驱动多语言）`

**关键设计**：
- 数据源双库：`onet_db`（只读）+ `career_db`（写入，含 `career` / `career_category` / `career_skill` / `career_ability` / `career_knowledge` / `career_mbti_score` 六表）
- frontmatter 由结构化数据确定性拼装，LLM 只生成内容性字段（subtitle / top_types / personality_sections / faq 等）
- 各阶段幂等，支持 `--dry-run` / `--force` / `--slug` 过滤

> **命令级操作细节**（完整命令链、flag 说明、seed 格式）见 [`ref/career/career_pipeline_runbook.md`](ref/career/career_pipeline_runbook.md)；产品设计见 `ref/career/career_explorer_design.md`。

### 4.6 relationship: 关系探索内容流水线（概览）

relationship 为 32 类真实关系生成结构化详情页（定义 / 概念映射 / 关系画像 / 证据引用 / MBTI 分型推断）。

**流水线（7 层）**：`catalog → metadata → concepts → profile → evidence（确定性，来自 handbook digest）→ mbti → page`，另有 `digest`（手册章翻译）与 `translate`（en 源 → 目标语言 7 层一键）。

**关键设计**：
- Front Matter 完全由结构化产物确定性拼装，不由 LLM 直接输出（保证前端契约稳定）
- evidence 从手册章 digest 按 `source_chapters` 确定性选取，翻译时 claim-id 与源语言逐条一致
- 概念映射翻译只翻 `relationship_relevance`，`concept_id` / `importance` 保留源值
- 每层 skip-if-exists，可断点续跑

> **命令级操作细节**见 [`ref/relationship/3-relationship_content_pipeline.md`](ref/relationship/3-relationship_content_pipeline.md)；关系目录见 `ref/relationship/0-relationship_catalog.md`。

### 4.7 thirdperson: 第三人测试题库流水线（概览）

第三人测试（他评版）题库生产：ContentEngine 只负责**题目内容**（生成 / 翻译 / 质检 / SQL），取题、计分、答卷存储由后端项目（PersonalityMatrix）复用自测链路消费。

**流水线**：`gen（中文源，每角色 10 题）→ translate（5 种目标语言）→ validate（内容规范质检）→ sql（四表 INSERT）`

**关键设计**：
- v1 固定 4 角色：partner（恋人，survey_id=30）/ friend（朋友，31）/ colleague（同事，32）/ boss（领导，33），共 40 题
- 核心内容约束：题干主语永远是「Ta」，选项只描述可观察行为、价值中性
- SQL 生成前需查库取 `questions` / `opts` 表 `MAX(id)` 作为 id 起点（或手工传 `--q-max` / `--o-max`）

> **内容规范（唯一内容契约）**见 [`ref/third_person/third_person_content_design.md`](ref/third_person/third_person_content_design.md)；后端消费设计见 `ref/third_person/third_person_test_design.md`。

---

## 5. 配置示例

```yaml
pipeline:
  article_type_source: db  # "db"（从CSV/CLI读取，冷启动用）或 "topic_planner"（LLM自主判断，多类型模式用）

llm:
  openai:
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1
  claude:
    api_key: ${CLAUDE_API_KEY}
  kimi:
    api_key: ${KIMI_API_KEY}
    base_url: https://api.moonshot.cn/v1
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    base_url: https://api.deepseek.com/
  zhipu:
    api_key: ${ZHIPU_API_KEY}
    base_url: https://open.bigmodel.cn/api/anthropic   # Anthropic 兼容代理
  # OpenAI 兼容的本地/自建端点（llm.NewClient 统一走 /v1/chat/completions，api_key 可留空）
  ollama:
    base_url: http://localhost:11434/v1
    model: qwen3:8b
  lm_studio:
    base_url: http://localhost:1234/v1
    model: qwen/qwen3.5-9b
  default_model: deepseek-v4-flash  # 可选: gpt-4o, claude-sonnet-4-6, kimi-k2-6, deepseek-chat, 本地模型名
                                    # 注意：relationship / thirdperson CLI 提示 deepseek-v4-flash 可能返回空内容，此时用 --model deepseek-chat 覆盖

humanizer:
  banned_phrases_file: data/banned_phrases.txt
  max_ppl: 120
  min_ppl: 60
  error_rate: 0.003

image:
  # 可选，不配置则跳过真实图片匹配
  unsplash_access_key: ${UNSPLASH_ACCESS_KEY}
  pexels_api_key: ${PEXELS_API_KEY}
  dall_e_model: dall-e-3      # 预留，后续对接 DALL-E 图片生成 API
  # gen-image 工具配置
  gen_provider: siliconflow                        # 服务商：siliconflow / ark / openai / zhipu
  gen_base_url: https://api.siliconflow.cn/v1      # API 地址
  gen_api_key: ${IMG_GEN_KEY}                      # API 密钥（或通过环境变量 IMG_GEN_KEY 传入）
  gen_model: black-forest-labs/FLUX.1-dev          # 模型名
  gen_size: 1024x1024                              # 图片尺寸

oss:
  endpoint: oss-cn-hangzhou.aliyuncs.com
  bucket: personality-matrix
  access_key: ${OSS_AK}
  secret_key: ${OSS_SK}
  cdn_domain: https://cdn.mbtisite.com   # CDN 域名，用于生成 JSON-LD 中绝对图片 URL

site_url: https://www.mbtisite.com       # 网站域名，用于 JSON-LD 中的 URL 和图片路径

database:
  dsn: root:password@tcp(127.0.0.1:3306)/content_db?charset=utf8mb4&parseTime=true&loc=Local
  # O*NET 数据仓库（只读），career import 数据源
  onet_dsn: root@tcp(127.0.0.1:3306)/onet_db?charset=utf8mb4&parseTime=true&loc=Local
  # 职业数据目标库（写入）
  career_dsn: root@tcp(127.0.0.1:3306)/career_db?charset=utf8mb4&parseTime=true&loc=Local
  # 双人关系分析 seed 导入目标库（pairanalysis import-seed；生产用 --dsn 覆盖）
  personality_dsn: ""

# 双人关系分析内容流水线配置（设计见 ref/third_person/kb_rag_design.md）
pairanalysis:
  top_k: 8
  diff_threshold: 20
  concurrency: 2
  kb_path: data/knowledge/kb.sqlite       # knowledge CLI 产出的知识库
  modules_path: data/pairanalysis/modules # 共享模块缓存
  scenes_path: data/pairanalysis/scenes.yaml
  langs: [zh-CN, ja, ko, es, pt-BR]
  # 各步骤可用不同本地/远程模型；缺省走 llm.default_model
  steps:
    modules:   { provider: ollama, model: qwen3:0.6b }
    assemble:  { provider: ollama, model: qwen3:0.6b }
    translate: { provider: ollama, model: qwen3:4b }
```

### 5.1 核心数据表（精简）

`content_db` 仅用于文章流水线的状态跟踪和元数据，最终 Markdown 文件不入库。

| 表名 | 用途 | 核心字段 |
|------|------|---------|
| `tasks` | 批次任务 | id, name, status, total_items, completed_items, config(json), created_at |
| `keywords` | 关键词库 | id, keyword, created_at |
| `articles` | 文章元数据 | id, task_id, keyword_id, group_id（多语言分组标识）, lang, article_type, slug, title, meta_description, status, oss_path, featured_image, seo_score, ai_detection_score, created_at |
| `translations` | 翻译关联 | id, group_id, article_id, lang, is_original |

其他库 / 存储（各垂直流水线，见 §4.5~§4.7 与配置 `pairanalysis`）：

| 存储 | 用途 | 核心表 / 结构 |
|---|---|---|
| `career_db` | 职业探索数据（career 流水线写入） | `career`, `career_category`, `career_skill`, `career_ability`, `career_knowledge`, `career_mbti_score` |
| `onet_db` | O*NET 只读数据仓库（career import 数据源） | `occupation_data`, `essential_skills`, `abilities`, `knowledge`, `task_statements` 等 |
| 测评站库 | 第三人测试题库（`thirdperson sql` 产出 INSERT，灌入测评站） | `questions` / `opts` 等四表 + 后端维护的 `survey_metas` |
| `data/knowledge/kb.sqlite` | 手册知识库（`knowledge` CLI 产出，FTS5 全文检索） | chunks + metadata + FTS5 索引 |
