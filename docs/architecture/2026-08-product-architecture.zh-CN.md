# LanGear 产品方案架构基线

状态：已达成共识，2026-08-23

本文将产品讨论中的关键决策整理为可执行的架构边界。它是设计基线，不是当前数据库的迁移方案；由于目前没有用户数据，现有数据库可以直接废弃并按新模型重建。

## 一、产品方向

LanGear 是一个在线的、Anki-like 的英语口语练习与间隔重复系统。长期保存的学习单位是 `Card`，长期保存的内容单位是 `Note`。系统不设置永久性的“课程完成”状态；Card 根据调度器处于新卡、学习中、到期、暂停或埋藏等状态。

第一阶段的可执行范围：

1. 多用户账号与 Collection 数据隔离。
2. 层级 Deck，以及由 Note 动态渲染 Card。
3. Vocabulary 和 Sentence 两种系统 NoteType。
4. FSRS 调度、运行时复习队列、兄弟卡埋藏和 Filtered Deck。
5. 保存 Attempt 快照，并独立处理 ASR、AI 反馈和用户 Rating。
6. 系统 Library 复制导入，以及 LanGear 自有 JSON/ZIP 导入导出。

暂不做：教师工作流、作业系统、用户自定义模板、Library 自动同步、APKG、离线模式、PostgreSQL RLS、Dialogue Session 和开放式 Q&A。

## 二、领域模型

```text
User
└── Collection（每个用户一个）
    ├── Deck 层级树
    │   └── Card
    │       ├── Note
    │       ├── Card Template
    │       ├── FSRS 状态
    │       └── Attempt 历史
    └── 私有 MediaAsset

系统 Library Collection（唯一、只读）
└── Deck 层级树 → Note → 共享参考 MediaAsset
```

Note 不属于 Deck。创建 Note 时指定一个目标 Standard Deck，Note 生成的所有 Card 默认放入该 Deck。之后每张 Card 可以独立移动，也可以把不同 NoteType 的 Card 混合在同一个 Deck 中。Note 即使没有 Card 也保留；用户需要时，通过明确操作重新生成缺失的 Card。

## 三、第一版 NoteType

### 3.1 Vocabulary NoteType

字段：

```text
word
meaning
phonetic
note
reference_audio
image
```

Card Template：

```text
English to Chinese
Chinese to English
```

### 3.2 Sentence NoteType

字段：

```text
english
chinese
note
reference_audio
```

Card Template：

```text
Sentence Retelling
Sentence Translation
```

`Sentence Retelling` 优先使用参考音频或语义提示；没有参考音频时退化为文字提示。`Sentence Translation` 使用中文作为正面题面，英文作为答案。

默认情况下，NoteType 中所有有效 Card Template 都会为每条 Note 生成持久化 Card。模板和字段的变化属于受控结构操作；普通 Note 字段修改则是受乐观锁保护的直接更新。

## 四、核心复习流程

```text
开始运行时复习队列
→ 动态读取 Note + Card Template 并渲染题面
→ 用户可以多次试录临时音频
→ 翻面
→ 同一事务创建 Attempt + 两条 Outbox 任务
→ Rating API 可以立即更新 Attempt 与 Card 的 FSRS 状态
→ ASR 和 AI 任务独立更新同一条 Attempt
→ 从运行时队列取下一张 Card
```

翻面前的试录只是临时 OSS 对象，可以被后一次试录替换。只有翻面提交时使用的最后一段录音才会被认领为 Attempt 的永久媒体。

ASR、AI Feedback 和 Rating 三条流程互不依赖：

- Rating 由用户点击 Again、Hard、Good、Easy 决定，AI 不自动替用户评分。
- Rating 走同步 API，直接更新 Attempt 和 Card 的 FSRS 状态。
- ASR 由 Celery 异步处理，失败不影响 Rating。
- AI Feedback 由 Celery 异步处理，失败不影响 Rating，也不依赖 ASR 结果。
- ASR/AI 重试只更新同一条 Attempt，不创建新的 Attempt。
- Rating 写入一次后保持幂等；重复请求不会再次推进 FSRS。

