# LanGear v1 Card 调度契约

状态：已确认，2026-08-27

LanGear v1 沿用 Anki 的 Card `type`、`queue` 和 FSRS 调度语义。调度间隔、模糊化、短期步骤和 memory state 由锁定版本的成熟 FSRS 实现计算；业务代码不得复制或改写 FSRS 公式。

行为参考固定为本地 Anki commit `2d44d4d6bc486803f9236033ad840df203c87036`；源码证据与 LanGear 的有意差异见 `2026-08-anki-source-research.zh-CN.md`。该 commit 使用的 `fsrs` crate 版本不是 LanGear 的运行时依赖声明；LanGear 仍须在 backend lockfile 中固定所选成熟 FSRS 库和版本。

## 默认配置

Collection 提供调度默认值，Standard Deck 可以覆盖允许的配置。配置变化只影响之后发生的 Rating，不追溯改写历史 Attempt。

```text
learning_steps = [15 minutes]
relearning_steps = [15 minutes]
desired_retention = 0.90
maximum_review_interval = 36500 days
sibling_burying = true
study_day_rollover_hour = 4
new_limit = 20
review_limit = 200
new_card_gather_order = random_cards
new_card_sort_order = order_gathered
new_review_order = after_reviews
interday_learning_review_order = before_reviews
review_sort_order = retrievability_descending
```

`study_day_rollover_hour` 是 Collection 级规则，v1 固定为本地 04:00，不允许 Deck 覆盖。Daily limits、`due_day` 和 buried Card 自动恢复都使用同一个 Study Day。

## Standard Deck 高级设置

Standard Deck 可以覆盖以下配置：

```text
new_limit
review_limit
desired_retention
sibling_burying
new_card_gather_order
new_card_sort_order
new_review_order
interday_learning_review_order
review_sort_order
```

`learning_steps`、`relearning_steps`、`maximum_review_interval` 和 `study_day_rollover_hour` 在 v1 保持 Collection 级配置，Deck 不能覆盖。Filtered Deck 使用 Card 原 Standard Deck 的有效调度配置和自身 build sort，不保存上述 Standard Deck 顺序覆盖。

除每日限额外，可覆盖字段使用逐项 nullable override：当前 Deck 有显式值时使用当前值，否则使用最近祖先 Standard Deck 的显式值，最后回退 Collection 默认值。“恢复默认”是清空 override，不是复制当前默认值。每日限额仍按层级 capacity 规则执行：各 Deck 的本地 limit 与所有祖先/Collection limit 共同约束子树，不能被子 Deck 的较大值放宽。

五个 Display Order 设置保留为高级设置，API 使用以下字符串枚举：

### New Card Gather Order

决定先从哪些 Deck/Note 收集 New Card：

```text
deck
deck_then_random_notes
lowest_position
highest_position
random_notes
random_cards
```

默认 `random_cards`。随机顺序使用 Collection、Study Day 和 Card ID 生成的稳定 seed；同一 Queue build 内稳定，rebuild 或跨 Study Day 可以重排。

### New Card Sort Order

决定 gather 后 New Card 的二次排序：

```text
template
order_gathered
template_then_random
random_note_then_template
random_card
```

默认 `order_gathered`，即不改变 `random_cards` gather 得到的顺序。

### New/Review Order

决定 New Card 与 Review Card 的混排位置：

```text
mix_with_reviews
before_reviews
after_reviews
```

默认 `after_reviews`。

### Interday Learning/Review Order

决定 `day_learning` Card 相对 Review Card 的位置：

```text
mix_with_reviews
before_reviews
after_reviews
```

默认 `before_reviews`。已经到期的 intraday `learning` Card 仍优先于此主队列设置，不受该选项控制。

### Review Sort Order

```text
due_day
due_day_then_deck
deck_then_due_day
interval_ascending
interval_descending
retrievability_ascending
retrievability_descending
relative_overdueness
random
added
reverse_added
```

默认 `retrievability_descending`，即当前计算的 retrievability 较高、最可能记住的 Review Card 先出现。相同排序键使用 Card ID 的稳定 tie-breaker。LanGear 不保存 Anki SM-2 ease factor，因此 v1 不提供 `ease_ascending/ease_descending`。

Display Order 修改只改变之后构建的运行时 Queue，不改写 Card type/queue/due/FSRS 或历史 Attempt。更新配置后当前 Collection 的活跃 `queue_id` 失效，下一次访问按新配置 rebuild。

## Type 与 Queue

`type` 表示 Card 的长期学习阶段：

```text
new = 0
learning = 1
review = 2
relearning = 3
```

`queue` 表示 Card 当前进入的调度队列：

