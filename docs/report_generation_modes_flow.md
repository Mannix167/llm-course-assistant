# 三种报告生成模式流程与大模型输入梳理

本文档梳理当前 `backend` 中三种报告生成模式的真实执行流程、大模型调用、输入内容和提示词来源，作为后续优化报告质量与 Prompt 的基线文档。

主要实现位置：

- `backend/app/services/report_service.py`：报告生成主流程、章节生成、插图处理、质量检查。
- `backend/app/services/llm_service.py`：统一大模型调用封装、provider/model 选择、文本/JSON/视觉调用。
- `backend/app/prompts/`：各步骤 Prompt 模板。
- `backend/app/config.py`：各 purpose 默认 provider/model 配置。

## 一、共用前置流程

三种模式都从 `ReportService._generate_report()` 进入，且都会先完成以下步骤。

### 1. 读取已解析页面

输入来源是数据库中的 `Page` 记录，按页码升序读取：

- `page_number`
- `text`
- `analysis_text`
- `image_path`
- `text_length`
- `analysis_text_length`
- `image_count`
- `page_type`
- `candidate_for_visual`
- `candidate_reasons`
- `layout_flags`
- `features`

这些数据来自 PDF 解析阶段，解析结果也会落到 `storage/course_xxx/pages.json`。

### 2. 生成目录、整课总结、章节规划

如果当前课程已有缓存的章节规划和概要，会复用缓存，不再调用大模型；否则调用 `outline.md`。

大模型调用：

- step_name：`generate_outline`
- 调用函数：`_run_text_step(..., expect_json=True)`
- purpose：默认 `standard_text`
- 默认模型配置：`STANDARD_TEXT_PROVIDER=deepseek`，`STANDARD_TEXT_MODEL=DeepSeek-V3.2`
- temperature：`0.1`
- max_tokens：默认 `8192`
- system message：`你是严谨的中文课件结构分析助手，只输出用户要求的内容。`
- user message：渲染后的 `backend/app/prompts/outline.md`
- 输出：JSON，随后被规范化为 `OutlinePlan`

Prompt 输入变量：

- `course_title`：课程标题。
- `page_count`：总页数。
- `course_text`：由 `_build_outline_context(pages)` 构造。

`course_text` 的构造方式：

- 每页最多取页面摘要 `features.page_summary`，否则取 `analysis_text` 或 `text` 前 360 字。
- 每页附带元信息：`[第 N 页 | page_type]`。
- 若存在 `features.title_candidates`，会附带最多两个标题候选。

`outline.md` 要求模型输出：

- `outline_markdown`
- `overall_summary_markdown`
- `chapters`
- 每个 chapter 包含 `title`、`start_page`、`end_page`、`content_summary`、`key_points`

### 3. 校验章节规划

目录生成后，系统会运行本地规则校验，不调用大模型。

step_name：`validate_chapter_plan`

主要规则：

- 页码范围裁剪到实际 PDF 页码内。
- 修正章节页码倒置。
- 避免章节页码交叉或回退。
- 删除没有任何有效文本的章节。
- 若全部章节无效，则回退为一个覆盖全课的章节。

校验后的章节会写入 `Chapter` 表，并写入 `generation_context_cache.json`。

### 4. 章节并行生成

三个模式的章节生成都通过 `_run_chapter_jobs_parallel()` 并行执行：

- 最大并发数：`min(3, 章节数)`
- 会记录 step：`parallel_chapter_generation_plan`
- 每个章节独立调用大模型或视觉模型。

章节上下文由 `_build_pages_text()` 构造。每页输入格式大致为：

```text
[第 N 页 | page_type | context_role | importance=分数]
页面摘要：...
页面正文或截断后的正文
```

每页文本预算由 `_page_context_text()` 决定：

- `title_or_transition`、`table_like`、`formula_like`、`diagram_like`：优先使用摘要，否则取正文前 320 字。
- importance < 2.2：摘要或正文前 420 字。
- 2.2 <= importance < 4.0：正文最多 900 字。
- importance >= 4.0：正文最多 1800 字。

## 二、standard 标准模式

标准模式目标是：先生成纯文本章节讲解，再让视觉模型判断是否插入候选页截图。

### 流程总览

1. 共用目录与整课总结生成。
2. 按章节生成纯文本讲解。
3. 对每章筛选最多 4 个候选视觉页。
4. 调用视觉模型生成图片插入计划。
5. 本地把图片 Markdown 插入章节内容。
6. 拼接最终报告。
7. 执行本地质量检查。

### 步骤 1：标准章节讲解

大模型调用：

