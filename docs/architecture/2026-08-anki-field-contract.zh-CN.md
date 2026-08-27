# LanGear v1 Anki 字段契约

状态：已确认，2026-08-27

本文只冻结领域字段的语义和兼容原则，不冻结 SQLAlchemy 模型、表名或 Celery 实现。LanGear 的 API 使用 `snake_case`；Anki 的 `camelCase`、短字段名和旧 `.apkg` 字段名不进入 v1 API 或导入格式。

## 复用原则

- 能保持原语义的字段直接复用，例如 `guid`、`tags`、`type`、`queue`、`reps`、`lapses`、模板序号 `ord`。
- Anki 将多个语义压在一个字段里的地方，LanGear 拆成明确字段。例如 Anki 的 `due` 会随队列改变含义，LanGear 用 `due_at`、`due_day` 和 `new_position` 表达不同状态。
- Anki 同步专用字段不进入 v1 领域模型。`usn`、SQLite 整数 ID、`graves` 和 Anki 的 collection sync 元数据不属于 LanGear contract。
- `Attempt` 不是 Anki `revlog` 的改名。Attempt 是一次翻面提交和内容快照；FSRS 调度审计如果以后需要，另建明确的 scheduler event，不混入 Attempt。

## Collection

| Anki 字段/概念 | LanGear 字段 | 决定 |
| --- | --- | --- |
| collection 配置 | `collection.timezone` | 复用“Collection 保存配置”的边界；值为 IANA timezone，绝对时间仍使用 UTC |
| `crt`、`mod`、`scm`、`ver` | `created_at`、`updated_at`、`schema_version` | 复用审计/版本语义，但不用 Anki 的 Unix 秒和同步版本混合字段 |
| collection 内模型/牌组配置 | `note_types`、`decks` | 拆成受约束的领域实体，不使用 Anki JSON 大对象 |

## Note、NoteType、Field、CardTemplate

| Anki 字段/概念 | LanGear 字段 | 决定 |
| --- | --- | --- |
| `notes.id` | `notes.id`（UUIDv7） | 复用稳定实体 ID 的用途；不复用整数类型 |
| `notes.guid` | `notes.guid` | 直接复用，作为 Collection 内 Library/import 幂等身份 |
| `notes.mid` | `notes.note_type_id` | 复用 Note 指向 NoteType 的关系；改成语义化名称 |
| `notes.flds` | `notes.fields`（JSONB/API object） | 复用“按 NoteType 保存字段”的语义；不使用 Anki 的 `\x1f` 拼接字符串 |
| `notes.tags` | `notes.tags`（去重后的 string[]） | 直接复用 |
| `notes.mod` | `notes.updated_at` | 复用更新时间；改为 UTC `timestamptz` |
| `notes.sfld`、`csum` | `notes.primary_field_value`（可选派生索引） | 只复用“排序/查重主字段”用途；不把哈希值作为领域事实 |
| `notes.flags`、`notes.data` | 不进入 v1 contract | 预留扩展字段时另行定义，不能作为前后端共享的无类型 JSON |
| `notetype.name` | `note_types.key`、`display_name` | `key` 为稳定机器标识（如 `vocabulary`），展示名可变 |
| `notetype.flds[]` | `note_type_fields[]` | 复用字段序号 `ord`、名称和必填/渲染要求；v1 系统 NoteType 为只读 |
| `notetype.tmpls[]` | `card_templates[]` | 复用模板序号 `ord`、名称、正面格式 `q_format`、背面格式 `a_format` |
| `notetype.req` | `card_templates.required_fields` | 复用“模板生成所需字段”的语义；改为可读的字段 key 列表/规则 |
| `notetype.css` | `card_templates.style`（可选） | 只在渲染确实需要时保留；不是业务内容 |
| `notetype.did` / template target deck | 不复用 | LanGear 的 Card 独立拥有当前 Deck，模板不能隐式决定 Deck |
| template `ord` | `cards.template_ord` | 直接复用；它是 NoteType 内稳定的 Card Template 索引 |

v1 系统 NoteType 的字段 key 固定为：

- Vocabulary：`word`、`meaning`、`phonetic`、`note`、`reference_audio`、`image`
- Sentence：`english`、`chinese`、`note`、`reference_audio`；模板为 Retelling、Translation、Dictation，其中 Dictation 仅在 `reference_audio` 有效时生成

## Deck

| Anki 字段/概念 | LanGear 字段 | 决定 |
| --- | --- | --- |
| `did` | `cards.deck_id` | 复用 Card 当前 Deck 归属 |
| deck name hierarchy | `decks.name`、`parent_id` | 复用层级牌组语义；名称和父级关系显式建模 |
| normal/filtered deck | `decks.kind` | 复用两种容器概念；Filtered Deck 仍是临时容器 |
| filtered search terms | `decks.filter_config.search_terms[]` | 复用 `query`、`limit`、`sort_order`；v1 固定参与正式重新调度，不暴露 Preview 开关 |
| deck daily limits | `decks.new_limit`、`review_limit` | 复用新卡/复习配额语义；父级和子树的有效配额取最小值 |
| Anki deck config preset | `decks.scheduling_config` | 只复用当前需要的配置字段；v1 不做可复用 DeckConfig preset |

