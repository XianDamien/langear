# LanGear v1 非 AI 核心契约

状态：已确认，2026-08-27

本文是 Feng 实现 PostgreSQL、Collection 隔离、认证、FSRS、Review 运行时、Attempt 持久化、媒体生命周期、Transactional Outbox 和部署的主 contract。本文不定义 ASR provider、AI prompt、AI evaluator 或 AI Feedback 的 mode-specific schema；这些内容见 `2026-08-attempt-processing-contract.zh-CN.md`。

## 1. 不可变边界

### 身份、时间和环境

- User、Session、Collection、Deck、Note、NoteType、CardTemplate、Card、Attempt、MediaAsset、MediaReference、TaskOutbox、IdempotencyRecord 的核心 ID 均由应用生成 UUIDv7。
- 所有绝对时间使用 PostgreSQL `timestamptz`，写入 UTC。Collection 保存一个 IANA timezone，用于学习日边界和 `due_day` 计算。
- 开发、Staging、Production 使用独立 PostgreSQL、Redis、Celery worker 和 OSS namespace。生产 schema 通过显式 release job 重建/迁移，不在 Web 或 Worker 启动时自动执行。

### Collection 隔离

- 一个 User 恰好拥有一个 Collection；`collections.owner_user_id` 唯一且非 Library Collection 的 owner 不为空。
- 系统 Library 是唯一的只读 Collection；普通 API 不能修改它。
- 所有用户数据表带 `collection_id`。Note、Card、Deck、Attempt 和私有 MediaAsset 的跨 Collection 关系由服务端 scope 和 PostgreSQL 复合外键共同阻止。
- 访问不存在资源和跨 Collection 资源统一返回 `404`，不泄露资源是否存在。

## 2. 持久化模型

| 实体 | 责任 | 必须满足 |
| --- | --- | --- |
| Collection | 所有权、timezone、默认调度配置 | User Collection 唯一；Library 只读 |
| Deck | Card 容器和层级；Standard 或 Filtered | Note 不属于 Deck；父子关系不能跨 Collection |
| NoteType | Note 字段、Card Template 和渲染规则 | v1 仅 Vocabulary、Sentence，系统定义且只读 |
| CardTemplate | 一个练习方向的 prompt/answer/input 规则 | `ord` 在 NoteType 内稳定；模板不能隐式拥有 Deck |
| Note | 可编辑内容和 Library 导入 guid | 可有零张 Card；字段更新受 revision 乐观锁保护 |
| Card | 一个可复习单位、当前 Deck 和 FSRS 状态 | 恰好属于一个 Note、Template、Deck；可独立移动/删除 |
| Attempt | 一次 flip 提交的不可变练习快照和 Rating | 不等于试录；Card 删除时级联删除 |
| MediaAsset | OSS 对象身份、scope、引用和生命周期 | object key 不复用；私有媒体不能跨 Collection 读取 |
| MediaReference | Note field 对媒体的显式引用 | 私有引用同 Collection；只读 Library shared 允许跨 Collection |
| TaskOutbox | 可靠投递任务意图 | 与 Attempt 在同一事务提交；按 aggregate/task 幂等 |
| IdempotencyRecord | 跨进程保存写请求的 key、payload hash 和结果 | 不能只放 Redis；过期时间由运维配置 |
| Session | User 的可撤销登录状态 | 只存 opaque token hash；支持绝对/空闲过期 |

核心关系：

```text
User 1──1 Collection
Collection 1──* Deck ──* Card *──1 Note
NoteType 1──* CardTemplate ──* Card
Card 1──* Attempt
Attempt 0──1 private MediaAsset
Note 1──* MediaReference *──1 MediaAsset
```

Note 不保存 `deck_id`。创建 Note 时可以指定目标 Standard Deck，仅用于首次生成 Card；之后每张 Card 独立拥有并可移动到其他 Deck。删除全部 Card 不删除 Note。

### 必须由 PostgreSQL 保证的约束

