# Core 迁移第一阶段 TODO：补齐独立运行能力

状态：已完成（2026-10-20）  
基线日期：2026-10-20  
后续阶段：[CORE_MIGRATION_PHASE_2_TODO.md](CORE_MIGRATION_PHASE_2_TODO.md)

## 阶段目标

让 `backend/core` 具备独立承载完整 LanGear 产品的能力。完成本阶段后，四个主页面（Dashboard、题库资源、我的课程、设置）以及登录、Review、卡片详情、Dialogue 和历史统计都应存在原生 core 接口，但暂不切换正式前端流量。

## 约束

- core PostgreSQL 是迁移后的唯一业务数据源。
- 不新增长期双写；旧数据库只作为迁移输入。
- 不把缺少不可变快照的旧 review history 伪造成 `Attempt`。
- 新接口以 UUID、Collection 隔离和 core session 为基础，不继续扩展 legacy 数字 ID。
- 外部依赖继续通过 OSS、ASR、Gemini/Qwen adapter 接入，但这些 adapter 的实现必须归 core 或中立包所有，core 不得再导入 `backend/app`。

## 1. 固定目标接口

- [x] 盘点前端当前使用的 legacy 路由、Bearer token、数字 lesson ID 和 `/api/content` 调用。
- [x] 为每个 legacy 调用标记处理方式：迁入 core、由现有 core 接口替代或直接删除。
- [x] 固定认证、Dashboard、全局设置、课程列表和历史统计的请求与响应结构。
- [x] 保证错误响应统一为 core 的 `error.code/message/details/request_id` 结构。
- [x] 固定四个主页面全部保留：`/dashboard`、`/library`、`/my-courses`、`/settings`。
- [x] 固定 `/library` 保留当前完整题库体验，由现有 `LibraryView` 收敛为 core-only 实现，不以独立 content 页面取代其他主页面。
- [x] 将 `default_source_scope` 迁为 Collection 中基于 core deck UUID 的 `default_deck_scope`，不再接受 legacy source 数字 ID。
- [x] 保留 Dashboard 的 Leaderboard 位置和组件接口；真实排行规则后置，迁移期间删除硬编码排名并显示明确空状态。
- [x] 增加接口级契约测试，避免迁移过程中同时修改前后端语义。

## 2. 补齐 Core 认证

- [x] 将邀请码注册规则迁入 core；邀请码的并发使用次数必须由数据库约束保护。
- [x] 保留“用户名或邮箱 + 密码”登录，覆盖已迁移账号的旧密码哈希验证。
- [x] 新密码统一使用 core 当前的 Argon2 哈希策略。
- [x] 补齐注册、登录、当前用户、退出、修改密码和禁用账号行为。
- [x] 所有浏览器认证统一使用 HttpOnly session cookie 和 CSRF，不返回 Bearer access token。
- [x] 覆盖用户名冲突、邮箱冲突、邀请码耗尽、禁用账号、session 过期和跨 Collection 隔离测试。

## 3. 补齐全局学习设置

- [x] 基于 `Collection.scheduling_config` 实现 `GET /api/v1/settings`。
- [x] 实现 `PUT /api/v1/settings`，覆盖目标保留率、学习步长、重学步长和最大复习间隔。
- [x] 将旧 `default_source_scope` 数据协调为 core `default_deck_scope` UUID 列表。
- [x] 保持现有 `/decks/{deck_id}/settings` 作为牌组级覆盖接口。
- [x] 覆盖 Collection 默认值、父子牌组继承、显式覆盖和恢复继承测试。

## 4. 实现 Core Dashboard

- [x] 实现 `GET /api/v1/dashboard`，直接返回当前前端需要的最终结构。
- [x] 从 core Card、Attempt、Review 队列计算今日新卡、今日复习、已完成和待复习数量。
- [x] 定义连续学习天数和热力图的业务口径及时区规则。
- [x] 新增可归属用户的每日活动聚合，承接旧历史统计。
- [x] Dashboard 保留 Leaderboard 槽位；没有真实排行数据时返回空集合，由前端展示空状态。
- [x] 将真实排行榜的排名口径、隐私范围和积分规则列为独立后续任务，不作为 core 切换阻塞项。
- [x] 覆盖空账号、跨日、时区、连续学习中断和大量历史记录测试。

## 5. 统一课程与练习入口

