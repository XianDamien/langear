# Anki 非 AI 调度语义源码核对

日期：2026-08-27

用途：为 LanGear v1 非 AI 后端 contract 和 Feng 的实现提供源码依据，不作为 Anki 文件格式兼容规格。

## 证据边界

- 主来源：本地 Anki 仓库 `/Users/damien/Desktop/LanProject/anki`。
- 固定提交：`2d44d4d6bc486803f9236033ad840df203c87036`，提交时间 2026-03-18，标题 `chore(deps): bumps rollup from 4.44.1 to 4.59.0 (#4615)`。
- 本文引用的源码均使用 `git show HEAD:<path>` 读取，行号对应上述提交。Anki 工作区存在大量 file-mode dirty 记录，但本次涉及文件的内容 diff 为 0；未把工作区未提交状态作为证据。
- 该提交锁定 `fsrs` crate `5.2.0`：[Cargo.lock](/Users/damien/Desktop/LanProject/anki/Cargo.lock:2235)。LanGear 仍需在依赖清单中独立锁定自己的调度库和版本，不能把本文的 Anki commit 当作运行时依赖锁。

## 结论摘要

LanGear 可以复用 Anki 的 `type + queue` 状态机、四档 Rating、学习/重学步骤、分层限额、sibling bury 和可重建运行时队列原则，但不应照搬 Anki 的 SQLite 存储编码。

最重要的差异是：Anki 的 `due` 同时承担新卡位置、秒级时间戳、学习日和 Filtered Deck 排序位置；LanGear 已明确拆为 `new_position`、`due_at`、`due_day`，并让 Filtered Deck 排序只存在于运行时队列。这是有意的领域模型差异，不是兼容缺陷。

## 1. Card type、queue 与 due

Anki 的 Card 长期阶段为 `New=0`、`Learn=1`、`Review=2`、`Relearn=3`；当前队列为 `New=0`、`Learn=1`、`Review=2`、`DayLearn=3`、`PreviewRepeat=4`、`Suspended=-1`、`SchedBuried=-2`、`UserBuried=-3`：[card/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/card/mod.rs:38)。

`type` 和 `queue` 是两个维度。`Relearn` 只是一种 type；实际 queue 根据到期时间是秒级还是学习日，落入 `Learn` 或 `DayLearn`。从 type 恢复 queue 的映射在 [filtered/card.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/filtered/card.rs:10) 中是显式实现。

Anki 单个 `due: i32` 的单位随 queue 改变：

| queue | Anki `due` 语义 |
| --- | --- |
| `New` | 展示顺序位置 |
| `Learn` | Unix 秒级时间戳 |
| `Review` / `DayLearn` | Collection 创建以来的学习日编号 |
| `PreviewRepeat` | Unix 秒级时间戳 |

这些语义直接写在 enum 注释中：[card/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/card/mod.rs:47)。Card 还持久化 `interval`、`reps`、`lapses`、`remaining_steps`、`original_due`、`original_deck_id` 和 FSRS memory state：[card/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/card/mod.rs:75)。

应用状态时，Anki 会把秒级 learning 写成 `queue=Learn, due=Unix timestamp`，跨日 learning 写成 `queue=DayLearn, due=today+days`：[answering/learning.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/answering/learning.rs:40)。Relearning 使用同一 queue 编码：[answering/relearning.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/answering/relearning.rs:12)。Review 则写成 `queue=Review, due=today+scheduled_days`：[answering/review.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/answering/review.rs:11)。

LanGear 已确认的对应关系是正确的：API 保留字符串 `type/queue` 语义，但数据库分别保存 `new_position`、UTC `due_at` 和 Collection 学习日 `due_day`。暂停或埋藏只切换 queue，不覆盖这些正式到期字段。

## 2. Learning 与 relearning 转换

Anki 把 New 当成“尚未完成第一次 learning 的卡”来生成四个候选状态：[states/normal.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/states/normal.rs:40)。四个按钮的候选状态由调度器一次性产生，而不是由前端推算：[scheduler.proto](/Users/damien/Desktop/LanProject/anki/proto/anki/scheduler.proto:264)。

Learning 的基本转换为：

