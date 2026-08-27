# LanGear v1 Contract 索引与责任边界

状态：已确认，2026-08-27

本页是 v1 destructive backend rebuild 的文档入口。它只说明规范来源、优先级和实施责任，不重复字段细节。

## 规范优先级

发生冲突时按以下顺序解释：

1. 专项 contract：Review API、Card Scheduling、Attempt Processing、API Error/Import、Anki Field Contract；
2. `2026-08-non-ai-core-contract.zh-CN.md`；
3. `2026-08-product-architecture.zh-CN.md` 总体基线；
4. ADR 只解释为何选择，不覆盖后续 contract；
5. Anki 源码研究只提供证据，不意味着文件格式或所有产品行为兼容。

旧生产 schema、旧 `/study/session`、旧 `/study/submissions`、LAN-22 和 LAN-15 中的兼容迁移、`user_deck` 学习实例拆分及独立 `user_card_fsrs` 当前状态，不是新实现 contract。

## 已冻结文档

| 文档 | 规范范围 | 主要负责人 |
| --- | --- | --- |
| `2026-08-non-ai-core-contract.zh-CN.md` | PostgreSQL、Collection、内容模型、Review runtime、媒体、Outbox、认证、部署、测试 | Feng |
| `2026-08-card-scheduling-contract.zh-CN.md` | Card type/queue/due、FSRS、限额、bury/suspend | Feng |
| `2026-08-review-api-contract.zh-CN.md` | Queue/next/flip/Rating/Undo HTTP seam 与模板输入矩阵 | Shared contract；Feng 后端、产品开发者前端 |
| `2026-08-anki-field-contract.zh-CN.md` | 可复用 Anki 语义及明确差异 | Feng |
| `2026-08-api-error-and-import-contract.zh-CN.md` | 错误 envelope、JSON/ZIP import | Feng 后端、产品开发者消费错误 |
| `2026-08-attempt-processing-contract.zh-CN.md` | ASR/AI 独立状态、Retelling/Translation evaluator envelope | 产品/AI；Feng 提供任务和持久化边界 |
| `2026-08-anki-source-research.zh-CN.md` | 固定 Anki commit 的源码证据 | Reference only |

## 两位开发者分工

### Feng：非 AI 基础设施主线

按依赖顺序交付：

1. PostgreSQL/Alembic 空库基线、UUIDv7、系统 seed、User/Session/Collection、复合所有权约束；
2. Deck/NoteType/CardTemplate/Note/Card、动态渲染、revision、结构切换和删除影响预检；
3. 锁定 FSRS adapter、Card 状态机、层级日限额、bury/suspend 和时区边界；
4. Review Queue/next/flip/Rating/Undo、Attempt 快照、持久化幂等；
5. OSS MediaAsset/MediaReference、Transactional Outbox、Redis/Celery 可靠投递；
6. Filtered Deck、Library copy、JSON/ZIP import；
7. Staging/Production release job、备份/PITR、健康检查和端到端非 AI 验收。

### 产品/AI 开发者

可立即与 Feng 并行，并依赖当前已冻结的 Review contract：

1. 五个 Card Template 的前端交互与 input requirement；
2. Queue/next/flip/Rating/Undo 的 Vue store、组件和浏览器流程；
3. Retelling/Translation 分离的 prompt、evaluator、JSON schema、fixture 和 eval；
4. Dictation 确定性 evaluator 的产品反馈展示；
5. Attempt processing/history UI，以及 ASR/AI pending/failed/skipped 独立状态。

产品/AI 开发者不直接修改 Card FSRS、due、Collection ownership 或 Outbox 投递语义；Feng 不在基础设施实现里自行合并 Retelling/Translation prompt 或让 AI 选择 Rating。

## 共享契约基线

OpenAPI 和 fixtures 是两边共同维护的第一个交付物，不是开工审批或串行前置条件。Feng 可以实现 Review service，产品开发者可以同时按当前 contract 开发 Review store；联调使用以下同源产物：

- OpenAPI 中的 UUID/string enum、错误 envelope 和 input discriminated union；
- `CardFront`、`AttemptSnapshot`、`RatingOption`、`AttemptProcessing` DTO；
- `review_token`、`card_schedule_revision` 和 Idempotency-Key 行为；
- 一套由后端生成、前端消费的 contract fixtures。

共享 DTO 只有一个 schema 来源；前端类型由 OpenAPI 生成或由同一 schema 校验，避免维护第二套同名状态机。

## 不需要再次产品确认的实现参数

以下参数不改变已冻结业务语义，可由实现 issue 固定后进入 lock/config：

- 成熟 Python FSRS 库的具体 package/version；必须 pin，并通过 Anki 语义 fixture 测试；
- Session 绝对/空闲 TTL、temporary media TTL、pending-delete grace period、IdempotencyRecord TTL；
- JSON/ZIP 与媒体的具体字节上限、Worker retry/backoff 和 Redis Queue TTL；
- PostgreSQL 索引名称、Alembic revision ID、Celery queue 名称和 OSS object key 前缀。

任何改变 Card 状态转换、输入必填规则、Attempt 创建时机、跨 Collection 访问、导入覆盖策略或 Filtered Deck 排序的提议，必须先修改对应 contract，再进入实现 issue。
