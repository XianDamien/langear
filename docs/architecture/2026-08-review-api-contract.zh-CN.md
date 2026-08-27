# LanGear v1 Review API 契约

状态：已确认，2026-08-27

本文冻结 Review 流程、Card Template 输入要求和运行时 Queue 身份。旧 `/study/session` 和 `/study/submissions` 语义不进入新 contract。

## 输入要求

是否必须录音、必须输入文本或允许直接翻面由 Card Template 定义，不能由全局 Review 页面统一限制。

| Card Template | 正面 | flip 前输入要求 | Attempt 输入 | ASR | AI Feedback |
| --- | --- | --- | --- | --- | --- |
| Vocabulary English-to-Chinese | `word` | 无，可直接翻面 | `none` | `skipped` | `skipped` |
| Vocabulary Chinese-to-English | `meaning` | 无，可直接翻面 | `none` | `skipped` | `skipped` |
| Retelling Card（来自 Sentence Note） | 仅 `reference_audio` | 必须提交一段最终录音 | `audio` | `pending` | `pending` |
| Translation Card（来自 Sentence Note） | `chinese` | 必须提交英文文本 | `text` | `skipped` | `pending` |
| Dictation Card（来自 Sentence Note） | `reference_audio` | 必须提交英文文本；不接受用户录音 | `text` | `skipped` | `skipped` |

Translation 使用 AI Feedback，因为正确译文可能有多种表达。Dictation 使用同步的确定性书写比对，不创建 ASR 或 AI Outbox 任务。单词、大小写、标点和空格都参与正确性判断；只允许不改变书写语义的技术规范化，例如 Unicode NFKC、换行编码统一，以及弯引号/直引号等明确列入 evaluator version 的排版等价字符。不得 lowercase、trim、折叠连续空格或删除标点。无输入或不适用的处理分支在 Attempt 上明确保存为 `skipped`，不能伪装成 `completed`。

## Sentence Card Template 渲染

三个 Card Template 复用同一条 Sentence Note，但分别生成持久化 Card 和独立 FSRS 状态：

| Card Template | 生成条件 | 正面 | 用户输入 | 背面 Note 内容 | Attempt 反馈 |
| --- | --- | --- | --- | --- | --- |
| Retelling | `english + reference_audio` | 仅参考音频 | 必须录音 | 参考音频、英文原文、中文翻译、笔记 | Retelling AI Feedback |
| Translation | `english + chinese` | 仅中文翻译 | 必须输入英文文本 | 英文原文、中文翻译、可选参考音频、笔记 | Translation AI Feedback |
| Dictation | `english + reference_audio` | 仅参考音频 | 必须输入英文文本 | 英文原文、中文翻译、笔记 | 同步 deterministic diff；AI Feedback 可为空 |

`chinese`、`note` 或 Translation 背面的 `reference_audio` 缺失时，对应可选槽位不渲染，不用空字符串占位。正面“仅音频/仅中文”意味着不能提前泄露英文原文、笔记或其他答案字段。

这里的“背面”是 Review API/View 的组合结果，不是把 AI 结果写进 Card Template：

```text
back view
= Card Template 从当前 Sentence Note 渲染的 Note 内容
+ 当前 Attempt 的 deterministic/AI processing result
```

Card/Note 不保存个性化反馈。Attempt 保存 flip 时的 immutable back snapshot，反馈结果继续保存在同一 Attempt 的独立 processing 字段中。

AI Feedback 是背面上的可选增强槽位，不是 Card 完整性的必需字段。Retelling/Translation 在 `ai_status=pending|failed` 时 `ai_feedback=null`；只有 `completed` 时结果非空。Dictation v1 固定 `ai_status=skipped`、`ai_feedback=null`，使用同步 deterministic diff。反馈为空不阻塞 flip、Rating 或 next。

Dictation flip 同步返回 `deterministic_result`：