撤回采用 Anki 风格的运行时 Undo：只保留当前复习服务中的最近一次操作，不在数据库中增加 FSRS 前状态字段。服务重启或切换服务实例后，不保证仍然可以撤回；前端 `rewind` 只负责回到正面，不回滚已提交的数据库状态。

复习队列是运行时状态，不建立持久化 Study Session 或队列表。队列可以保存在进程内存或 Redis 中，丢失后按当前 Card 状态重新生成，不影响已经保存的学习事实。

## 五、数据库 Schema 草案

以下是持久化表的边界。具体 SQLAlchemy 模型、字段类型、索引和 Alembic 迁移属于后续实现工作。

```text
users
collections
decks(parent_id, kind, filter_config_json, scheduling_config)
note_types
note_type_fields
card_templates
notes(guid, fields_json, tags, revision)
cards(note_id, deck_id, card_template_id, type, queue,
      due_at, due_day, fsrs_state_json,
      original_deck_id, original_due)
card_review_attempts(card_id, note_id, snapshots,
                    audio_asset_id, ASR fields,
                    feedback fields, rating)
media_assets(scope, collection_id, object_key, lifecycle)
task_outbox(task_type, aggregate_id, status, retry metadata)
```

### 5.1 所有权与隔离

所有用户核心表都保存 `collection_id`。通过复合外键保证 Note、Card、Deck、Attempt 和媒体引用不会跨 Collection 关联。

第一版规则：

- 每个用户注册时自动创建一个 Collection。
- `collections.owner_user_id` 唯一，用户不能创建第二个 Collection。
- 系统 Library 使用一个唯一的只读 Collection，`owner_user_id` 为空。
- 普通 API 不允许直接修改系统 Library。
- 第一版不启用 PostgreSQL RLS，依赖服务端 Collection scope、复合外键和自动化测试。

### 5.2 Note 与导入身份

`Note.guid` 是 Collection 内的稳定导入身份：

```text
有 guid
→ 按 (collection_id, guid) 查找并幂等更新

没有 guid
→ 按 NoteType 的主字段查重
→ 默认跳过重复项
```

Library 导入保留原始 `guid`，但不覆盖用户已经修改的 Note。重复导入同一 Library Deck 时，只补充缺失 Card；已有 Card 不移动。

### 5.3 Card 与调度

Note 不保存 `deck_id`；Card 才保存当前 Deck。Card 使用 Anki 式 `type + queue`：

```text
new = 0
learning = 1
review = 2
relearning = 3
suspended = -1
buried_user = -2
buried_sibling = -3
```

应用代码使用枚举，不直接散落魔法数字。Filtered Deck 临时修改 `deck_id`，同时保存 `original_deck_id` 和 `original_due`；一张 Card 同时最多属于一个 Filtered Deck。删除 Filtered Deck 前先归还 Card。

Card 的当前 FSRS 状态直接保存在 `cards`。`user_card_srs` 不再单独存在。Attempt 保存用户 Rating、算法版本和配置版本，但不保存 FSRS 前后状态快照。

所有时间点使用 PostgreSQL `timestamptz`，统一保存 UTC；Collection 保存 IANA 时区，用于计算学习日和“今天到期”的边界。

### 5.4 Attempt

一条 Attempt 代表一次翻面提交，而不是一次试录。它需要保存：

- 当时的输入类型和输入快照；
- Note 完整字段快照；
- 实际渲染出的正面、背面和答案快照；
- 最终提交的用户录音媒体引用，可为空；
- ASR 状态和结果 JSON；
- AI Feedback 状态和结果 JSON；
- 用户 Rating 与评分时间；
- 模型、算法和配置版本。