- `Again` 回到第一步并重置剩余步数；存在 learning step 时继续 Learning：[states/learning.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/states/learning.rs:39)。
- `Hard` 留在当前学习步；第一步的 Hard 间隔取第一、第二步均值，只有一步时为第一步的 1.5 倍且最多多一天：[states/steps.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/states/steps.rs:38)。
- `Good` 前进到下一步；没有下一步时毕业为 Review：[states/learning.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/states/learning.rs:133)。
- `Easy` 直接毕业为 Review：[states/learning.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/states/learning.rs:180)。

Review 的 `Again` 增加一次 lapse，并在配置了 relearning step 时进入 Relearning；`Hard/Good/Easy` 仍是 Review：[states/review.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/states/review.rs:63)。Relearning 内部同时保留 Learning 子状态和 Review 子状态，完成步骤后回到 Review：[states/relearning.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/states/relearning.rs:12)。

对 LanGear 已确认的单步 `[15m]` 配置，确定性的外层行为是：

- New/Learning/Relearning 的 `Again` 为 15 分钟步骤；
- 单步的 `Hard` 基准为 22.5 分钟，再按 Anki 的 learning fuzz 规则处理；
- `Good` 因没有下一步而毕业到 Review；
- `Easy` 直接毕业到 Review；
- Review 的 `Again` 进入 15 分钟 Relearning。

Anki 对 learning 秒数最多增加 25%、且不超过 5 分钟的确定性 fuzz；无 seed 时不 fuzz：[answering/learning.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/answering/learning.rs:77)。因此 UI 显示值必须来自后端候选状态，不能把 `[15m]` 解释成四个按钮都显示 15 分钟。

Anki 当前默认 steps 是 learning `[1m, 10m]`、relearning `[10m]`：[deckconfig/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/deckconfig/mod.rs:88)。LanGear 使用 `[15m]` 和 `[15m]` 是明确的产品差异。

## 3. 运行时队列与重排

Anki 的运行时 `CardQueues` 保存在 Collection 进程状态中，分为：

- `main`：New、Review、跨日 Learning；
- `intraday_learning`：秒级 Learning，按到期时间排序。

结构定义见 [queue/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/mod.rs:29)。队列缺失时才从 Card 持久化状态重建：[queue/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/mod.rs:245)。跨日 Learning、Review 和 New 会按配置先分别排序，再合并成 main；秒级 Learning 独立按 due 排序：[queue/builder/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/builder/mod.rs:184)。

实际出队顺序是“已经到期的 intraday Learning -> main -> learn-ahead 窗口内的 intraday Learning”：[queue/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/mod.rs:149)。当前时间推进后，新的秒级 Learning 会进入可见范围；刚评分且仍在当天 Learning 的 Card 会按 due 二分插回队列：[queue/learning.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/learning.rs:36)。为避免队列已空时立即重复同一张卡，Anki 甚至可能只调整运行时 entry 的 due，把它插到下一张之后：[queue/learning.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/learning.rs:93)。

所以“Anki 是否会突然重排”的精确答案是：main build 的相对顺序通常保持，但到期 Learning 可以动态进入前方；会影响队列事实的其他操作会清空并重建队列；跨学习日也会丢弃旧队列并自动 unbury：[queue/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/mod.rs:198)。随机新卡排序使用 card/note ID 加当天 salt 的稳定 hash，源码也明确承认重建后 Learning 混排仍可能改变下一张卡：[queue/builder/sorting.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/builder/sorting.rs:63)。

LanGear 的“build 后主顺序稳定，intraday Learning 可按 `due_at` 动态插回”与这一原则一致。不同之处是 LanGear 用显式 `queue_id` 连接 Redis/多 Web 进程，并规定一个 Collection 同时只有一个活跃 Queue；Anki 的队列只是单个 Collection 实例内的对象，没有对应的跨请求 `queue_id` contract。

## 4. Filtered Deck

### Anki 的实际实现

Anki Filtered Deck 每个 search term 保存 `search`、`limit`、`order`，完整排序枚举有 11 种：[decks.proto](/Users/damien/Desktop/LanProject/anki/proto/anki/decks.proto:91)。构建时最多消费前两个 term，按 term 顺序搜索，并排除 suspended、buried 和已经在 filtered deck 的 Card：[filtered/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/filtered/mod.rs:103)。

排序是在 rebuild 查询时计算的，随后被物化到 Card：

