# Core 迁移第三阶段 TODO：生产切换与遗留删除

状态：等待第二阶段  
前置阶段：[CORE_MIGRATION_PHASE_2_TODO.md](CORE_MIGRATION_PHASE_2_TODO.md)

## 阶段目标

将 production 切换为 core 唯一运行时，把 core 直接挂到 `/api/v1`，然后删除 legacy 后端、旧数据库运行时依赖、前端兼容代码和双迁移体系。

## 授权要求

- production 备份、写入冻结、迁移和部署执行都需要用户明确授权。
- 未获得生产执行授权时，只能生成发布计划、校验命令和验收清单。
- 必须通过不可变 release 流程执行，不直接修改 production checkout 中的应用代码。

## 1. 生产切换准备

- [ ] 确认 staging 验收证据、目标 Git SHA、镜像 ID 和数据库 revision。
- [ ] 准备 core 数据库备份和 legacy 数据库只读快照。
- [ ] 准备写入冻结窗口，覆盖注册、设置和旧学习入口。
- [ ] 在最新 production 快照上执行迁移 dry-run。
- [ ] 审核全量差异报告：邀请码及用量、用户、Collection 设置及默认范围、Deck、Note、Card、Media 引用、membership、学习状态和历史活动去重结果。
- [ ] 批准回滚触发条件、观察窗口和 RTO；已提交 core 写入的 RPO 固定为 0。
- [ ] 准备并记录只能继续写 core 的回滚 release SHA 及其兼容 schema revision 范围。

## 2. 执行生产数据切换

- [ ] 开启维护窗口并在入口层拒绝全部 legacy 写请求。
- [ ] 停止新 legacy 作业，排空或显式取消后台队列，并终止仍会写旧库的活跃 session/WebSocket。
- [ ] 完成两个数据库的最终备份。
- [ ] 在只读事务中生成最终不可变快照、checksum 和 high-water mark。
- [ ] 执行只读 preflight；存在未解决冲突、源 checksum 变化或队列未清空时中止。
- [ ] 在单个 core 数据库事务中执行最终增量协调，失败时整批回滚。
- [ ] 运行数量、身份、状态和约束核对脚本。
- [ ] 抽样验证现有用户名账号、邮箱账号、课程选择和复习状态。
- [ ] 将 legacy 数据库改为只读；不得继续双写。

## 3. 发布 Core-only 产品流量

- [ ] 先发布第二阶段已验收的 core-only 前端。
- [ ] 验证登录、Dashboard、课程、Review、上传、ASR、AI feedback 和 Dialogue。
- [ ] 按发布前批准的阈值观察错误率、认证失败、队列失败、WebSocket 中断和数据库连接状态。
- [ ] 除健康检查和迁移管理请求外，连续 24 小时确认 production legacy 业务路由调用为零。
- [ ] 记录 release SHA、镜像 ID、迁移 revision 和验收证据。

## 4. 收敛正式运行入口

- [ ] 构建 Release A（兼容后端）：让同一个 core 同时服务 `/api/content/v1` 和 `/api/v1`，两个前缀共享同一数据库和行为；前端仍使用旧前缀。
- [ ] Release A 必须独立完成 immutable staging stage/approve，再推广 production；记录 Release A SHA 及其 core-only 回滚 SHA。
- [ ] 验证旧前端配 Release A 后端、新前端配 Release A 后端两种组合；不得出现前端/后端发布顺序窗口。
- [ ] 构建 Release B（正式前缀）：前端改用 `/api/v1`，后端启动入口改为 `core.main:app`，但继续保留 `/api/content/v1` core alias。
- [ ] Release B 必须独立完成 immutable staging stage/approve，再推广 production；记录 Release B SHA，回滚目标固定为已批准的 Release A SHA。
- [ ] Release B 明确接受一次强制重新登录，并清理旧 `/api/content/v1` path cookie。
- [ ] 更新 Nginx、Compose、健康检查和 WebSocket 路由。
- [ ] 验证 cookie path、CSRF、CORS 和 WebSocket upgrade。
- [ ] `/api/v1` 稳定且 `/api/content/v1` 连续 7 天无业务请求后，删除旧 alias。

## 5. 删除 Legacy 运行时代码

- [ ] 删除 `backend/app/`。
- [ ] 删除 `backend/migrations/` 和旧 Alembic 配置。
- [ ] 删除 `backend/core/release_app.py` 和 `backend/app/release.py`。
- [ ] 删除 `/auth/legacy`、`legacy_identity_url` 和 legacy token 验证代码。
- [ ] 删除 `legacy_selection.py`、`legacyReviewLocation` 和数字 ID 兼容接口。
- [ ] 删除 `/api/content`、`/content-api` 代理和 cookie path rewrite。
- [ ] 读取旧 `/study/:lessonId` 与 `/summary/:lessonId` 的独立前端遥测；两个路由各自连续 7 天命中数为零后，删除旧 Study 和 Summary 路由及实现。
- [ ] 删除 legacy Dashboard、课程树和 auth 实现。
- [ ] 保留 Dashboard、题库资源、我的课程、设置四个 core-only 主页面，以及 Login、Review、Card Detail、Dialogue History 流程页。
- [ ] 保留 Leaderboard 展示模块和空状态，为后续真实排行榜接口预留稳定 props，不保留硬编码排行。
- [ ] 删除 legacy 专属测试、fixture、mock 和发布配置。
- [ ] 保留迁移报告和必要的离线审计数据，但不得被运行时导入。

## 6. 测试与仓库收口

- [ ] 用 core 接口测试替代旧测试，不长期叠加两套行为测试。
- [ ] 运行 core 后端全量测试和迁移测试。
- [ ] 运行前端单元测试、类型检查、构建、lint 和完整 E2E。
- [ ] 运行 release tooling 测试和镜像健康检查。
- [ ] 实际执行一次应用 artifact 回滚和恢复前滚，验证不会恢复旧库或丢失 core 写入。
- [ ] 确认以下运行时遗留搜索没有结果：

```bash
rg 'VITE_CONTENT_CORE|VITE_LIBRARY_CONTENT_EDITOR|libraryContent|auth/legacy|legacy-lessons|/api/content|content-api|app.release' frontend backend scripts
```

- [ ] 确认运行配置只包含一个数据库 URL、一套迁移 head 和一个后端启动入口。
- [ ] 如需将 `backend/core` 重命名为 `backend/app`，放在独立机械提交中，不与行为切换混合。

## 7. 最终文档更新

- [ ] 功能全部合并后再统一更新 `README.md`、`PRD.md` 和 `PRD_BASELINE.md`。
- [ ] 更新运行命令、环境变量、接口前缀、数据库和发布流程。
- [ ] 归档三阶段迁移 TODO，并记录最终 release SHA 与完成日期。

## 最终完成条件

- production 的前端、后端和后台任务只依赖 core PostgreSQL。
- legacy 数据库处于只读归档状态，不参与登录或业务请求。
- 仓库中不存在运行时模式开关、身份交换、legacy ID 转换或组合后端。
- 新用户和已迁移用户使用同一套认证、课程、复习、对话和统计链路。