- Collection 使用 `kind=user|library`；`kind=user` 必须有 owner，`kind=library` 必须没有 owner。`owner_user_id` 唯一，并通过部分唯一索引保证系统只有一个 Library Collection。
- 每张表为自身提供 `UNIQUE(collection_id, id)` 候选键；所有用户实体关系使用包含 `collection_id` 的复合外键。
- `UNIQUE(collection_id, note_id, card_template_id)` 保证一个 Note 的一个 Template 最多生成一张 Card。
- Card 的 Template 必须属于 Note 的 NoteType；可通过冗余 `note_type_id` 加复合外键实现，不能只依赖前端传参。
- Attempt 的 `(collection_id, card_id, note_id, card_template_id)` 必须整体引用同一张 Card，避免快照元数据指向彼此无关的实体。
- Standard Deck 的同级名称唯一；根 Deck 单独使用部分唯一索引。父级必须在同一 Collection，移动 Deck 时服务端用递归查询拒绝自身父级和后代父级，返回 `422 DECK_HIERARCHY_CYCLE`。
- Filtered Deck 不参与 Standard Deck 层级：不能拥有 parent/child；Card 只有在 `deck.kind=filtered` 时才能设置 `original_deck_id`，且 original 必须指向同 Collection 的 Standard Deck。
- `new_position` 从 Collection 内的原子递增值分配，不能使用 `MAX(position)+1`。批量导入按 manifest 顺序连续分配。

## 3. Note、Card 和结构操作

### 普通编辑

- `notes.revision` 是整数乐观锁。更新必须携带客户端已读 revision；revision 不匹配返回 `409 NOTE_REVISION_CONFLICT`，details 至少包含当前 revision。
- 必填字段不能被清空；字段校验在写入前完成。普通编辑只改变未来 Card 渲染，不改写历史 Attempt 快照。
- Note 的 `guid` 在 Collection 内唯一。Library 复制和导入保留 guid；重复导入保留本地 fields、tags、Card 所在 Deck，只补缺失 Card。

### NoteType 切换

NoteType 切换是显式的破坏性结构操作：接口先返回受影响的 Card/Attempt 数量，确认后在一个事务中删除旧 Card 及其 Attempts，再按新 NoteType 的有效模板生成新 Card。旧 FSRS、Rating 和历史 Attempt 不迁移。

### Card 生成和删除

- v1 每个有效 Card Template 默认生成一张持久化 Card；缺少模板 required fields 时不生成，并在 API 返回可修复原因。
- 删除一张 Card 只删除该 Card 和其 Attempts，保留 Note、同 Note 的 sibling Card 和其他 Deck 中的 Card。
- 删除 Note 会删除该 Note 的全部 Cards、Attempts 以及不再被引用的私有媒体；删除前必须显式确认影响范围。

所有破坏性接口分为 impact preview 和 execute 两步。preview 返回受影响实体数与短期 `confirmation_token`；token 绑定 Collection、资源 ID、资源 revision/更新时间和操作类型。execute 必须重新校验，影响范围变化时返回 `409 DELETION_IMPACT_CHANGED`，不能按过期预览继续删除。

## 4. Card 调度事实

调度器使用锁定版本的成熟 FSRS 实现；业务代码不复制 FSRS 公式，也不允许客户端提交 FSRS state。

### Type 与 Queue

API 只暴露字符串：

```text
type:  new | learning | review | relearning
queue: new | learning | day_learning | review |
       suspended | buried_sibling | buried_user
```

`relearning` 是 type，不是 queue。Relearning Card 使用 `learning` 或 `day_learning` queue。暂停和埋藏不改变 FSRS memory state 或正式 due。

### Due 不变量

| queue | 有效字段 | 单位 |
| --- | --- | --- |
| `new` | `new_position` | Collection 内新卡顺序整数 |
| `learning` | `due_at` | UTC 时间点 |
| `day_learning` | `due_day` | Collection 学习日整数 |
| `review` | `due_day` | Collection 学习日整数 |
| suspended/buried | 保留原 type 对应字段 | 不改变正式 due |

`due_day` 定义为 Collection timezone 下的本地日期距 `1970-01-01` 的天数；“当前学习日”使用同一公式。这样值不依赖部署时区，也不因进程重启改变。数据库约束拒绝同时存在互相矛盾的 due 字段。Filtered Deck 不覆盖 `new_position`、`due_at` 或 `due_day`。

### 默认配置和 Rating

Collection 默认值：

```text
learning_steps = [15 minutes]
relearning_steps = [15 minutes]
desired_retention = 0.90
maximum_review_interval = 36500 days
sibling_burying = true
```

