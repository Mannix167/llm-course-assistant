你正在复核经过规则解析后的课件 PDF 页面。

你的任务不是写报告内容，而是修正后续流程要用的页级参数。

请针对每一页判断：
1. 这页是否可能成为最终报告里的视觉候选页
2. 这页抽取出来的文字是否应该继续传给下游纯文本模型
3. 这页最合适的页面类型

页面类型只能使用以下六种：
- text
- text_with_visual
- table_like
- diagram_like
- formula_like
- title_or_transition

判断规则：
- 只有当这一页本身可能作为图片、表格、图示、公式页进入最终报告时，才把 `candidate_for_visual` 设为 `true`
- 如果这一页的文字提取结果噪声很大、表格化严重、公式错位明显，或者视觉结构强到会误导纯文本分析，就把 `exclude_text_from_llm` 设为 `true`
- 不要决定最终是否插入，只判断“是否可能成为候选页”
- 尽量保守，不要把普通文字页过度标成视觉候选
- 如果一页里同时有重要图示和说明文字，优先使用 `text_with_visual`
- `llm_reason` 必须使用中文，简洁说明理由

只返回合法 JSON，不要输出任何解释文字。格式必须是：

{{
  "pages": [
    {{
      "page_number": 1,
      "page_type": "text",
      "candidate_for_visual": false,
      "exclude_text_from_llm": false,
      "llm_reason": "中文简短理由"
    }}
  ]
}}
