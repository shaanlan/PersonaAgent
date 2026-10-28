
# Content Engine PRD
## MBTI 性格评测内容自动化生成流水线

| 文档信息 | 内容 |
|---------|------|
| 产品名称 | MBTI Content Engine（MCE） |
| 版本 | v1.2 |
| 创建日期 | 2026-05-26 |
| 更新日期 | 2026-10-23（拆分：设计内容移至 `design.md`，本文档只保留产品需求） |
| 文档类型 | 产品需求文档（PRD） |

### 文档索引

| 文档 | 内容 |
|---|---|
| `requirement.md`（本文档） | 产品需求：做什么、产出什么、验收标准 |
| [`design.md`](design.md) | 技术设计：系统架构、Agent 工作流、CLI、配置、数据流 |
| `ref/career/career_pipeline_runbook.md` | 职业探索流水线操作手册（命令级细节的单一事实源） |
| `ref/relationship/3-relationship_content_pipeline.md` | 关系探索流水线设计与操作 |
| `ref/third_person/third_person_content_design.md` | 第三人测试题库内容规范（唯一内容契约） |

---

## 1. 产品概述

### 1.1 背景
MBTI 性格评测独立网站需要大量高质量、结构化、可被搜索引擎识别为权威且具有情感共鸣的文章。人工撰写效率低、成本高，而直接使用大模型生成的内容容易被识别为 AI 文本，导致降权。因此需要一个内容生成引擎，内置防AI检测、SEO优化的内容生产引擎，既满足用户阅读体验，又符合搜索引擎抓取规律。

### 1.2 产品定位
Content Engine 是一套基于 Agent Workflow 的内容生产流水线，通过多个专业化 Agent 协同，将 MBTI 主题关键词转化为可直接发布的 Markdown 文章。输出符合 Google 等搜索引擎质量要求，易于被广告联盟和搜索引擎收录。

除文章流水线（`mce`）外，站点还包含职业探索、关系探索、第三人测试等垂直内容产品，各自有独立的 CLI 流水线，共用同一套 LLM 客户端、Prompt 管理与配置体系：

| 产品线 | CLI | 产物 | 需求章节 |
|---|---|---|---|
| 文章流水线 | `cmd/mce` | `{lang}/{article_type}/{slug}.md` | 本文 §2 / §5 |
| 职业探索 | `cmd/career` | `data/career/{lang}/{slug}.md` | §3.1 |
| 关系探索 | `cmd/relationship` | `data/relationship/{lang}/pages/{slug}.md` | §3.2 |
| 第三人测试 | `cmd/thirdperson` | `data/third_person/tp_*.json` + `tp_third_person.sql` | §3.3 |

文章流水线支持七种文章类型：**列表型**（listicle）、**指南型**（guide）、**对比型**（comparison）、**通用文章**（article）、**故事型**（story）、**人格剧场**（personality_drama）、**分析型**（analysis）

### 1.3 核心价值
- **防 AI 检测**：多阶段人性化处理，模拟人类写作特征，降低 AI 内容被识别概率。
- **SEO 就绪**：自动生成 Title、Description、Slug、JSON-LD 结构化数据。
- **广告联盟友好**：在 Markdown 中预留广告位标记（如 `<!-- AD_SLOT_1 -->`），前端可直接渲染 Google AdSense。
- **开发者友好**：输出结构化 Markdown 文件，直接与静态站点生成器（如 Hugo、Next.js）集成。

---

## 2. 核心功能（文章流水线）

- **关键词文件输入**：支持文本或 CSV，人工指定即可
- **单任务顺序执行**：逐条处理关键词，每条任务可断点续跑，前期串行执行即刻，不需要并发任务，每步状态持久化到MySQL
- **断点续跑**：支持 `--phase` 和 `--article` 参数从指定阶段恢复执行，中间结果以 JSON 快照持久化到本地文件系统，无需重新执行已完成阶段
- **多 Agent 流水线生成**：
  `Topic Planner → Outliner → Writer → Rewriter → Humanizer → Visual Builder → SEO Meta Generator → Final Assembler → Translator → Upload`