Standard Deck 可覆盖允许的配置；配置变化只影响之后发生的 Rating。每张 Card 返回由同一调度器计算的 Again/Hard/Good/Easy 预计间隔。Rating API 在事务中锁定 Card、重新计算并写入 Attempt Rating 与 Card FSRS；候选已过期返回 `409 CARD_SCHEDULE_CONFLICT`。

Card 保存单调递增的 `schedule_revision`。Rating、Undo、Suspend/Unsuspend、Bury/Unbury 和任何调度字段修改都递增它；Undo 恢复业务状态但不回退 revision。前端只能回传已读 revision，不能指定新值。

状态转换遵循 FSRS/Anki 语义：

```text
new -> learning 或 review
learning -> learning/day_learning 或 review
review + again -> relearning（queue 为 learning/day_learning）
review + hard/good/easy -> review
relearning -> learning/day_learning 或 review
```

## 5. Review 运行时

- 每个 Collection 同一时刻只有一个活跃的临时 `queue_id`。创建或显式 rebuild 会替换旧 Queue。
- Queue 只保存 Card ID 顺序、当前游标、flip 状态和最近一次 Rating 的 Undo 上下文；不保存学习事实，不是持久化 Study Session。
- `next` 为本次 Card 出队实例生成 UUIDv7 `review_token`；相同 Card 以后因 learning step 再次出现时获得新 token。flip 必须同时携带 token，Attempt 持久化该 token，并以 `(collection_id, review_token)` 唯一，防止客户端换 Idempotency-Key 后为同一次出队创建第二条 Attempt。
- `next`、`flip`、`rating`、`undo` 都携带 `queue_id`。Queue 过期、被替换或服务重启后返回 `409 QUEUE_EXPIRED`，客户端创建新 Queue。
- Queue 丢失时按 Card 持久化 type/queue/due/FSRS 重建；重建不会生成额外 Attempt 或改变调度事实。
- 当前 Card 已 flip 但未 Rating 时，主队列不推进。Rating 响应不夹带下一张 Card；Rating 成功后客户端再调用 `next`。
- `flip` 和 `rating` 必须携带前端生成的 UUIDv7 `Idempotency-Key`。同 key 同 payload 返回第一次结果；同 key 不同 payload 返回 `409 IDEMPOTENCY_KEY_REUSED`。
- 同一 Attempt 重复提交相同 Rating 不重复推进 FSRS；不同 Rating 返回 `409 RATING_ALREADY_SET`。
- Runtime Undo 只恢复最近一次 Rating 的 Card FSRS/due、Queue 顺序和 sibling bury，并清空同一 Attempt 的 Rating；保留输入、媒体和异步结果。服务上下文丢失返回 `409 UNDO_NOT_AVAILABLE`。

一个 Collection 最多有一条已 flip、未 Rating 的活跃 Attempt，由部分唯一索引保证。创建或重建 Queue 时若存在该 Attempt，必须先把它恢复为当前项并返回已翻面快照；不能选择另一张 Card。这样进程重启不会重复创建 Attempt，也不会靠绕过当前 Card 推进 Queue。

每日新卡/复习上限在查询和 Rating 时都校验。父 Deck 限制整个子树，子 Deck 限制本地 Card，有效容量取沿途最小值。

每日已用额度从当前 Collection 学习日内已 Rating 的 Attempt 推导，不依赖 Runtime Queue。Undo 清空 Rating 后，该次用量不再计入。Rating 事务需对 Collection + study day 的配额判定串行化，避免并发请求突破上限。

New 和 Review 先分别应用层级限额，再用剩余 Review capacity 对 New 做二次 cap；v1 固定 `new_cards_ignore_review_limit=false`，不暴露开关。Sibling bury 默认覆盖同 Note 的 New、Review 和 Day Learning Card；不埋藏 intraday Learning，不改变已 suspended/user-buried Card。v1 不实现 leech 阈值或自动 suspend。

## 6. Filtered Deck

