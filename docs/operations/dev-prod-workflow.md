# LanGear 开发与生产环境

更新时间：2026-10-15。

## 日常开发：本地前端直接经 FRP 连接 staging

```bash
cd frontend
pnpm dev
```

浏览器打开 `http://localhost:3002`。默认配置在版本控制中，新 checkout/worktree 和 `pnpm dev:staging` 也使用同一目标：

```text
浏览器 localhost:3002/api/v1/…
  → 本地 Vite proxy
  → https://8.159.139.145:7145/api/v1/…
  → FRP → staging Nginx → dev backend → 独立 dev PostgreSQL
```

不需要额外建立 SSH 隧道。`VITE_API_BASE_URL=/api/v1` 是前端请求路径；`VITE_DEV_PROXY_TARGET=https://8.159.139.145:7145` 是代理目标 origin，不要把 `/api/v1` 再拼进 target。Vite 只对这个已知自签名 staging 目标跳过证书校验。浏览器通过本地同源代理访问 API，不需额外配置 API 跨域；WebSocket 也经过该代理。

不要把公网绝对 URL 直接写进浏览器的 API base，除非另行处理跨域和浏览器证书信任。公网预览 `https://8.159.139.145:7145` 可以直接访问，首次需要接受自签名证书。它是构建后的静态前端，不是本地 Vite 热重载页面。OSS CORS 已包含公网预览 origin 和 localhost:3002。

`.env.development.local` 和进程变量可覆盖默认值，排查连接目标时检查二者。本地 `18000` 是历史生产隧道；若显式选择该端口，必须同时设置 `LANGEAR_ALLOW_PROD_PROXY=1`，只用于明确的生产排查。Vite 固定使用 `3002`，端口冲突会报错，不自动漂移。需要私有 SSH 方式时仍可显式使用 `18004 → staging:8004`，但它不是默认依赖。

## 后端开发与测试

| 环境 | 主机/路径 | 用途 |
|---|---|---|
| prod | `ssh langear-prod`，`/srv/langear/prod/repo` | 正式用户；发布固定镜像 |
| dev | `ssh zhaohui-staging-server`，`/home/kemove/langear/dev/repo` | 后端源码、热重载、独立 PostgreSQL |
| 本地 | Mac `frontend/` | Vite 与浏览器，无需 Docker |

staging 的 SSH 经 FRP 网关 `8.159.139.145:20224`，实际开发机器为 `kemove-G292-Z20-00`。Remote SSH 打开 `/home/kemove/langear/dev/repo`。开发 Compose 位于 `/home/kemove/langear/dev/compose/docker-compose.yml`，将 backend 挂载到 `/workspace/backend`，Python 环境位于 `/app/.venv`。

```bash
# 在 staging 查看开发容器
cd /home/kemove/langear/dev
docker compose -f compose/docker-compose.yml ps
./compose/test-backend.sh -q
```

核心测试使用隔离 PostgreSQL。仓库入口为 `scripts/release/test-core.sh`：设置 `CORE_TEST_DATABASE_URL` 指向一次性 `lan30_test_*` 数据库，在 backend 目录执行。脚本会固定 `PGTZ=UTC` 并清空继承的应用凭据。不要直接用真实数据库运行 pytest。

app 源码修改会热重载；依赖变更需重建开发镜像。每任务 worktree/容器/端口/数据库隔离仍是待办，当前共享 dev 一次只允许一个任务独占运行，创建 worktree 本身不会切换 Compose 挂载。

## 发布：同一提交、同一套产物

`.github/workflows/frontend-dev-deploy.yml` 已改为 **Verify and Package Release**。PR、main push 或手动触发只执行测试和构建，不直接部署服务器。保留原文件名是为了替换旧的前端单独发布任务。

CI 必须全部通过：后端隔离 pytest、前端 Vitest、类型检查与构建、发布工具测试。它将同一 Git SHA 的前端 tar、后端 Docker 镜像 tar、镜像 ID 和文件 SHA256 打成一个 `langear-release-<完整 SHA>` artifact。`/release.json` 标识前端版本，镜像 revision label 标识后端版本。后端代码变化也会触发流水线。

以下命令在具有 GitHub 登录和两个 SSH alias 的 Mac 仓库根目录执行；不向 staging 复制 GitHub 私钥。

```bash
# 如需手动构建某个已推送分支
gh workflow run frontend-dev-deploy.yml --ref <分支>
gh run list --workflow frontend-dev-deploy.yml

# 使用成功的 main push 或 workflow_dispatch run ID 部署 staging
python3 scripts/release/manage.py stage --run <RUN_ID>
```