- **自动标签生成**：从关键词中提取语义单词（过滤标点和纯数字纯符号），结合文章类型自动生成 Front Matter tags 标签数组，始终包含 "MBTI" 标签
- **字数追踪**：Writer / Rewriter 阶段输出含 `WordCount` 字段，SEO Meta 阶段独立计算字数用于关键词密度分析
- **防 AI 检测**：困惑度控制、个人经历注入、句式复杂度调整、智能跳过Markdown标签
- **SEO 优化**：自动生成 Title、Description、Slug、JSON-LD Article schema
- **广告联盟就绪**：预留广告位标记，支持 Google AdSense 等。
- **多语言翻译**：支持 `zh-CN` / `en` / `ja` / `ko` / `es` / `pt-BR` 六种语言。流水线在 Assembler 后自动将文章翻译到目标语言，图片复用、SEO 元数据本地化生成
- **跳过翻译模式**：支持 `--skip-translation` 参数跳过翻译阶段，适用于先生成中文文章经人工编辑润色后再单独执行翻译的场景
- **多 LLM 支持**：OpenAI GPT-4o、Claude、Kimi、DeepSeek、智谱（Anthropic 兼容代理），以及 Ollama / LM Studio 等 OpenAI 兼容本地端点，可配置 fallback。
- **文章类型**：`guide` / `listicle` / `comparison` / `article` / `story` / `personality_drama` / `analysis`
  - `personality_drama` 类型默认内部结构为：**5% Hook / 10% 人格设定 / 70% 故事 / 10% 心理解析 / 5% FAQ**

各 Agent 的输入输出、LLM 参数与 JSON-LD 规范等设计细节见 [`design.md`](design.md) §2。

---

## 3. 垂直产品线需求

> 本章只描述各垂直产品的**需求**（目标、输入、产物、验收标准）；实现设计与 CLI 用法见 [`design.md`](design.md) §4 与 `ref/` 下各 runbook。

### 3.1 职业探索（career）

- **目标**：为用户提供职业探索页，展示每个职业的介绍、核心技能、以及 16 型 MBTI 人格与该职业的适配度。
- **输入**：人工维护的职业 seed（含每职业 16 维权重）+ O*NET 职业数据库（外部权威数据源，1016 个职业）。
- **产物**：每个职业的内容页 Markdown（6 种语言），含职业介绍、技能/知识/任务要点、16 型匹配分数（rank 1-16）、人格适配解读（`personality_sections`）、AI 时代影响、FAQ。
- **验收标准**：
  - 匹配分数由确定性算法产出（非 LLM 生成），可复现、可解释
  - 16 型分数完整注入该职业的所有语言版本，语言间一致
  - 内容页可被前端直接消费（frontmatter 契约稳定）
  - 全流程幂等，可重复执行不产生重复数据

### 3.2 关系探索（relationship）

- **目标**：建立关系知识内容体系，覆盖 32 类真实关系（亲子、伴侣、婚姻、友谊、同事、上下级等），帮助用户从关系科学视角理解各类关系，而非简单的「A 型 × B 型是否相配」。
- **输入**：关系科学书籍语料（手册章 digest）+ 关系目录（32 类关系的结构化定义）。
- **产物**：每类关系的详情页 Markdown（多语言），含关系定义、核心概念、关系画像、有出处的证据引用（可溯源到手册章节）、MBTI 分型视角推断。
- **验收标准**：
  - 每条证据引用可溯源到手册具体章节（不做无出处的断言）
  - 多语言版本结构一致（同一关系各语言页面章节完整对齐）
  - 页面结构稳定，前端可确定性渲染

### 3.3 第三人测试题库（thirdperson）

- **目标**：生产「他评版」MBTI 测试题库——用户凭日常观察估测另一个人（恋人 / 朋友 / 同事 / 领导）的类型，补足自测之外的场景。
- **输入**：内容规范（`ref/third_person/third_person_content_design.md`，唯一内容契约）。
- **产物**：4 个角色 × 10 题 × 6 种语言的题库（JSON），以及可直接灌入测评库的 SQL。
- **验收标准**：
  - 题干主语永远是「Ta」（第三人称），只描述外部可观察行为，不问内心想法
  - 选项价值中性（两个选项都是正常可接受的行为）
  - 同一角色 10 题覆盖 ≥6 类不同观察场景
  - 6 种语言题目结构一致（题量、维度分布、计分一致）
  - 通过内容规范质检清单后方可入库

---

## 4. 防 AI 检测策略