- Filtered Deck 是临时 Deck；一张 Card 最多属于一个 Filtered Deck。
- 持久化 `original_deck_id`，不持久化 `filtered_position` 或 `original_due`；返回时恢复原 Deck，正式 due 字段从未被覆盖。
- v1 `search_terms[]` 最多两项，每项包含 `query`、`limit`、`sort_order`，按数组顺序执行，只支持：
  - `added`：`card.created_at ASC, card.id ASC`；
  - `retrievability_ascending`：当前 FSRS retrievability 升序；
  - `retrievability_descending`：当前 FSRS retrievability 降序。
- 没有 FSRS memory state 的 Card 在 retrievability 排序中排在有状态 Card 之后，并以 `added` 保持稳定。
- rebuild 按 term 顺序查询、排序、截取并生成运行时 Card ID 队列；本次 build 的主顺序稳定，intraday learning Card 可按 `due_at` 动态插回。服务重启或显式 rebuild 时重新计算。
- v1 始终 `reschedule=true`，不提供 Preview、`preview_repeat` 或 `reschedule=false`。
- 删除 Filtered Deck 前先在一个事务中归还全部 Card，再删除临时 Deck。归还失败时整个操作回滚。
- Filtered Deck 中的 Card 禁止直接移动；必须先 empty/return。删除 Standard Deck 子树时，`original_deck_id` 指向该子树的借出 Card 也属于影响范围：先归还，再与该子树的其他 Card 一起删除，不能留下悬空 original reference。

## 7. Attempt 的非 AI 部分

flip 只创建一条 Attempt。Attempt 必须保存：

- `card_id`、`note_id`、`card_template_id`、`collection_id`；
- 本次出队的 `review_token`；
- `input_type` 和原始 `input_snapshot`；
- 完整 `note_snapshot`、`front_snapshot`、`back_snapshot`、`answer_snapshot`；
- 最终录音 `media_asset_id`（可为空）；
- `rating`、`rated_at`、`previous_interval_days`、`scheduled_interval_days`、`review_kind`；
- rating 时使用的 FSRS、算法和配置版本；
- `created_at`、`updated_at`。

题面、答案和输入快照创建后不可变；Rating、ASR 和 AI 只能补写各自字段。预期 Rating 间隔只用于展示和审计，不允许客户端回传覆盖。

Attempt 与适用的 Outbox 行必须在同一个 PostgreSQL 事务中提交。Rating 同步写入 Attempt 和 Card；ASR/AI worker 只更新同一 Attempt，不创建 Attempt、不推进 FSRS。Worker 以 Attempt ID 幂等，重复投递不能产生重复业务事实。

### 写请求幂等记录

- flip 与 Rating 在业务事务内同时写入 IdempotencyRecord，保存 `collection_id`、operation、key、payload hash、resource ID、最小可重放响应和完成状态。
- `UNIQUE(collection_id, operation, key)` 防止并发双写；相同 key、相同 hash 返回记录结果，相同 key、不同 hash 返回 `409 IDEMPOTENCY_KEY_REUSED`。
- IdempotencyRecord 的生命周期必须长于客户端的最大重试窗口，因此服务重启、Queue 过期或 Redis 丢失后仍不能重复创建 Attempt 或推进 FSRS。
- Undo 不删除旧 Rating 的 IdempotencyRecord。旧请求重放只返回其已记录且标记为 superseded 的结果，不重新应用；Undo 后重新 Rating 必须使用新 key。

### Outbox 状态

TaskOutbox 至少包含 `pending|publishing|published|failed`、attempt aggregate ID、task type、尝试次数、next attempt time 和 publisher lease。Publisher 只有在 broker 确认接收后才标记 published；lease 超时的 publishing 行可被其他 Publisher 重新认领。`UNIQUE(attempt_id, task_type)` 保证一次 Attempt 的同类处理意图唯一；自动或人工重试复用同一行，不创建第二个业务任务。

## 8. Media 生命周期

- OSS object key 使用 UUIDv7/时间前缀生成且不可变；MediaAsset 保存 `scope=private|library_shared`、`collection_id`、`object_key`、媒体类型、checksum、大小和生命周期状态。
- pre-flip 录音是 private scope 且 lifecycle 为 temporary，可被后一次试录替换并按 TTL 清理；只有 flip 指定的最后录音可在事务中认领为 Attempt permanent asset。
- Library reference audio/image 属于 Library shared scope，用户读取时复用对象，不复制到用户私有 namespace；用户录音始终是 private scope。
- 删除 Card/Note 或导入事务回滚后，失去业务引用的私有对象进入延迟清理；清理任务必须可重试。硬删除依赖 PostgreSQL 备份/WAL/PITR 和 OSS 延迟窗口恢复。

