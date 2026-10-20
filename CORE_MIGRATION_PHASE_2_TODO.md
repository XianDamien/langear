# Core 迁移第二阶段 TODO：前端单轨与 Staging 切换

状态：代码迁移已完成；staging 发布与验收待执行（2026-10-20）  
前置阶段：[CORE_MIGRATION_PHASE_1_TODO.md](CORE_MIGRATION_PHASE_1_TODO.md)  
后续阶段：[CORE_MIGRATION_PHASE_3_TODO.md](CORE_MIGRATION_PHASE_3_TODO.md)

## 阶段目标

让前端只认识一个 core 接口和一种认证方式，并在 staging 证明四个主页面及完整学习链路不再访问 legacy。为降低切换风险，本阶段可以暂时继续把 core 挂在 `/api/content/v1`，但前端不得再保留双模式分支。

## 约束

- 前端不再根据环境变量选择 legacy/core 行为。
- 切换后所有新写入只进入 core，禁止回滚到会继续写旧数据库的版本。
- staging 数据库继续与 production 隔离。
- 验收使用现有 Playwright 测试或直接接口检查，不使用 `agent-browser`。

## 1. 统一前端请求模块

- [x] 新建唯一的 core HTTP 模块，统一 base URL、cookie、CSRF、超时和错误解析。
- [x] 将 `http.ts`、`contentCore.ts` 和 `libraryContent.ts` 的调用迁入该模块。
- [x] 删除 Bearer token 注入和 `langear_access_token` localStorage 状态。
- [x] 删除 `/auth/legacy` session exchange。
- [x] 确保上传到 OSS 的请求不会携带应用 cookie、CSRF 或认证头。
- [x] 用接口级测试覆盖 GET、写请求、CSRF 刷新、401 和 session 过期。

## 2. 切换统一认证界面

- [x] LoginView 始终提交 core 的“用户名或邮箱 + 密码”格式。
- [x] 注册界面使用 core 邀请码规则和密码要求。
- [x] 路由守卫只查询 core `/auth/me`。
- [x] 退出时清理 core session，不再维护两套 auth store。
- [x] 删除 legacy `useAuthStore`、`authToken.ts` 和相关 mock 分支。

## 3. 迁移页面与路由

- [x] Dashboard 只请求 core Dashboard。
- [x] `/library` 主页面保留，`LibraryView` 只使用 core Deck/Note/Card 数据并保留题库编辑能力。
- [x] My Courses 只展示 `in_my_courses=true` 的 core Deck，不拼接 legacy tree。
- [x] Settings 只使用 core Collection 和 Deck 设置接口。
- [x] Dashboard、题库资源、我的课程和设置继续作为四个主导航入口。
- [x] Login/Register、Review、Card Detail 和 Dialogue History 继续作为流程页或详情页。
- [x] Leaderboard 组件改为接收数据的展示模块；没有真实接口时展示“暂无排行数据”，不得保留硬编码用户和积分。
- [x] 所有 Review、Dialogue、卡片和设置路由使用 UUID。
- [x] 删除 `legacyReviewLocation`、`legacy-lessons` 和数字 lesson ID 转换。
- [x] 旧 `/study/:lessonId` 和 `/summary/:lessonId` 不再查询 ID 映射，只重定向到 `/my-courses` 并提示旧链接已失效。
- [x] 为上述两个旧 SPA 路由增加不含用户内容的命中计数遥测，分别记录 route name、日期和 release SHA。
- [ ] 上述无状态重定向保留到第一版 core-only production 发布后；两个路由各自连续 7 天命中数为零后由第三阶段删除。

## 4. 删除前端双模式

- [x] 删除 `VITE_CONTENT_CORE`。
- [x] 删除 `VITE_LIBRARY_CONTENT_EDITOR`。
- [x] 删除 `ResourceLibraryView`/`LibraryView` 的模式选择；保留 `/library` 和最终 core-only `LibraryView`，迁入仍需的编辑能力。
- [x] 删除 core/legacy 条件导航和条件路由守卫。
- [x] 删除只用于独立 content 模式的脚本、E2E 配置和测试夹具。
- [x] 更新 `.env.development`、`.env.staging` 和 `.env.production`，不再声明模式开关。

## 5. Staging 数据与发布演练

- [x] 发布前检查本地 worktree 与 staging checkout 的分支、提交和脏文件。
- [ ] 备份 staging core 与 legacy 数据库。
- [ ] 进入维护窗口，阻止所有 legacy 数据库写入，包括注册、设置、课程选择、Study submission、ASR session 和后台任务。
- [ ] 停止接收新 legacy 作业，排空或明确取消队列，并处理仍活跃的浏览器/WebSocket session。
- [ ] 在只读事务中生成不可变快照、checksum 和 high-water mark。
- [ ] 执行第一阶段的 preflight、最终协调工具与核对脚本；checksum 变化或核对失败时中止发布。
- [ ] 发布过渡版本：前端全部访问 core，组合后端暂时保留 legacy 作为回滚外壳。
- [ ] 确认运行镜像 SHA、source mount、数据库和迁移 revision 与目标提交一致。

## 6. 更新不可变发布工具

- [x] 更新 release manifest，使 core-only 成为明确的 runtime 类型。
- [x] 更新 `scripts/release/package.py`、`host.py` 和管理命令，不再硬编码 `app.release:app` 或旧 Alembic。
- [x] core-only runtime 只执行 core migration head 检查和 core readiness 检查。
- [ ] 为 `/api/content/v1` 过渡路径、HTTP、WebSocket、cookie path 和 worker 增加打包后测试。
- [ ] 在 staging 完整执行 stage、approve、rollback 演练，并记录 artifact SHA、兼容 schema 范围、RTO 和 RPO；已提交 core 写入的 RPO 必须为 0。

## 7. Staging 验收

- [ ] 已迁移用户名账号和邮箱账号都能登录。
- [ ] 使用固定数据集断言 Dashboard 数量、连续学习和热力图的精确期望值。
- [ ] 题库、我的课程、加入/退出课程和选卡正常。
- [ ] 五类 Review、评分、撤销、重试和 FSRS 状态正常。
- [ ] 音频上传、实时 ASR、AI feedback 和 Dialogue 正常。
- [ ] 对话历史与删除功能按 Collection 隔离。
- [ ] 刷新页面后 session、当前 Review 和页面路由可恢复。
- [ ] 除显式健康检查和迁移管理请求外，连续 24 小时访问日志中 legacy 业务路由请求数为零。
- [x] 前端单元测试、类型检查、构建、lint 和 Playwright E2E 通过。
- [x] core 后端全量测试和迁移 head 检查通过。

## 回滚规则

- 可回滚到本阶段最近一个仍然只写 core 的前端/后端组合。
- 不允许回滚到恢复 legacy 写入的版本，否则会造成两个数据库重新分叉。
- 组合后端只提供短期路由兼容，不代表 legacy 重新成为数据源。
- 常规应用回滚只切换已验证 artifact，不恢复数据库备份；备份恢复仅用于数据库灾难，并需要单独授权。
- rollback 演练必须证明 schema 向后兼容且不会丢失切换后的已提交 core 写入。

## 退出条件

- 前端运行时代码只使用 core 接口和 core session。
- staging 完整业务链路通过，且 legacy 业务流量为零。
- 生产切换所需的数据工具、发布包、核对脚本和回滚包均已在 staging 实际演练。