```text
new = 0
learning = 1
review = 2
day_learning = 3
suspended = -1
buried_sibling = -2
buried_user = -3
```

API 使用上述字符串值，不暴露数值编码。`relearning` 是 `type`，不是 queue；Relearning Card 根据下次时间使用 `learning` 或 `day_learning` queue。v1 Filtered Deck 始终参与正式重新调度，因此不提供 Anki 的 `preview_repeat` queue。

## Due 字段不变量

LanGear 不复用 Anki 单个 `due` 字段的多单位编码：

| 当前 queue | 有效调度字段 |
| --- | --- |
| `new` | `new_position` |
| `learning` | `due_at`，UTC 时间点 |
| `day_learning` | `due_day`，Collection 时区下的学习日编号 |
| `review` | `due_day`，Collection 时区下的学习日编号 |
| suspended/buried | 保留暂停或埋藏前的调度字段，不改变正式到期信息 |

Study Day 在 Collection IANA timezone 下从本地 04:00 开始；早于 04:00 的本地时间仍属于前一学习日。`due_day` 使用该学习日起始日期的明确日期序号，不复用 Anki 单个 `due` 字段的多单位编码。恢复 suspended/buried Card 时，根据 `type` 和已保留的 due 字段恢复其有效 queue。数据库约束必须拒绝会造成歧义的字段组合。

## Rating 转换

所有阶段都提供 `again`、`hard`、`good`、`easy` 四个 Rating。状态转换遵循锁定版本的 Anki/FSRS 调度器输出，而不是由路由或前端写死：

```text
new -> learning 或 review
learning -> learning/day_learning 或 review
review + again -> relearning（queue 为 learning/day_learning）
review + hard/good/easy -> review
relearning -> learning/day_learning 或 review
```

单个 15 分钟 step 不代表四个按钮都固定显示 15 分钟。各按钮的预计间隔由调度器结合当前 Card、Rating、FSRS memory state、配置、时间和 fuzz 计算。

## FSRS 状态

Card 保存当前调度事实，至少包括：

```text
fsrs_state.stability
fsrs_state.difficulty
interval_days
desired_retention
last_reviewed_at
reps
lapses
learning_steps_remaining
fsrs_algorithm_version
fsrs_config_version
```

若所选 FSRS 版本需要 `decay` 等额外参数，它们必须进入版本化的 typed state，不能放入无约束的 `custom_data`。新 Card 的 `fsrs_state` 为空，第一次 Rating 后由调度器生成。

## Rating Options API

获取当前 Card 时，后端同时返回四个由同一调度器计算的候选结果，至少包含：

```json
{
  "rating": "good",
  "display_interval": "3d",
  "next_type": "review",
  "next_queue": "review",
  "due_at": null,
  "due_day": 2142
}
```

前端只展示候选结果并提交选中的 Rating，不能提交或覆盖计算后的 FSRS state。Rating API 在持有 Card 行锁的事务中重新校验当前状态并应用结果；候选状态过期时返回 `409 CARD_SCHEDULE_CONFLICT`。

Card 保存单调递增的 `schedule_revision`。Rating options 响应携带当前 revision，Rating 请求必须原样回传。Rating、Undo、Suspend/Unsuspend、Bury/Unbury 和其他调度状态修改都递增 revision；正常墙钟时间流逝不改变 revision，Rating 时仍以实际 `rated_at` 重新计算最终间隔。

## Filtered Deck、Suspend 与 Bury

- v1 Filtered Deck 只支持影响正式调度的复习，等价于固定 `reschedule=true`；API 不暴露 Preview 开关。
- Filtered Deck 最多包含两个 search term，按 term 顺序查询、排序和截取。
- `suspended` 持续到用户手动恢复。
- `buried_user` 持续到用户手动恢复或下一个 Collection 学习日自动解除。
- `buried_sibling` 在下一个 Collection 学习日自动解除。
- 暂停和埋藏不修改 Card 的 FSRS memory state 或正式 due 字段。
- 默认 sibling bury 覆盖同 Note 的 New、Review 和 Day Learning sibling；不埋藏 intraday Learning，也不覆盖已 suspended/user-buried 状态。
- v1 不实现 leech 阈值和自动 suspend。

## 每日限额

New 和 Review 分别应用当前 Deck 与完整 ancestor 路径的限额，沿途有效 capacity 取最小值。New 在此基础上再受剩余 Review capacity 限制；v1 固定等价于 Anki 默认 `new_cards_ignore_review_limit=false`，不提供配置开关。当天用量从已 Rating Attempt 推导，Undo 清空 Rating 后释放对应额度。