部署使用固定镜像覆盖 staging backend 源码挂载，前后端一并切换；等待健康检查，验证前端 SHA 和 API 鉴权。此时公网 IP 预览与本地 Vite 代理都访问该验收版本，**后端源码热重载暂停**。不要与其他开发任务同时操作。PR 的临时合并提交不直接用于发布。

```bash
# 检查当前镜像、前端目录、迁移版本和发布记录
python3 scripts/release/manage.py status staging

# 在公网预览完成登录、课程、学习、录音上传/ASR 等实际验收后记录证据
python3 scripts/release/manage.py approve --checks '<实际完成的验收步骤和结果>'

# 生成生产发布计划；此命令不修改生产服务器
python3 scripts/release/manage.py promote --sha <完整 SHA>

# 获得本次生产发布授权后执行，复用 staging 验收的原始产物，不重新构建
python3 scripts/release/manage.py promote --sha <完整 SHA> --execute
```

生产发布必须匹配 staging 的产物哈希、镜像 ID 和验收记录。不发布未提交源码，不分别从浮动分支重建前后端，也不将 dev 数据覆盖到 prod。旧 checkout 不会因固定镜像发布自动更新；运行版本以 `releases/current.json`、镜像 ID 和前端 `/release.json` 为准，不能只看 repo HEAD。

每次发布保存上一版镜像、前端目录和迁移版本。应用部署失败会尝试恢复前后端；成功发布后也可显式回滚：

```bash
python3 scripts/release/manage.py rollback staging
# 生产回滚先查看计划，经授权再加 --execute
python3 scripts/release/manage.py rollback prod
python3 scripts/release/manage.py rollback prod --execute

# 结束 staging 固定版本验收，恢复源码挂载和热重载
python3 scripts/release/manage.py dev
```

恢复开发模式保留最后的静态前端预览；日常前端仍使用本地 Vite。`compose/release.override.yml` 由发布脚本管理，处于验收/生产发布模式时，不要绕过脚本用 base Compose 单独重建 backend，否则会丢失固定版本选择。

发布过程中没有跨前后端的原子事务，单实例切换可能有短暂中断；失败时恢复上一版。数据库迁移**不会自动执行或回滚**：候选代码的 Alembic heads 必须等于当前数据库版本，否则发布中止；需单独准备数据库备份、迁移和恢复步骤。数据库版本改变后，脚本拒绝自动回滚应用。首次遗留版本可以作为回滚目标，后续版本均记录明确 SHA。

产物和记录位于各环境根目录 `releases/<SHA>/`。重复安装同一 SHA 会拒绝覆盖，避免破坏原始产物、验收证据和回滚记录。CI artifact 保留 30 天；已上传的服务器产物不随 GitHub artifact 到期删除，清理需保留当前版和回滚版。

## 基线与数据

迁移基线为当时 main/prod `179f83dd4945953930a196836556d26b95124b44`；原 prod backend 镜像为 `sha256:9e436c8f5aa317d1cb9e76abcf9eb872e2b17370cbccd12c90f440bae8602098`。按用户要求复制 prod 数据到独立 `langear_dev`，Alembic `a8f2d4c6e9b1`，保留账号密码哈希与学习数据，数据库凭据及 token 签名密钥独立。旧 dev 分支和数据保留。后续数据刷新必须是明确任务，不自动同步。

新录音写入 `dev/staging/recordings`，历史内容可能引用原 prod OSS 对象；AI/OSS 凭据仍共享。env、备份和凭据不进 Git。

staging 暂无 GitHub SSH 权限；在 staging 提交功能后，Mac 使用 `git fetch staging-dev dev/staging` 获取并审阅，通过 GitHub 集成流程发布。`staging-dev` 指向 `ssh://zhaohui-staging-server/home/kemove/langear/dev/repo`。

## 旧环境

- `/srv/langear/dev/repo`、端口 `8001`：旧 dev，保留数据，不作为日常入口。
- staging `/home/kemove/langear/repo` 和旧 `langear-staging-*`：更早的停用环境。
- `dev.langear.cn` 指向另一台旧前端，不作为新 dev 入口。
- `round-one` 是独立实验环境，不在本次发布流程内。
- 既有 FRP SSH 和其他服务保持原配置；新开发不依赖旧 `17110` 业务隧道。
