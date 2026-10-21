# Shared Library 导入执行清单

## 目标与决策

- 使用现有 `kind='library'` collection 和 `decks`、`notes`、`cards` 表，不新增平行的 Library 表或 per-user 状态表。
- 点击父 deck 时复制完整子树；用户副本拥有独立的 note/card 行和新卡调度状态。
- 从“我的课程”移除共享课程时，预览影响范围并确认删除用户副本；共享 Library 不受影响。
- Library 只显示内容量；用户自建/编辑入口放在“我的课程”。

## 当前状态（2026-10-21）

任务 worktree：`.worktrees/library-shared-import`，分支：`feature/library-shared-import`。代码尚未提交、未同步 staging、未向 `test1`～`test10` 写入数据。

已在工作区实现 Library 树/卡片只读 API、整棵子树导入 API、Library/My Courses 页面切换，以及删除预览中对 Library 副本孤立 note 的统计与删除。导入按 deck/note GUID 幂等，note 的 `imported=False`，逐张复制来源卡片并通过 `ContentService.next_position()` 分配新位置。Library 页面可预览牌组子树内容并分页。

## 改动前后逻辑

| 操作 | 改动前 | 改动后 |
| --- | --- | --- |
| 浏览题库 | 读取当前用户 collection，Library 同时承担内容编辑 | 读取共享 Library collection，只读查看牌组与卡片；内容编辑入口在“我的课程” |
| 加入课程 | 修改当前用户 deck 的 `in_my_courses`，父子牌组分别选择 | 复制选中 deck 的完整子树、note 和 card 到当前用户 collection，副本独立学习 |
| 再次加入 | 再次切换成员状态 | 按 GUID 补齐缺失内容，保留已有 note 字段、卡片调度和用户调整的牌组/卡片位置 |
| 移除课程 | 将 `in_my_courses` 设为 false，内容和学习状态仍在 | 显示删除范围并确认，删除所选用户 deck 子树及其卡片/复习记录；共享原件不受影响 |
| 统计 | 同一批用户牌组同时展示内容和学习状态 | Library 只显示内容量；My Courses 显示用户副本的学习状态 |

Library 使用现有 `collections.kind='library'`，无需新增平行表。删除确认按当前用户 deck 子树计算范围，若用户在副本下面加入自己的牌组或卡片，也会进入删除预览的范围。

验证现状：

- 本机 PostgreSQL 15 正在运行。本次修复使用独立的 `lan30_test_library_fix_20261021` 测试库，没有使用 `lan30_local` 或 staging 数据库。
- `PGTZ=UTC` 下全量 `backend/core_tests`：261 passed。新增覆盖用户移动牌组后的重导入、NoteType 转换后重导入、编辑 note 后删除令牌失效，以及父牌组内容量聚合。未设置 `PGTZ` 时，本机 PostgreSQL 的 `Asia/Shanghai` 会使一项未改动的 legacy 时间断言失败。
- 前端 `pnpm typecheck`、`pnpm test:unit`（134 passed）和 `pnpm build`：通过。一次并行运行中的单测因 5 秒超时失败，单独重跑全量通过。
- 改动涉及的前端文件 ESLint 与 `git diff --check HEAD`：通过。

## 发布前必须完成

1. **做真实页面验收。** 在本地或选定的 staging 运行与本分支一致的前后端，使用测试账号检查：预览共享子树及分页 → 导入父 deck → 在 My Courses 练习/编辑 → 删除副本 → Library 原件仍在 → 再导入产生全新调度状态。检查移动端布局和确认弹窗。
2. **交付前复核。** 检查同名/GUID 冲突、跨 collection 媒体引用、导入子 deck 后再导入父 deck、用户移动牌组/卡片与 NoteType 转换后的重导入结果。上述场景已各有后端测试，真实数据验收仍待执行。

## 交付步骤

1. 在该 worktree 完成上述修正，并再次运行：

   ```bash
   cd backend
   PGTZ=UTC CORE_TEST_DATABASE_URL='postgresql+psycopg://damien@127.0.0.1/lan30_test_library_fix_20261021' uv run --extra dev pytest -q core_tests
   cd ../frontend
   pnpm typecheck
   pnpm test:unit
   pnpm build
   ```

2. 审核 `git diff` 与 `git status`，只提交本任务文件。提交标题按仓库约定使用简短中文。
3. 如需 staging 验收，先分别检查本地与 staging checkout 的分支、提交、暂存/未暂存改动，再将指定提交同步到明确选定的 staging checkout；验证运行镜像或源码挂载。同步源代码本身不会切换不可变 release。
4. `test1`～`test10` 批量铺课是独立的数据操作，当前未执行。先确认目标账号和课程清单，再做可重复、逐账号可核对的导入脚本，在隔离环境验证后执行。

`README.md`、`PRD.md`、`PRD_BASELINE.md` 依 worktree 文档策略暂不更新；功能合并后再统一改写。