- step_name：`generate_chapter_{chapter_index}`
- Prompt 文件：`backend/app/prompts/chapter.md`
- 调用函数：`_run_text_step(..., expect_json=False)`
- purpose：默认 `standard_text`
- 默认模型配置：`STANDARD_TEXT_PROVIDER=deepseek`，`STANDARD_TEXT_MODEL=DeepSeek-V3.2`
- temperature：`0.3`
- max_tokens：默认 `4096`
- system message：`你是善于把课件讲清楚的中文课程讲解助手。`
- user message：渲染后的 `chapter.md`
- 输出：Markdown 正文

Prompt 输入变量：

- `course_title`
- `chapter_title`
- `start_page`
- `end_page`
- `chapter_summary`：目录步骤得到的简短章节说明。
- `chapter_text`：本章页码范围内的结构化页面文本。

`chapter.md` 的核心要求：

- 讲清本章内容、核心概念和逻辑关系。
- 尽量按页码顺序解释。
- 可适度补充背景，但不要偏离课件。
- 章节末尾加入“本章小结”。
- 不插入图片，不输出 JSON。

### 步骤 2：标准模式插图判断

本地先调用 `_select_visual_candidate_pages()` 在当前章节页码范围内筛选候选页：

- 若 `candidate_for_visual=True`，进入候选。
- 若 `image_count > 0`，进入候选。
- 若 `page_type` 属于 `diagram_like`、`table_like`、`formula_like`、`text_with_visual`，进入候选。
- 按 `_visual_candidate_score()` 排序。
- 标准模式每章最多传入 4 个候选页。

大模型调用：

- step_name：`generate_image_insert_plan_{chapter_index}`
- Prompt 文件：`backend/app/prompts/image_insert.md`
- 调用函数：`_run_vision_json_step()`
- purpose：固定 `visual_vision`
- 默认模型配置：`VISUAL_VISION_PROVIDER=kimi`，`VISUAL_VISION_MODEL=Kimi-K2.5`
- temperature：`0.1`
- max_tokens：`4096`
- system message：`你是严谨的课件图文关系分析助手，只输出合法 JSON。`
- user message：渲染后的 `image_insert.md`
- images：候选页截图绝对路径列表
- 输出：JSON 插图计划

Prompt 输入变量：

- `course_title`
- `chapter_title`
- `start_page`
- `end_page`
- `chapter_markdown`：上一步生成的章节 Markdown。
- `candidate_pages`：候选页 JSON。
- `max_insertions`：当前写死为 `2`。

`candidate_pages` 单页结构：

```json
{
  "page_number": 12,
  "page_type": "diagram_like",
  "text": "页面 analysis_text 或 text，最多 1000 字",
  "image_count": 1,
  "candidate_reasons": [],
  "layout_flags": [],
  "features": {}
}
```

`image_insert.md` 要求模型输出：

- `insertions`
- 每个 insertion 包含：
  - `page_number`
  - `should_insert`
  - `insert_after_heading`
  - `caption`
  - `minor_text_patch`
  - `reason`

本地后处理：

- 只保留候选页范围内、`should_insert=true`、未重复的图片。
- 每章最多保留 2 张。
- `_apply_image_insertions()` 在对应标题后插入：

```markdown
![第N页课件截图](../../../images/page_NNN.png)

> 图示说明：...
```

若有 `minor_text_patch`，会放在图片前。

### 步骤 3：标准模式最终产物

标准模式会额外生成 `image_insert_plan.json`，并在 `report.review_result` 中保存：

- `image_insert_plan`
- `quality_checks`

最终报告结构：

```markdown
# 课程标题 标准学习报告

## 课程目录

## 课程整体总结

## 分章节详细讲解

各章节 Markdown
```

## 三、advanced 高级模式

高级模式目标是：把章节文本和候选页截图一起发给多模态模型，由模型直接生成带图片引用的章节讲解。

### 流程总览

1. 共用目录与整课总结生成。
2. 每章筛选最多 3 个候选视觉页。
3. 若有候选图，调用视觉模型生成图文章节。
4. 若没有候选图，退化为文本模型生成章节。
5. 从章节 Markdown 中提取实际插入的 `page_NNN.png`，形成插图计划。
6. 拼接最终报告。
7. 执行本地质量检查。

### 高级章节图文生成

候选页筛选：

- 调用 `_select_visual_candidate_pages(..., max_pages=3)`。
- 候选逻辑同标准模式。
- 候选页 JSON 会额外包含 `markdown_image`，例如 `../../../images/page_012.png`。

有候选图片时的大模型调用：