Attempt 创建后，题面和输入快照不可变。ASR、AI Feedback 和 Rating 只补写各自负责的字段。

### 5.5 Outbox 与异步任务

创建 Attempt 时，同一个 PostgreSQL 事务写入：

```text
Attempt
+ task_outbox(transcribe_attempt)
+ task_outbox(evaluate_attempt)
```

Outbox Publisher 将两条任务分别投递到 Celery。投递语义是至少一次，因此 Worker 必须以 `attempt_id` 幂等：重复任务只能更新同一条 Attempt，不能创建新 Attempt 或重复推进 FSRS。

Celery 只负责可靠投递和执行；Attempt 才是 ASR、AI 和 Rating 的业务事实来源。

## 六、删除规则

所有破坏性操作都需要明确确认。第一版不做回收站，恢复依赖 PostgreSQL 备份/PITR 和 OSS 延迟清理。

```text
删除 Card
→ 硬删除 Card 与 Attempts
→ Note 保留

删除 Note
→ 硬删除 Note、全部 Cards 与 Attempts
→ 媒体进入延迟清理

删除 Standard Deck
→ 硬删除其中 Cards 与关联 Attempts
→ 仍被其他 Card 使用的 Note 保留

删除 Filtered Deck
→ 先归还 Cards
→ 再删除 Filtered Deck

删除 CardTemplate / NoteType
→ 展示影响范围并确认
→ 批量删除受影响的 Cards 与 Attempts
```

用户删除账号时，删除其 Collection、学习数据和私有媒体；系统 Library 与仍被引用的共享媒体保留。

## 七、基础设施与发布

- 开发、Staging、Production 全部使用 PostgreSQL；不以 SQLite 能力设计 schema。
- 核心实体使用应用生成的 UUIDv7。
- ASR/AI 使用 Celery + Redis；PostgreSQL 是业务事实来源。
- Attempt 与 Outbox 在同一事务中创建，避免数据库提交与任务投递之间的双写丢失。
- Production migration 由独立 release job 显式执行，不在每个 Web/Worker 进程启动时自动执行。
- `main` 自动部署 Staging；Production 发布已验证的同一 commit/tag。
- Staging 与 Production 使用独立的 PostgreSQL、Redis、Worker 和 OSS 命名空间。
- PostgreSQL 使用完整备份和 WAL/PITR，目标 RPO 不超过 24 小时，RTO 不超过 4 小时。
- 用户认证使用邮箱密码、Argon2id 和 HttpOnly Session Cookie；OAuth 延后。

## 八、产品路线图

### P0：基础模型与可靠性

- 重建 PostgreSQL schema 和 Alembic migrations。
- 用户、Session、Collection、默认 Deck。
- NoteType、CardTemplate、Note、Card 动态渲染。
- Collection scope、复合外键、乐观锁。
- OSS 临时上传、MediaAsset、延迟清理。
- Celery、Redis、Transactional Outbox、失败重试和幂等。

### P1：核心复习闭环

- Vocabulary/Sentence 两种 NoteType。
- FSRS 调度、每日上限、层级 Deck 配额。
- 运行时复习队列、Sibling Burying、Filtered Deck。
- 翻面创建 Attempt。
- Rating、ASR、AI Feedback 三条独立流程。
- Attempt 快照、历史查询和运行时 Undo。

### P2：内容进出与 Library

- 系统 Library 只读展示。
- Deck 子树和 Note 复制导入。
- 按 guid 幂等导入与缺失 Card 补齐。
- LanGear JSON/ZIP 导出和再次导入。

### P3：后续产品能力

- Card-level AI Explanation。
- Q&A/summary agent。
- Dialogue Session、Scenario、Dialogue Goal、Target Expressions。
- 教师、学生、作业计划和 AI 学习报告。
- 用户自定义 NoteType/CardTemplate。
- APKG、离线复习和多 Collection。