Note 媒体引用不能只藏在 `notes.fields` JSONB 中。使用显式 MediaReference 保存 Note/field 与 MediaAsset 的关系：私有引用必须由复合外键约束为相同 Collection；唯一允许的跨 Collection 引用是指向系统 Library Collection 中 `library_shared` 资产的只读引用。MediaReference 必须携带并约束 asset scope，不能引用另一用户的 private 资产。Attempt 的最终录音使用直接的 `(collection_id, media_asset_id)` 复合外键，只允许同 Collection 的 private permanent 资产。

MediaAsset lifecycle 为 `temporary|permanent|pending_delete|deleted`。flip 的“提升”只在数据库中把既有 immutable object 由 temporary 认领为 permanent，不执行 OSS rename。引用归零后先进入 `pending_delete` 并写清理任务；OSS 删除成功后才标记 `deleted`，失败保持可重试。

## 9. JSON/ZIP 导入

- v1 只导入 LanGear JSON 和 ZIP；两者共用带 `schema_version` 的 `manifest.json`。不导入 User、Collection、Attempt、Rating、FSRS、Queue、Outbox 或运行历史。
- 只接受系统 Vocabulary/Sentence NoteType 和 Card Template key；不能通过文件创建或修改 NoteType/Template。
- 导入目标固定为当前用户 Collection。ZIP 内路径必须相对且不能包含 `..`；媒体先进入临时 namespace，解析、类型、大小和 checksum 全部通过后再认领。
- Deck、Note、Card 和 MediaAsset 引用在单一事务中写入；事务失败不留下部分业务数据，未认领临时媒体按 TTL 清理。
- manifest 中每个 Deck 也必须有稳定 `deck_guid`。目标 Deck 保存可空的 import identity，并以 `(collection_id, deck_guid)` 唯一；用户本地改名后重复导入仍映射到原 Deck，不靠名称重复创建层级。
- Note 按 `(collection_id, guid)` 幂等；已有 Note 保留本地 fields/tags/Deck，重复包只补缺失 Card。ZIP 媒体按 checksum 去重，但私有引用仍受 Collection scope 约束。

## 10. 认证与 Session

- v1 只支持 email/password。email 经 Unicode trim 和大小写规范化后以 `normalized_email` 唯一；原始展示 email 可另存。密码使用 Argon2id，参数进入版本化配置并在成功登录时按需 rehash。
- 注册 User 与其唯一 Collection、默认 Standard Deck 必须在同一事务完成；任何一步失败都不留下半初始化账号。
- Session 使用服务端持久化记录和高熵 opaque token。客户端 cookie 只保存 token；数据库只保存 token hash，不保存明文。登录和权限变化时轮换 token，登出、改密和封禁可立即撤销 Session。
- Cookie 在生产环境固定 `HttpOnly`、`Secure`、`SameSite=Lax`，限制 Path/Domain 并配置绝对过期和空闲过期。所有有副作用的 cookie-auth API 校验 CSRF token 和允许的 Origin；CORS 不允许带凭证的通配 origin。
- 每个请求先由 Session 得到 User，再由 User 得到唯一 Collection。路由不能接受客户端传入的 `collection_id` 作为授权依据；导入、媒体签名和 Worker payload 也必须携带并重新校验服务端确定的 Collection scope。
- 登录、注册、密码校验、媒体签名和导入入口应用独立速率限制。认证日志不记录密码、Session token、CSRF token、OSS 签名 URL 或完整私有输入。

## 11. 基础错误和可观测性

所有非 2xx 使用统一错误 envelope，稳定 machine code 见 `2026-08-api-error-and-import-contract.zh-CN.md`。本契约涉及的最小错误集合：

```text
NOTE_REVISION_CONFLICT
CARD_SCHEDULE_CONFLICT
QUEUE_EXPIRED
IDEMPOTENCY_KEY_REUSED
RATING_ALREADY_SET
UNDO_NOT_AVAILABLE
IMPORT_SCHEMA_UNSUPPORTED
DECK_HIERARCHY_CYCLE
DELETION_IMPACT_CHANGED
```