1. Anki 按指定 SQL order 和 limit 查询 Card；相同排序键使用 `fnvhash(card.id, card.mod)` 作为稳定 tie-breaker：[storage/card/filtered.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/storage/card/filtered.rs:9)。
2. 从 `-100000` 开始依次分配 position：[filtered/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/filtered/mod.rs:103)。
3. Card 的当前 `deck_id` 改为 Filtered Deck，原 `deck_id` 写入 `original_deck_id`，原 `due` 写入 `original_due`，当前 `due` 改为 position：[filtered/card.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/filtered/card.rs:27)。
4. Empty/rebuild 前先把 Card 返回原 Deck，恢复原 due 和由 type 推导的 queue：[filtered/card.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/filtered/card.rs:64)。

Anki 的 `Added` 实际按 `note.id, card.template_ord`，不是 Card 自身创建时间：[storage/card/filtered.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/storage/card/filtered.rs:24)。Retrievability 排序调用当前时间、原 due/当前 due 和 FSRS memory state 动态计算：[storage/card/filtered.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/storage/card/filtered.rs:32)。缺少 FSRS memory state 时函数返回 SQL `NULL`：[storage/sqlite.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/storage/sqlite.rs:312)，而该排序 SQL 没有显式指定 `NULLS LAST`。

### LanGear 的明确差异

LanGear v1 有意不复刻上面的物化编码：

- 只持久化 `original_deck_id`，正式 `new_position/due_at/due_day` 不被 Filtered Deck 覆盖；
- rebuild 生成运行时有序 Card ID，不把排序 position 写回 Card；
- 服务重启或显式 rebuild 会按当前状态重新算排序；
- 只支持 `added`、`retrievability_ascending`、`retrievability_descending`；
- `added` 明确定义为 `card.created_at, card.id`，与 Anki 的 `note.id, template_ord` 不同；
- 无 FSRS state 的 Card 显式放到有状态 Card 之后，避免依赖数据库的 NULL 默认顺序；
- 固定 `reschedule=true`，不实现 Anki Preview 和 `PreviewRepeat`。

这套差异减少了 Card 字段的多单位写入，也避免一次 rebuild 更新大量正式调度字段。代价是运行时队列丢失后顺序可因时间和 retrievability 变化而重算；这是当前 contract 已接受的行为。

Anki 最多两个 search term。LanGear v1 已据此固定 `search_terms[]` 上限为 2，避免无界查询组合。

## 5. Sibling bury 与 suspend

Anki 区分 `SchedBuried`、`UserBuried` 和 `Suspended`。手动 bury 不会覆盖已经 suspended 的 Card；unbury/unsuspend 时按 type 恢复 queue：[bury_and_suspend.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/bury_and_suspend.rs:16)。两种 buried queue 都会在学习日 rollover 自动恢复，Suspended 不会：[bury_and_suspend.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/bury_and_suspend.rs:31)。这与 LanGear 当前 `buried_sibling`、`buried_user` 和 `suspended` 生命周期一致。

Sibling 是同一 Note 下、排除当前 Card 的其他 Card。Anki 在评分事务中根据 Card 所在原 Deck 的配置把符合 queue 类型的 siblings 持久化为 `SchedBuried`：[bury_and_suspend.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/bury_and_suspend.rs:132)。构建队列时还会提前识别相同 Note，避免把后续应被 bury 的 sibling 放进运行时队列：[queue/builder/gathering.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/builder/gathering.rs:135)。

Anki 此提交的底层默认配置是 `bury_new=false`、`bury_reviews=false`、`bury_interday_learning=false`：[deckconfig/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/deckconfig/mod.rs:40)。LanGear 统一默认 sibling burying 为 true，是明确产品差异；实现时应定义它覆盖 New、Review 和 Day Learning 三类 sibling，而不是只覆盖 Review。

Anki 还支持 leech 阈值触发自动 suspend，但默认 action 是只打 tag：[deckconfig/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/deckconfig/mod.rs:62)。LanGear v1 contract 未定义 leech 识别和自动 suspend，Feng 不应从“沿用 Anki suspend”推导出该功能。

## 6. 分层 Deck 每日限额

Anki 分别维护 New 和 Review 剩余额度。Deck 自身当日 override 优先于普通 deck/config limit，再减去当天已学习计数；默认情况下 New 还会被剩余 Review 额度限制：[decks/limits.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/decks/limits.rs:25)。

限额树构建时，child 的额度先 cap 到 parent；每收集一张 Card，会同时递减该 Deck 和所有已纳入树的 ancestors；某节点归零后继续 cap 整个后代：[decks/limits.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/decks/limits.rs:316)。队列 gather 同时检查 root 和当前 child 的剩余额度：[queue/builder/gathering.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/builder/gathering.rs:35)。因此“父级限制整个子树、子级限制本地、有效容量取沿途最小值”准确描述了限额树内部语义。