```json
{
  "kind": "dictation_text_diff",
  "evaluator_version": "1",
  "exact_match": false,
  "differences": [
    {
      "category": "capitalization",
      "expected": "I",
      "actual": "i",
      "expected_range": { "start": 0, "end": 1 },
      "actual_range": { "start": 0, "end": 1 }
    }
  ]
}
```

`category` 只允许 `word|capitalization|punctuation|spacing`。range 使用规范化字符串的 Unicode code-point offset。`exact_match` 和 diff 只提供反馈，不自动选择 Rating，也不改变 FSRS。

Retelling 与 Translation 只共用 AI Feedback 的外层响应 envelope，不共用 evaluator 或提示词。两者分别保存独立的 `feedback_kind`、`prompt_key`、`prompt_version` 和结果 schema 版本；prompt 变化不能改变 Rating，也不能直接推进 FSRS。详细结构见 `2026-08-attempt-processing-contract.zh-CN.md`。

## Next、Flip 与 Rating

三个操作相互独立：

```text
next
→ 返回当前 Card 正面、允许的输入要求和本次出队的 review_token

flip
→ 校验 Card Template 输入要求
→ 幂等创建一个 Attempt 和适用的 Outbox 任务
→ 返回 Attempt、背面快照和四个 Rating 预计间隔

rating
→ 对同一 Attempt 写入用户 Rating
→ 同步推进 Card FSRS

next
→ 获取下一张 Card
```

Rating 响应不夹带下一张 Card。当前 Card 已 flip 但尚未 Rating 时，运行时 Queue 不推进；ASR 或 AI 处于 pending/failed 不阻塞 Rating 或之后的 next。

一次 flip 只创建一条 Attempt。翻面前可有多次临时录音，但只认领 flip 请求指定的最后一个临时媒体；flip 后 rewind 到正面只改变界面，不创建第二条 Attempt，也不允许替换已经提交的输入。

`review_token` 是每次 Card 从 Queue 出队时生成的 UUIDv7。flip 必须回传它，Attempt 以 `(collection_id, review_token)` 唯一；同一 Card 在 15 分钟 learning step 后再次出队会获得新的 token。它防止客户端使用不同 Idempotency-Key 为同一次翻面创建多个 Attempt。

## 运行时 Queue 身份

- 每个 Collection 同一时刻只有一个活跃的临时 `queue_id`；创建或显式 rebuild Queue 会替换此前的 Queue。
- `queue_id` 只标识 Redis/进程内的运行时顺序和 Undo 上下文，不是持久化 Study Session，也不承载学习事实。
- Queue 丢失、过期或服务重启后，后端从 Card 的持久化状态重建并返回新的 `queue_id`。
- `next`、`flip`、`rating` 和 `undo` 都携带 `queue_id`；已被替换或失效的 Queue 返回 `409 QUEUE_EXPIRED`，客户端重新创建 Queue。
- Filtered Deck 的主排序在 Queue 构建时确定；到期的 intraday learning Card 可以按 `due_at` 在运行时重新插入。
- 一个 Collection 最多有一条已 flip、未 Rating 的活跃 Attempt。创建/rebuild Queue 时必须先恢复它并返回已翻面状态；Rating 前不能选择另一张 Card。
- v1 不提供 abandon 未 Rating Attempt。重新进入后恢复该 Attempt，用户完成 Rating 才能继续；ASR/AI 成败不影响此规则。

## HTTP 操作

| 操作 | Route | 说明 |
| --- | --- | --- |
| 创建/重建 Queue | `POST /api/v1/review/queues` | 选择 Standard Deck 子树或 Filtered Deck；替换当前 Collection 的旧 Queue |
| 获取当前项 | `GET /api/v1/review/queues/{queue_id}/next` | 未 flip 时重复调用返回同一 Card/review_token；空队列返回 `card=null` 和剩余计数 |
| 翻面 | `POST /api/v1/review/queues/{queue_id}/flip` | 需要 Idempotency-Key；校验 input、card_id、review_token，创建/重放 Attempt |
| Rating | `PUT /api/v1/review/queues/{queue_id}/attempts/{attempt_id}/rating` | 需要 Idempotency-Key；同步应用 FSRS，不返回下一张 Card |
| Undo | `POST /api/v1/review/queues/{queue_id}/undo` | 只撤销当前运行时上下文最近一次 Rating |
| 查询 Attempt | `GET /api/v1/attempts/{attempt_id}` | 返回快照、Rating 和独立 processing status/result |