Web、Outbox Publisher、Worker 和导入流程都必须透传 `request_id`/`correlation_id`，日志不得打印用户私有媒体凭证。业务查询以 PostgreSQL Attempt/Card/MediaAsset 为准，Celery result backend 不作为事实来源。

## 12. 发布验收

- Alembic 必须能从空 PostgreSQL 实例一次构建完整 schema，并以幂等 seed 创建两个系统 NoteType、五个 Card Template 和唯一 Library Collection。
- destructive rebuild 先在隔离 Staging 对同一 commit/tag 执行；通过 schema smoke、Review seam、Worker duplicate delivery 和媒体清理测试后，Production 才允许执行。
- Production release job 使用 PostgreSQL advisory lock 防止并发迁移。迁移失败不得启动新版本 Web/Worker；成功后记录 commit/tag、migration revision、开始/结束时间和操作者。
- Production rebuild 前生成可恢复的数据库备份并核验 OSS namespace；PostgreSQL 配置完整备份和 WAL/PITR，目标 RPO 不超过 24 小时、RTO 不超过 4 小时。
- Web、Outbox Publisher 和 Worker 分别提供 health/readiness；readiness 必须覆盖 PostgreSQL/Redis 连通性，但外部 ASR/AI provider 暂时失败不能让已启动 Web 整体退出服务。

## 13. 非 AI 验收测试

### Schema 与隔离

- 从空 PostgreSQL 建库，验证所有 unique/check/composite FK、部分唯一索引和 seed 数据。
- 尝试把 Card、Attempt、private MediaReference 指向其他 Collection，数据库层必须拒绝；跨 Collection API 返回 404。
- 注册失败事务回滚；同一 normalized email、第二个 User Collection、第二个 Library Collection 均被约束拒绝。

### 内容与删除

- Vocabulary/Sentence Note 按有效模板生成唯一 Card；重复生成只补缺失项。
- Note revision 冲突、必填字段校验、NoteType 切换影响预览、过期 confirmation token、Card/Note/Deck 删除级联均覆盖。
- 普通 Note 编辑改变未来渲染，但已有 Attempt 的 front/back/answer/note snapshot 保持不变。

### 调度与 Queue

- 用锁定调度器覆盖 new、learning、review、relearning 的四按钮转换、15 分钟步骤、interval preview、reps/lapses 和最大间隔。
- 覆盖 Collection timezone 的 UTC 跨日、DST 前进/回退和 timezone 修改；相同 `due_day` 在不同部署时区得到一致学习日。
- 覆盖父/子 Deck 每日限额、并发 Rating 不突破配额、Undo 释放配额，以及 sibling bury 次日恢复。
- 覆盖 Queue 丢失重建、旧 queue_id 失效、相同 next 稳定返回、intraday learning 动态插回和一个未 Rating Attempt 的跨重启恢复。
- 对 flip/Rating 并发发送相同 key、不同 key、相同/不同 payload，验证只创建一个 Attempt、FSRS 只推进一次，旧 key 在 Undo 后不重新应用。

### Filtered Deck

- 对三种 sort_order 使用固定 Card/FSRS fixtures 验证稳定顺序；无 memory state 的 Card 始终排在 stateful Card 后。
- 覆盖 rebuild 后主序稳定、learning Card 插回、empty/delete 归还、借出期间原 Deck 删除和禁止直接移动 borrowed Card。

### 媒体、导入与 Outbox

- 覆盖 immutable object key、临时录音 TTL、仅最终录音认领、private 隔离、Library shared 读取和 pending_delete 重试。
- JSON/ZIP 使用同一 manifest fixtures，覆盖路径穿越、checksum/大小失败的全事务回滚、Deck/Note guid 幂等、本地编辑保留和缺失 Card 补齐。
- 重复投递同一 Outbox、Publisher lease 超时和 Worker 重试只能更新同一 Attempt；Celery result backend 清空后业务状态仍可从 PostgreSQL 完整读取。

### 最高应用 seam

至少有一条不 mock repository/service 的 API 集成测试完成：创建 Queue → next → flip 创建 Attempt/Outbox → Rating 推进 FSRS → next，并断言异步 processing pending 不阻塞 Rating。外部 provider 可替换为 adapter fake，但不能断言 ORM 或 Celery 内部调用细节。
