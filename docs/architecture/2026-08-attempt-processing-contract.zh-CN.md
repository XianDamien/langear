# LanGear v1 Attempt Processing 契约

状态：已确认，2026-08-27

本文冻结 Attempt 的输入快照、异步处理状态和 AI Feedback 外层 contract。非 AI 的持久化、事务和媒体边界见 `2026-08-non-ai-core-contract.zh-CN.md`。

## Attempt 输入

`input_type` 仅允许：

- `none`：Vocabulary 直接翻面；
- `audio`：Retelling Card 的最终录音媒体；
- `text`：Translation Card 或 Dictation Card 的原始用户文本。

Attempt 创建时保存原始 `input_snapshot`、完整 `note_snapshot`、`front_snapshot`、`back_snapshot` 和 `answer_snapshot`。这些快照创建后不可变；规范化文本、ASR 和 AI 结果必须另存，不能覆盖学习者原始输入。

## 独立处理状态

`asr_status` 与 `ai_status` 分别使用同一组状态：

```text
skipped
pending
processing
completed
failed
```

- `skipped` 表示当前 Card Template 不适用，不创建对应 Outbox；
- `pending` 表示 Outbox 已与 Attempt 在同一事务提交；
- `processing` 表示 Worker 已认领任务；
- `completed` 表示结构化结果已写回同一 Attempt；
- `failed` 保存稳定的 provider-independent error code 和可展示消息，并允许幂等重试同一 Attempt。

ASR、AI Feedback 与 Rating 各自补写独立字段。任一处理失败都不能回滚 Attempt 或 Rating，也不能创建第二条 Attempt。

结果字段与状态满足：`completed` 时对应 result 必须非空；`skipped|pending|processing|failed` 时 result 为 `null`。因此 `ai_feedback=null` 本身不表达处理原因，调用方必须同时读取 `ai_status`。AI Feedback 是可选增强，空值不影响背面 Note 内容、Rating 或 Queue 推进。

## AI Feedback 外层 Envelope

Retelling 与 Translation 共用外层 envelope，前端可据 `feedback_kind` 选择 mode-specific 组件：

```json
{
  "schema_version": "1",
  "feedback_kind": "retelling",
  "summary": "整体表达清楚，注意一个遗漏和两处语音问题。",
  "issues": [
    {
      "category": "completeness",
      "message": "遗漏了时间条件。",
      "evidence": "after work",
      "suggestion": "补充完整的时间关系。",
      "audio_offset_ms": 1800
    }
  ],
  "suggestions": [
    {
      "text": "可以先保证信息完整，再调整表达自然度。",
      "reason": "本次主要问题是内容遗漏。"
    }
  ],
  "details": {}
}
```

稳定公共字段为 `schema_version`、`feedback_kind`、`summary`、`issues` 和 `suggestions`。`issues[].audio_offset_ms` 只对音频输入有意义，文本输入返回 `null`。`details` 是按 `feedback_kind` 区分的 discriminated schema，不允许前端把两个 mode 的详情结构混用。

AI Feedback 使用中文说明；被评价的英文片段、修改后的英文和建议答案保留英文。v1 不返回数值总分，AI 不产生 Again/Hard/Good/Easy，不直接修改 Card 或 FSRS。

## 独立 Evaluator 与 Prompt

### Retelling Card

- `feedback_kind=retelling`
- `prompt_key=sentence_retelling_feedback`
- 评价维度：内容完整度、发音、流畅度和表达自然度；
- 允许音频时间点定位；
- mode-specific `details` 可包含各维度的文字总结和建议复述，不包含数值总分。

### Translation Card

- `feedback_kind=translation`
- `prompt_key=sentence_translation_feedback`
- 输入为用户英文文本、中文题面、参考英文答案和 Note 快照；
- 评价维度：语义完整度、语法、用词和表达自然度；
- `audio_offset_ms` 固定为 `null`；
- mode-specific `details` 可包含建议译文，不包含发音或流畅度字段。

每次结果在 Attempt 上同时保存 `prompt_key`、`prompt_version`、`provider`、`model` 和 `schema_version`。重试默认使用 Attempt 首次创建时冻结的 prompt/model 配置，以保证同一次 Attempt 的处理可追溯；只有显式的重新评估操作才能升级版本。

## 非 AI Evaluator

Dictation Card 使用独立的同步确定性文本 evaluator。它保存 `deterministic_result` 和 evaluator version，但 `asr_status=skipped`、`ai_status=skipped`、`ai_feedback=null`，不伪装为 AI Feedback。以后若增加 Dictation AI evaluator，必须通过新的 prompt/schema version 修改 contract；v1 不预创建空任务。

正确性比对包含单词、大小写、标点和空格。Evaluator 只执行版本化的 Unicode/排版等价规范化，不 lowercase、不 trim、不折叠连续空格、不删除标点。结果返回 `exact_match` 以及分类为 `word|capitalization|punctuation|spacing` 的 diff；该结果只辅助学习者自行 Rating，不自动推进 FSRS。

## Retelling AI 输入依赖

Retelling AI 直接读取最终录音、题面和 Attempt 快照；ASR 任务独立生成 transcript。ASR provider 失败时 AI 仍可完成，符合 ASR/AI 独立失败边界，并保留发音、流畅度和音频时间点评价能力。AI evaluator 需要支持多模态音频输入；它不能只读取 ASR transcript。