- [x] 确认 `GET /api/v1/decks` 能返回题库和“我的课程”所需的层级、membership 和统计字段。
- [x] 所有加入课程行为写入 core `Deck.in_my_courses`。
- [x] 所有选卡行为使用 `/decks/{deck_id}/study-selection` 和 core card UUID。
- [x] Review、设置和 Dialogue 全部只接受 core deck UUID。
- [x] 为旧教材导入内容保留来源元数据，但新业务代码不解析 `legacy:*` GUID。
- [x] 覆盖父子牌组、加入/退出课程、选卡、权限隔离和删除级联测试。

## 6. 迁移 Core 仍在复用的旧实现

- [x] 盘点 `backend/core` 中所有 `from app` / `import app` 依赖。
- [x] 将 ASR、AI feedback、OSS、FSRS 和 realtime 所需 adapter 迁入 core 自有模块或中立 integrations 包。
- [x] 将 realtime session、任务处理和配置读取迁出 `backend/app`。
- [x] 保留外部 provider 的可替换 seam，并为生产 adapter 提供测试 adapter。
- [x] 增加 core-only 导入测试：临时使 `app` 包不可用时，core 启动、处理任务和 realtime 路由仍可工作。
- [x] `rg 'from app|import app' backend/core` 在运行时代码中没有结果。

## 7. 建立最终数据协调工具

- [x] 在现有 `backend/core/legacy_import.py` 之外实现明确的最终增量协调流程。
- [x] 先定义每类实体的唯一来源、自然键、冲突规则和删除规则，覆盖邀请码、用户、设置、Deck、Note、Card、Media、membership、学习状态和每日活动。
- [x] 支持新增用户、账号状态、邀请码及用量、全局设置、课程 membership 和学习状态的最终同步。
- [x] 明确 legacy Deck/Note/Card/Media 在初次导入后的变更与删除如何处理；core 已产生的新数据不得被旧快照覆盖。
- [x] 使用确定性映射；同一输入重复执行必须得到相同结果。
- [x] 使用不可变输入快照、checksum 和 high-water mark；apply 前后源发生变化时必须中止。
- [x] 先完成只读 preflight，再在单个数据库事务中 apply；失败时整批回滚，不留下部分迁移。
- [x] 遇到身份、密码、邀请码、课程、卡片、媒体或活动重复冲突时停止，不静默覆盖 core 中的新数据。
- [x] 为已解决冲突保存显式决策清单；重跑不得要求人工重复判断。
- [x] 导入可归属用户的每日历史活动；无法安全归属的数据继续只读归档。
- [x] 每日活动使用稳定来源键去重，防止旧聚合与 core Attempt 重复计数。
- [x] 输出不含密码、token 或媒体签名的结构化迁移报告。
- [x] 核对脚本覆盖每类迁移实体的数量、稳定键和关键状态：邀请码及用量、User、Collection 设置及 `default_deck_scope`、Deck、Note、Card、Media 及引用、membership、学习状态和每日活动去重结果。
- [x] 对无法逐行比对的归档历史输出来源行数、归属结果、去重数和拒绝数，四项总和必须守恒。

## 8. 阶段验收

- [x] core 后端测试全部通过（210 passed）。
- [x] 新增“注册/登录 -> 加入课程 -> Review -> 设置 -> Dashboard -> Dialogue”集成测试。
- [x] 使用同一份不可变快照在隔离 PostgreSQL 完成至少两次迁移演练；第二次数据库写入数为零，报告 checksum 和数量完全一致。
- [x] 将 `backend/app` 从 Python import path 移除后，所有目标接口、worker 和 realtime 测试仍可通过。
- [x] 数量核对必须完全一致；允许差异只能来自版本控制中的机器可读 allowlist，并包含实体、原因和批准人。

## 退出条件

- [x] `core.main:app` 已具备完整产品接口，不需要调用 legacy 身份或业务接口。
- [x] `backend/core` 不再导入将于第三阶段删除的 `backend/app` 实现。
- [x] core 数据库包含前端运行所需的全部在线数据。
- [x] 第二阶段只需要改前端调用和部署流量，不再补核心业务能力。

## 实施说明

- 迁移 revision `lan33_0011` 新增 `invitation_codes`、`users.invitation_code_id`、`collections.default_deck_scope`、`decks.source_metadata/imported`、`notes.source_metadata/imported` 和 `daily_activities`，并把既有 `legacy:*` 行回填为 `imported = true`。
- 新增 core 模块：`settings_service.py`、`dashboard.py`、`courses.py`、`product_routes.py`、`reconcile.py`、`integrations/`。
- 核心测试要求 `PGTZ=UTC`（`study_day` 契约）与隔离的 `lan30_test_*` 数据库。
- 前端切换、`VITE_CONTENT_CORE` 删除与发布流程更新属于第二阶段，本阶段未改动前端。