创建 Queue 的最小请求：

```json
{
  "scope": {
    "deck_id": "019...",
    "include_descendants": true
  }
}
```

Filtered Deck 也通过其 `deck_id` 创建 Queue，后端从 `decks.kind` 判断，不允许客户端伪造 kind。响应至少包含 `queue_id`、`scope`、`new_remaining`、`learning_remaining` 和 `review_remaining`。

`next` 未翻面响应至少包含：

```json
{
  "queue_id": "019...",
  "review_token": "019...",
  "card": {
    "id": "019...",
    "note_id": "019...",
    "deck_id": "019...",
    "card_template_key": "sentence_translation",
    "card_schedule_revision": 3,
    "front": {},
    "input_requirement": { "type": "text", "required": true }
  }
}
```

flip 请求的 `input` 是 discriminated union：

```json
{ "card_id": "019...", "review_token": "019...", "input": { "type": "none" } }
{ "card_id": "019...", "review_token": "019...", "input": { "type": "text", "text": "I came home late." } }
{ "card_id": "019...", "review_token": "019...", "input": { "type": "audio", "temporary_media_asset_id": "019..." } }
```

文本在 trim 后必须非空，但 Attempt 保存原始输入；音频必须是当前 Collection 未被认领的 temporary private MediaAsset。flip 响应至少包含 Attempt ID、不可变 back/answer snapshot、ASR/AI status 和四个 Rating interval options。

Rating 请求包含 `rating` 和 flip 时返回的 `card_schedule_revision`。revision 用于发现 Card 被其他写操作修改；正常墙钟时间流逝不使 revision 失效，后端以实际 `rated_at` 重新计算并返回最终 schedule。Rating 响应包含 Attempt Rating 和 Card 最终 type/queue/due/FSRS 摘要，不包含 next Card。

## 幂等

flip 与 Rating 请求都必须携带前端生成的 UUIDv7 `Idempotency-Key`：

- 相同 key、相同 payload 返回第一次操作的结果；
- 相同 key、不同 payload 返回 `409 IDEMPOTENCY_KEY_REUSED`；
- 同一 Attempt 重复提交相同 Rating 返回已存在的 Rating 结果，不再次推进 FSRS；
- 同一 Attempt 在未 Undo 时提交不同 Rating 返回 `409 RATING_ALREADY_SET`；
- Rating 应用时后端锁定 Card 并重新校验候选状态，过期时返回 `409 CARD_SCHEDULE_CONFLICT`。

## Undo

Undo 只作用于当前运行时 Queue 最近一次成功 Rating：

- 恢复 Card 评分前的 FSRS 与 due 状态；
- 恢复当前 Queue 顺序和该次 Rating 引发的 sibling bury 状态；
- 清空同一 Attempt 的 `rating` 和 `rated_at`，允许学习者重新选择；
- 保留 Attempt、输入快照、录音、ASR 和 AI Feedback，不创建新 Attempt；
- 一旦发生后续 Rating、运行时 Undo 上下文丢失或服务上下文失效，返回 `409 UNDO_NOT_AVAILABLE`。

Undo 前状态只保存在当前 Review service/Redis 的短期上下文中，不向 Attempt 持久化 FSRS before/after snapshot。

## 已冻结边界

- 输入要求属于 Card Template，不属于全局 Review 页面。
- 无 ASR/AI 需求的 Attempt 将对应 processing status 直接设为 `skipped`，且不创建相应 Outbox 行。
- 一个 Collection 只有一个活跃运行时 Queue；它可以从 Card 状态重建，不形成持久化 Study Session。