| 策略 | 实现方式 | 阶段 |
|------|--------|------|
| 困惑度控制 | 内部部署 GPT-2 Small 计算 PPL，目标区间 60-120 | Humanizer 循环 |
| Burstiness | 交替长短句，计算句子长度标准差，要求 > 8 | Humanizer prompt 指令 |
| 禁止短语表 | 维护 500+ 常见 AI 短语黑名单，强制替换 | Humanizer 后处理 |
| 个人故事注入 | 提示词要求插入 1-2 个虚拟个人经历，与主题相关 | Humanizer |
| 随机不完美 | 0.3% 概率删除逗号、使用小写 "i" 等，可配置 | Humanizer 后处理 |
| 段落重组 | 随机调整段落顺序（在合理范围内） | Humanizer |
| 事实性小错误 | 非关键数字稍作修改（如 "78%" 改成 "around 8 in 10"）| Writer/Humanizer |

**评估指标**：
- 原始文本 AI 检测概率（使用 Originality.ai API）应 < 20%
- 人性化后目标 < 5%

---

## 5. 输入与输出

### 5.1 输入格式

本地文本文件，每行一个关键词：
```
INTJ careers
ENFP relationships
best jobs for INTJ
```

或 CSV：
```csv
keyword,article_type
INTJ careers,listicle
ENFP relationships,guide
```

### 5.2 输出格式
personality_drama 类型文章内部固定结构：Hook / 人格设定 / 故事 / 心理解析 / FAQ
保留原有 Front Matter、广告位、JSON-LD 结构化数据

本地目录结构（以 "INTJ careers" 关键词为例，6 种语言）：
```
data/output/
├── zh-CN/
│   └── listicle/
│       └── intj-shi-ye.md
├── en/
│   └── listicle/
│       └── intj-careers.md
├── ja/
│   └── listicle/
│       └── intj-kyaria.md
├── ko/
│   └── listicle/
│       └── intj-career.md
├── es/
│   └── listicle/
│       └── carreras-intj.md
└── pt-BR/
    └── listicle/
        └── carreiras-intj.md
```

### 5.3 最终 Markdown 文件示例结构

```markdown
---
title: "Top 10 Careers for INTJ Personalities in 2026"
description: "Discover the best career paths for INTJ types..."
slug: "top-10-careers-for-intj"
date: "2026-05-26"
lastmod: "2026-05-26"
lang: "en"
category: "listicle"
tags:
  - INTJ
  - career
  - MBTI
  - Listicle
cover: ""
---

If you're an INTJ like me, you've probably spent hours thinking about the perfect career…

<!-- AD_SLOT_1 -->

## 1. Software Architect
…content…

<!-- AD_SLOT_2 -->

### 相关内容

- [Related Article Title](/en/listicle/related-slug)
  Related article description…

<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Article","headline":"Top 10 Careers for INTJ Personalities in 2026",...}
</script>
```

> 执行流程（import / run / export / import-seed 的典型场景）与 Slug 生成规则属于设计内容，见 [`design.md`](design.md) §3。

---

## 6. 非功能性需求

- **性能**：单篇文章生成时间 < 120 秒（含所有阶段）。
- **可靠性**：LLM 调用失败自动重试 3 次（指数退避），单条失败不影响后续关键词。
- **可扩展性**：Agent 可插拔，通过配置文件新增自定义 Agent；Image Matcher 等 Agent 后续可无缝接入。
- **成本控制**：每万词成本控制在 $0.5 以内（通过混合使用轻量模型和强模型）。

### 6.1 降级策略（Fallback / Degradation）

非致命错误（组件降级而非整个流水线失败）：

| 场景 | 降级行为 |
|------|---------|
| SEO Meta LLM 调用失败或返回格式解析错误 | 自动 fallback 到规则化生成：基于关键词生成 title/description/slug，硬编码 JSON-LD，流水线继续 |
| Image Matcher 外部图片 API 失败 | 使用占位路径 `/images/{article_type}/{slug}-{n}.jpg`，`featured_image` 留空，流水线不中断 |
| Translator 输出被截断且 JSON 恢复失败 | 标记翻译文章为 `failed`，继续处理其他语言，不影响源文文章状态 |
| Humanizer 困惑度评估器不可用 | 跳过困惑度评估，仍返回最后一次改写结果 |
| 数据库连接失败 | CLI 启动阶段立即报错退出，不进入流水线 |

---