- step_name：`generate_advanced_chapter_{chapter_index}`
- Prompt 文件：`backend/app/prompts/advanced_report.md`
- 调用函数：`_run_vision_text_step()`
- purpose：`advanced`
- 默认模型配置：`ADVANCED_PROVIDER=kimi`，`ADVANCED_MODEL=Kimi-K2.5`
- temperature：`0.2`
- max_tokens：`3200`
- system message：`你是中文课件图文讲解专家。请基于文字和截图生成准确、克制、结构清晰的 Markdown。`
- user message：渲染后的 `advanced_report.md`
- images：候选页截图绝对路径列表
- 输出：Markdown 正文

无候选图片时的大模型调用：

- step_name：同上。
- 调用函数：`_run_text_step(..., expect_json=False)`
- purpose：`advanced`
- temperature：`0.3`
- max_tokens：`3200`
- system message：`你是中文课件讲解专家。请生成准确、克制、结构清晰的 Markdown。`
- user message：渲染后的 `advanced_report.md`
- 输出：Markdown 正文

Prompt 输入变量：

- `course_title`
- `chapter_title`
- `start_page`
- `end_page`
- `chapter_summary`
- `chapter_text`
- `candidate_pages`
- `max_insertions`：当前写死为 `2`。

高级模式 `candidate_pages` 单页结构：

```json
{
  "page_number": 12,
  "page_type": "diagram_like",
  "text": "页面 analysis_text 或 text，最多 1000 字",
  "image_count": 1,
  "candidate_reasons": [],
  "layout_flags": [],
  "features": {},
  "markdown_image": "../../../images/page_012.png"
}
```

`advanced_report.md` 的核心要求：

- 综合净化页面文本、候选截图和候选页信息。
- 重点观察图片里的结构图、表格、公式、箭头、坐标图、矩阵排版等。
- 模型自行判断是否插图，直接在 Markdown 中插入图片引用。
- 只允许使用 `candidate_pages` 给出的 `markdown_image`。
- 每章最多插入 2 张。
- 如果图片不能显著帮助理解，不要插入。
- 控制篇幅，避免过度展开。

### 高级模式插图计划

高级模式没有单独的插图判断调用。系统通过 `_build_advanced_image_plan()` 从章节 Markdown 中正则提取 `page_NNN.png`，生成：

```json
{
  "insertions": [
    {
      "page_number": 12,
      "chapter_title": "...",
      "chapter_index": 1,
      "source": "advanced_chapter_markdown"
    }
  ]
}
```

最终也会写入 `image_insert_plan.json` 和 `report.review_result`。

## 四、extended 扩展模式

扩展模式目标是：先从课件章节文本中抽取知识骨架，再基于知识骨架生成更利于理解的拓展讲解。当前扩展模式不插图。

### 流程总览

1. 共用目录与整课总结生成。
2. 每章先提取知识骨架。
3. 把知识骨架格式化为 Markdown。
4. 基于知识骨架生成扩展讲解。
5. 拼接最终报告。
6. 执行本地质量检查。

### 步骤 1：提取章节知识骨架

大模型调用：

- step_name：`extract_extended_knowledge_{chapter_index}`
- Prompt 文件：`backend/app/prompts/extended_extract.md`
- 调用函数：`_run_text_step(..., expect_json=True)`
- purpose：`standard_text`
- 默认模型配置：`STANDARD_TEXT_PROVIDER=deepseek`，`STANDARD_TEXT_MODEL=DeepSeek-V3.2`
- temperature：`0.1`
- max_tokens：`4096`
- system message：`你是严谨的中文课程知识结构分析助手，只输出合法 JSON。`
- user message：渲染后的 `extended_extract.md`
- 输出：JSON 知识骨架

Prompt 输入变量：

- `course_title`
- `chapter_title`
- `start_page`
- `end_page`
- `chapter_summary`
- `chapter_text`

`extended_extract.md` 要求模型输出：

- `logic_markdown`
- `core_knowledge_points`
- `keywords`
- `learning_goal`

### 步骤 2：格式化知识骨架

本地调用 `_format_knowledge_skeleton()`，不调用大模型。

格式化后的结构：

```markdown
## 学习目标

...

## 逻辑脉络

...

## 核心知识点

- ...

## 关键词

...
```

### 步骤 3：生成扩展章节讲解

大模型调用：

- step_name：`generate_extended_chapter_{chapter_index}`
- Prompt 文件：`backend/app/prompts/extended_chapter.md`
- 调用函数：`_run_text_step(..., expect_json=False)`
- purpose：`standard_text`
- 默认模型配置：`STANDARD_TEXT_PROVIDER=deepseek`，`STANDARD_TEXT_MODEL=DeepSeek-V3.2`
- temperature：`0.3`
- max_tokens：`4096`
- system message：`你是擅长把抽象知识讲清楚的中文课程老师。`
- user message：渲染后的 `extended_chapter.md`
- 输出：Markdown 正文