但 Anki 有一个范围开关：当直接学习 child 时，只有 `apply_all_parent_limits=true` 才把该 child 之上的 ancestors 加入限额树；默认值为 false：[queue/builder/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/builder/mod.rs:126)。LanGear 当前 contract 没有该开关，规定始终沿完整祖先路径取最小值，这是有意简化。

Anki 默认 `new_cards_ignore_review_limit=false`，因此 Review 余额会进一步 cap New；也可以配置 New 忽略 Review limit：[decks/limits.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/decks/limits.rs:98)。LanGear v1 已固定沿用默认行为：Review 余额进一步 cap New，且不暴露忽略开关。

Anki 用 Deck 上的当日计数更新额度；评分时同步更新，Undo 时恢复。LanGear 则已决定从当日已 Rating 的 Attempt 推导用量，Undo 清空 Rating 后不再计入。这是符合 LanGear Attempt 事实边界的明确差异。

## 7. Undo 与幂等

Anki 的 AnswerCard 在数据库事务中完成，并校验客户端提交的 current state 仍与数据库计算结果相等；状态变化则拒绝回答：[answering/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/answering/mod.rs:308)。这个 optimistic state check 能阻止旧状态再次应用，但 Anki 的 CardAnswer 请求没有 `Idempotency-Key` 字段：[scheduler.proto](/Users/damien/Desktop/LanProject/anki/proto/anki/scheduler.proto:272)，因此它不是 LanGear 所需的可重放 HTTP 幂等协议。

Anki 通用 UndoManager 在进程内保留最多 30 个 operation，支持 redo；新普通操作会清空 redo 栈：[undo/mod.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/undo/mod.rs:15)。一次 Answer Undo 会恢复 Card、删除对应 revlog、恢复 Deck 当日计数、恢复 sibling bury/leech tag，并尽可能把原 queue entry 放回队头；源码测试覆盖了这组效果：[queue/undo.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/undo.rs:99)。队列若已重建，Undo 会使旧 queue context 失效并依靠后续重建，而不是把旧运行时队列强行拼回：[queue/undo.rs](/Users/damien/Desktop/LanProject/anki/rslib/src/scheduler/queue/undo.rs:30)。

LanGear 的边界更窄也更适合服务端：只允许当前 Queue 最近一次 Rating 的 Undo，不提供通用 redo；恢复 Card FSRS/due/queue 和 sibling bury，清空 Attempt Rating，但保留 Attempt 输入、媒体和处理结果。与此同时，LanGear 额外持久化 IdempotencyRecord，确保 Web 进程或 Redis 丢失后重试也不会重复创建 Attempt 或推进 FSRS。这两项都是相对 Anki 的明确差异。

## 8. 给非 AI 后端实现的直接约束

1. `type` 决定长期阶段，`queue` 决定当前可调度状态；不要把 `relearning` 加成一个 queue。
2. 让调度库返回四个候选状态和显示间隔；前端不能自行推算，也不能回传 FSRS state。
3. Card 正式 due 字段永远不承担 Filtered Deck 排序 position；Filtered Deck rebuild 只写 `original_deck_id` 和运行时队列。
4. runtime queue 必须允许到期的 `due_at` Learning 动态插到 main 前方；“主顺序稳定”不等于整个 next 序列永不变化。
5. sibling bury 要在队列构建阶段去重 sibling，并在 Rating 事务中持久化 `buried_sibling`，Undo 同事务语义恢复。
6. 每日限额对当前 Deck 和 ancestors 串行扣减；LanGear 不提供 Anki 的 `apply_all_parent_limits` 开关。
7. 不要照搬 Anki 的 revlog、通用 Undo 栈或无幂等的 AnswerCard API；以 LanGear Attempt、IdempotencyRecord 和最近一次 Rating Undo contract 为准。

## Contract 补齐结果

- `search_terms[]` 最大数量固定为 2。
- New 受剩余 Review limit 额外 cap，v1 不提供忽略开关。

本次核对范围内没有发现会阻塞 Feng 开始 PostgreSQL schema、Card 状态机、运行时 Queue、Filtered Deck、bury/suspend 和 Undo 基础实现的非 AI contract 缺口。