Filtered Deck v1 的 `sort_order` 只允许：

- `added`：按 `card.created_at ASC, card.id ASC`，即 Card 添加顺序；
- `retrievability_ascending`：rebuild 时计算 FSRS retrievability，数值低、最容易忘记的 Card 优先；
- `retrievability_descending`：rebuild 时计算 FSRS retrievability，数值高、最容易记住的 Card 优先。

没有 FSRS memory state 的 Card 在两种 retrievability 排序中均排在有状态 Card 之后，并按 `added` 保持稳定。Filtered Deck rebuild 时按 `search_terms` 依次查询、排序和截取 Card，并把有序 Card ID 放入进程内存或 Redis。主队列在本次运行时 build 后保持稳定；分钟级 learning Card 可以按 `due_at` 动态插回。Card 不保存 `filtered_position`，队列丢失或显式 rebuild 时重新计算。

v1 最多保存两个 `search_terms`，与固定参考的 Anki 实现上限一致。

## Card 与 FSRS

### 直接复用语义

| Anki 字段 | LanGear 字段 | 说明 |
| --- | --- | --- |
| `type` | `type` | `new`、`learning`、`review`、`relearning` |
| `queue` | `queue` | `new`、`learning`、`day_learning`、`review`、`suspended`、`buried_sibling`、`buried_user`；`relearning` 只属于 `type` |
| `ord` | `template_ord` | Card 使用的 Card Template 序号 |
| `reps` | `reps` | 影响调度的累计评分次数 |
| `lapses` | `lapses` | 进入 relearning 的次数 |
| `left` / `remaining_steps` | `learning_steps_remaining` | 学习步骤剩余次数；不暴露模糊的 `left` 名称 |
| `flags` | `flags`（可选） | 仅在 v1 真正提供用户旗标时启用，不能承载状态机 |
| `custom_data` | `custom_data`（可选） | 仅作为版本化扩展，不参与核心调度契约 |

### 语义复用但拆分

| Anki 字段 | LanGear 字段 | 原因 |
| --- | --- | --- |
| `due` | `due_at`、`due_day`、`new_position` | Anki 中 `due` 对 new/learning/review 是不同单位；LanGear 需要明确 UTC 时间和 Collection 学习日 |
| `ivl` | `interval_days` | v1 FSRS 以天为主要间隔；学习中的短时到期由 `due_at` 表达，不使用负秒编码 |
| `factor` | `fsrs_state.difficulty` / `fsrs_state.stability` | `factor` 是 SM-2 ease factor，不是 FSRS 的完整状态；不把它误命名成 FSRS 字段 |
| `odue` | 不复用 | Filtered Deck 不覆盖正式调度字段，因此无需保存原始 due |
| `odid` | `original_deck_id` | 直接复用原始 Deck 归还语义，但使用 UUIDv7 |
| `last_review_time` | `last_reviewed_at` | 复用最近复习时间；统一 UTC `timestamptz` |
| `memory_state` | `fsrs_state` | 复用 FSRS 稳定性/难度状态；具体 JSON schema 需由调度 contract 另行冻结 |

Card 还必须有 `id`、`collection_id`、`note_id`、`card_template_id`、`deck_id`、`original_deck_id`、`created_at`、`updated_at`。Card 不保存当前渲染题面或 Filtered Deck 排序位置；题面由 Note 当前字段和模板动态生成。

## Attempt 与 Anki revlog 的边界

Anki revlog 中以下语义可以参考，但不能直接照搬字段名：

| Anki revlog | LanGear Attempt |
| --- | --- |
| `ease` / button chosen | `rating`：`again`、`hard`、`good`、`easy` |
| `ivl`、`lastIvl` | `scheduled_interval_days`、`previous_interval_days`，作为评分时的调度结果快照 |
| `time` | `duration_ms`，仅表示本次输入/作答耗时 |
| `type` | `review_kind`，如 `learning`、`review`、`relearning`、`filtered`；不与 `input_type` 混用 |
| `id`、`cid` | `attempt.id`、`attempt.card_id`（UUIDv7） |

Attempt 额外必须保存 `note_snapshot`、`front_snapshot`、`back_snapshot`、`answer_snapshot`、`input_type`、最终媒体引用、ASR/AI 独立状态和结果、模型/配置版本。题面与输入快照创建后不可变；Rating、ASR、AI 只能补写各自字段。

## 明确不复用的 Anki 字段

`usn`、整数 `id`、`graves`、`col.models/decks/dconf` JSON、`sfld` 的哈希事实、SM-2 专用 `factor`、Anki 同步版本字段，以及 `revlog` 作为 Attempt 的替代品，都不进入 LanGear v1 业务 contract。