Prompt 输入变量：

- `course_title`
- `chapter_title`
- `knowledge_skeleton`：上一步格式化后的知识骨架 Markdown。

`extended_chapter.md` 的核心要求：

- 只根据逻辑脉络、核心知识点和关键词生成扩展讲解。
- 可以补充背景、直观解释、小例子、常见误区和学习建议。
- 不要声称课件中出现了未给出的具体页码、图表或数字。
- 不插入图片。
- 建议结构包括：本章要解决的问题、知识脉络、核心知识点详解、例子、易错点与学习建议、本章小结。

## 五、最终报告拼接与质量检查

三种模式都会使用相同的最终拼接逻辑：

```markdown
# {course.title} {模式标签}学习报告

{outline_markdown}

{summary_markdown}

## 分章节详细讲解

{content_markdown}
```

其中模式标签：

- `standard` -> `标准`
- `advanced` -> `高级`
- `extended` -> `扩展`

拼接完成后执行 `_run_final_quality_checks()`，这是本地规则检查，不调用大模型。

当前检查项：

- 报告是否过短。
- 是否包含 `## 分章节详细讲解`。
- 是否残留 `{{...}}` 模板变量。
- 图片引用页码是否存在。
- “第 N 页”页码是否越界。
- `<mark>` 标签是否配对。
- 是否存在空标题。

检查结果写入：

- step_name：`quality_check_report`
- `report.review_result.quality_checks`

最后写入：

- step_name：`build_final_report`
- `storage/course_xxx/reports/{mode}/report_xxx/final_report.md`

## 六、大模型 purpose 与默认模型

当前报告生成主链路涉及以下 purpose：

| purpose | 用途 | 默认 provider | 默认 model |
|---|---|---|---|
| `standard_text` | 目录、标准章节、扩展模式知识提取、扩展章节 | `deepseek` | `DeepSeek-V3.2` |
| `visual_vision` | 标准模式插图判断 | `kimi` | `Kimi-K2.5` |
| `advanced` | 高级模式图文章节生成 | `kimi` | `Kimi-K2.5` |

`LLMService` 支持 OpenAI-compatible providers：

- `openai_compatible`
- `deepseek`
- `glm`
- `kimi`
- `gemini`
- `qwen`

也支持 `anthropic` 风格调用。

## 七、调用参数汇总

| 步骤 | mode | step_name | Prompt | 调用类型 | purpose | temperature | max_tokens | 输出 |
|---|---|---|---|---|---|---:|---:|---|
| 目录与总结 | 全部 | `generate_outline` | `outline.md` | 文本 | `standard_text` | 0.1 | 8192 | JSON |
| 标准章节 | standard | `generate_chapter_{i}` | `chapter.md` | 文本 | `standard_text` | 0.3 | 4096 | Markdown |
| 标准插图判断 | standard | `generate_image_insert_plan_{i}` | `image_insert.md` | 视觉 | `visual_vision` | 0.1 | 4096 | JSON |
| 高级图文章节 | advanced | `generate_advanced_chapter_{i}` | `advanced_report.md` | 视觉 | `advanced` | 0.2 | 3200 | Markdown |
| 高级无图兜底 | advanced | `generate_advanced_chapter_{i}` | `advanced_report.md` | 文本 | `advanced` | 0.3 | 3200 | Markdown |
| 扩展知识骨架 | extended | `extract_extended_knowledge_{i}` | `extended_extract.md` | 文本 | `standard_text` | 0.1 | 4096 | JSON |
| 扩展章节 | extended | `generate_extended_chapter_{i}` | `extended_chapter.md` | 文本 | `standard_text` | 0.3 | 4096 | Markdown |

## 八、当前质量优化切入点

从流程看，报告质量主要受以下环节影响：

1. `outline.md` 决定章节拆分质量。章节页码错误会传递到所有模式。
2. `_build_outline_context()` 只给目录步骤每页摘要或前 360 字，若页面摘要质量不足，目录容易误判。
3. `_build_pages_text()` 会按重要性截断正文，低分页面可能只保留摘要或较短文本。
4. `chapter.md` 决定标准模式讲解深度和结构。
5. `image_insert.md` 决定标准模式图片是否插得准。
6. `advanced_report.md` 决定高级模式是否能把图片信息转化为讲解价值。
7. `extended_extract.md` 决定扩展模式知识骨架质量，进而影响扩展讲解。
8. 当前质量检查是本地规则检查，还没有使用 `review.md` 做大模型审稿。

