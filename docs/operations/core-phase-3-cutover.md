# Core 迁移第三阶段切换手册

状态：**本地代码收口已完成**；生产执行未开始（前置条件未满足，且未获得生产执行授权）
审计时间：2026-10-21
关联任务：仓库根目录的 `CORE_MIGRATION_PHASE_3_TODO.md`

本手册对应第三阶段 TODO 的“授权要求”：在生产备份、写入冻结、迁移和部署执行获得用户明确授权前，只生成发布计划、校验命令和验收清单。本文所有生产命令都标注了执行位置和授权门槛，不得把本文当作已执行记录。

## 0. 本轮结论

第三阶段**现在不能进入生产切换**，原因不是代码缺失，而是生产环境尚未具备 core 运行前置条件：

1. production 只有 legacy 数据库 `langear`，没有 core 数据库、`env/review.env`、`langear-prod-review` 网络或 `review-worker`。
2. staging 从未发布过 core-only（`runtime=core`）版本，也没有 `staging-approval.json`；当前 staging 固定版本是 `b3bfe5d` 的 `runtime=review`。
3. staging core 数据库 revision 为 `lan21_0010`，仓库 core migration head 为 `lan33_0011`，发布前必须先迁移。
4. 第二阶段 TODO 的 staging 备份、冻结、演练和业务验收仍未勾选；§6 的“打包后过渡路径测试”也未完成。
5. 用户尚未授予生产备份、冻结、迁移和部署执行权限。

因此生产切换仍不能开始。作为可离线完成的部分，本轮已在本分支完成仓库侧第三阶段清理：

- 删除 `backend/app/`、`backend/migrations/`、旧 Alembic 配置、legacy 测试和只依赖 `app` 的脚本。
- 删除 `/api/v1/auth/legacy`、`legacy_identity_url`、`legacy_selection` 和 `/review/legacy-lessons` 数字 ID 兼容接口。
- 发布工具只保留 `core` / `core-v1` 两种运行合同；`review` 和 `legacy` 运行时不再可构建。
- 使用本地隔离 PostgreSQL 跑通 core 全量测试，并用浏览器完成注册、四个主页面、建卡、Review 和评分确认。

仍按 TODO 保留的过渡能力：`/api/content` alias、旧 `/study/:lessonId` 与 `/summary/:lessonId` SPA 路由。它们必须等 production 稳定和 7 天零命中后再删除。

## 1. 当前状态审计

审计均为只读命令，未修改任何服务器。

| 项目 | 现状 | 证据 |
|---|---|---|
| 本地 `dev/staging` | `e5b9372`（第二阶段代码已合入） | `git log -1` |
| 本地 Phase 3 清理分支 | `codex/core-phase-3-cutover`；legacy 运行时、迁移和旧测试已删除 | `git log -1` |
| staging 固定版本 | `b3bfe5d`，`runtime=review` | `manage.py status staging` |
| staging 前端 API 前缀 | `/api/content/v1` | `frontend/Dockerfile` 默认值、manifest |
| staging legacy DB | `langear_dev`，revision `a8f2d4c6e9b1` | `alembic_version` |
| staging core DB | `langear-lan3132-test-postgres` / `review_integration_preview`，revision `lan21_0010` | `review.env`、`alembic_version` |
| staging core-only 验收记录 | 不存在 | `releases/b3bfe5d.../staging-approval.json` 缺失 |
| production legacy DB | `langear`，revision `a8f2d4c6e9b1` | `langear-prod-postgres` |
| production core DB | **不存在** | `pg_database` 只有 `langear`、`postgres` |
| production core env/网络 | **不存在**；`env/` 只有 `backend.env`、`postgres.env`、备份 | `ls /srv/langear/prod/env` |
| production 发布记录 | 无 `releases/current.json` | `/srv/langear/prod/releases` 不存在 |
| production 入口 | 主机 Nginx `:443` → `/srv/langear/prod/web/current`，`/api/` → `127.0.0.1:8000` | `/etc/nginx/sites-enabled/langear-frontend` |

## 2. 发布合同

| runtime | 前端 API base | 后端入口 | 后端前缀 | 用途 |
|---|---|---|---|---|
| `core`（Release A） | `/api/content/v1` | `core.core_only:app` | `/api/v1` = core，`/api/content` = core alias | 首个 core-only 生产版本 |
| `core-v1`（Release B） | `/api/v1` | `core.core_only:app` | `/api/v1` = core，保留 `/api/content` alias | 正式前缀切换 |

`legacy` 和 `review` 合同已在仓库侧删除，不能再用 CI 或 `package.py` 构建。staging 上正在运行的 `b3bfe5d`（`runtime=review`）只是历史发布记录，不是可回滚目标。

说明：Release B 的后端入口仍是 `core.core_only:app`，因为该入口同时提供 `/api/v1` 和待删除的 `/api/content` alias。第三阶段第 5 节删除 alias 时，再把入口收敛为 `core.main:app`，避免在切换窗口内同时改动入口和路径。

`core` 与 `core-v1` 都要求 `collection-core-pytest`；manifest 不再接受 `backend-pytest`，且发布工具会同时检查 `/api/v1/auth/me` 与 `/api/content/v1/auth/me` 返回 401。

## 3. 硬件与授权门槛

执行以下任何一项前，必须取得用户对**当次**操作的明确授权，并记录授权人、时间、窗口和回滚联系人。

- production 数据库备份
- production 写入冻结
- production 数据迁移（reconcile `--apply`）
- production release Promote `--execute`
- production Nginx/Compose 修改与 reload

未授权时只允许执行：`status`、只读 SQL、快照导出到受保护目录（不含任何写库操作）、`promote --sha`（不带 `--execute`）和本文中的校验命令。

## 4. 阶段 1：生产切换准备

### 4.1 确认 staging 证据和目标 SHA

```bash
# Mac，仓库根目录
python3 scripts/release/manage.py status staging
```

必须看到：

- `state.mode = release`
- `state.runtime = core`（不是 `review`）
- `state.sha` 与待推广 SHA 一致
- `image_id`、`db_revision`、`core_db_revision` 与 staging 实际一致
- `releases/<SHA>/staging-approval.json` 存在且 `checks` 非空

当前不满足：runtime 是 `review`，且没有 approval 文件。先完成第二阶段 §5–§7，不得跳到第三阶段。

### 4.2 生产 core 数据库预备（尚未执行）

production 需要独立 PostgreSQL 实例或独立数据库，且满足发布工具约定：

- 容器名建议：`langear-prod-core-postgres`
- 网络必须为 `langear-prod-review`（`host.py` 的 `core_revision()` 和 overlay 固定使用该名称）
- env 文件必须为 `/srv/langear/prod/env/review.env`
- `CORE_DATABASE_URL` 必须是 `postgresql+psycopg://...`
- `CORE_CONFIRMATION_SECRET` 至少 32 字符
- `CORE_ALLOWED_ORIGINS` 显式列出生产 origin，不允许 `*`
- `CORE_COOKIE_SECURE=true`
- 其余键按 staging `env/review.env` 对齐（AI、OSS、Dialogue、ASR）

参考键名（不含值）：

```text
CORE_DATABASE_URL CORE_CONFIRMATION_SECRET CORE_ALLOWED_ORIGINS CORE_COOKIE_SECURE
CORE_DIALOGUE_* CORE_AI_FEEDBACK_* CORE_GEMINI_API_KEY CORE_GEMINI_MODEL_ID
GOOGLE_GEMINI_BASE_URL CORE_QWEN_OMNI_* CORE_OSS_* CORE_UPLOAD_PREFIX
CORE_ASR_API_KEY CORE_REALTIME_ASR_*
```

所有运行配置以 `CORE_` 前缀为准；`GOOGLE_GEMINI_BASE_URL` 是唯一保留的无前缀别名。

在候选镜像上显式执行 core migration（不得由 Web 启动代跑）：

```bash
# production，授权后执行
CORE_IMAGE=langear-release:<RELEASE_SHA_A>
docker run --rm --network langear-prod-review \
  --env-file /srv/langear/prod/env/review.env \
  --entrypoint alembic "$CORE_IMAGE" -c alembic-core.ini upgrade head
```

### 4.3 备份与只读快照

```bash
# production，授权后执行
CUT=/srv/langear/cutover/$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 700 "$CUT"

# legacy 备份
docker exec langear-prod-postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$CUT/legacy.dump"

# core 备份（core 数据库就绪后）
docker exec langear-prod-core-postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$CUT/core.dump"

sha256sum "$CUT"/*.dump | tee "$CUT/backup.sha256"
# 验证备份可读，不还原
docker exec -i langear-prod-postgres pg_restore -l < "$CUT/legacy.dump" >/dev/null
docker exec -i langear-prod-core-postgres pg_restore -l < "$CUT/core.dump" >/dev/null
```

只读快照必须使用版本控制中已审阅的导出脚本，并在生产机校验脚本 SHA256 后再运行：

```bash
# Mac：获取已批准提交中的脚本并记录校验值
shasum -a 256 backend/scripts/export_legacy_core.py

# 复制到生产受保护目录（不要覆盖应用代码）
scp backend/scripts/export_legacy_core.py langear-prod:"$CUT/export_legacy_core.py"

# production
python3 "$CUT/export_legacy_core.py" --environment prod \
  --output "$CUT/legacy-snapshot.json"
```

导出脚本使用 `REPEATABLE READ READ ONLY` 事务；`--environment prod` 只接受名称包含 `prod` 的容器，防止误读 staging。

记录不可变快照的 checksum 和 high-water mark。checksum 与 high-water 必须使用与最终协调完全相同的实现：

```bash
docker run --rm \
  --network langear-prod-review \
  --env-file /srv/langear/prod/env/review.env \
  -v "$CUT:/cutover:ro" \
  --entrypoint python langear-release:<RELEASE_SHA_A> -c \
  'import json; from core.reconcile import high_water, snapshot_checksum; data = json.load(open("/cutover/legacy-snapshot.json")); print(json.dumps({"checksum": snapshot_checksum(data), "high_water": high_water(data)}, sort_keys=True))'
```

把输出写入 `$CUT/snapshot.meta.json`，并在 apply 前再次运行；两次输出必须完全一致。

### 4.4 迁移 dry-run

以下命令使用已在 staging 验收的 Release A 镜像。dry-run 前必须先把该镜像 `docker load` 到 production（不切换服务），这一步同样需要生产授权。更保守的做法是把快照复制到隔离环境，用同一镜像和独立 core 数据库演练，再在生产执行只读 preflight。

在 production 快照上先跑只读 preflight，不传 `--apply`：

```bash
# production，使用候选 core 镜像
docker run --rm --network langear-prod-review \
  --env-file /srv/langear/prod/env/review.env \
  -v "$CUT:/cutover:ro" \
  --entrypoint python langear-release:<RELEASE_SHA_A> \
  -m core.reconcile /cutover/legacy-snapshot.json --source final
```

通过条件：

- 输出 `conflicts` 为空
- `snapshot_checksum` 与 4.3 记录的 checksum 一致
- `daily_activity.accounted` 守恒
- 报告不含密码、token 或媒体签名

### 4.5 差异审核清单

逐项审核并签字：

- [ ] 邀请码数量、使用次数、耗尽状态
- [ ] 用户数量、用户名/邮箱唯一性、禁用状态、密码哈希来源
- [ ] Collection 设置、`default_deck_scope`、时区、学习步长
- [ ] Deck / Note / Card 数量、层级、`imported` 与 `source_metadata`
- [ ] Media 引用、缺失 asset、缺失 reference 均为 0
- [ ] membership（`in_my_courses`）与选卡范围
- [ ] 学习状态（due、interval、steps、FSRS memory）
- [ ] 每日活动去重结果：归档行数 = 归属行数 + 拒绝行数
- [ ] 所有冲突都有显式决策记录

### 4.6 回滚与观察窗口

执行前必须批准并记录：

- [ ] 回滚触发条件（错误率、认证失败、队列失败、WebSocket 中断、连接耗尽）
- [ ] 观察窗口（建议至少 24 小时；alias 删除前连续 7 天）
- [ ] RTO（建议 ≤ 30 分钟）
- [ ] RPO：**已提交的 core 写入固定为 0**；只允许丢失冻结后、切换前未提交的 legacy 写入
- [ ] 只能继续写 core 的回滚 release SHA（Release A）及其兼容 schema revision 范围
- [ ] 回滚后不得重新启用 legacy 写入，不得恢复 legacy 数据库为可写

## 5. 阶段 2：执行生产数据切换

### 5.1 写入冻结

```bash
# production，授权后执行
sudo cp /etc/nginx/sites-enabled/langear-frontend \
        /etc/nginx/sites-enabled/langear-frontend.pre-cutover
```

在 legacy `/api/` location 前加入维护拦截（只拒绝写请求和 WebSocket 升级，保留健康检查与迁移管理读取）：

```nginx
map $http_upgrade $ws_upgrade { default 0; "~*^websocket$" 1; }
map "$request_method:$ws_upgrade" $legacy_write {
    default 0;
    "~^POST:" 1; "~^PUT:" 1; "~^PATCH:" 1; "~^DELETE:" 1;
    "~:1$" 1;
}

server {
    location /api/ {
        if ($legacy_write) { return 503; }
        # 原有 proxy_pass 配置保持不变
    }
}
```

```bash
sudo nginx -t && sudo nginx -s reload
```

同时：

- [ ] 拒绝 legacy 注册、设置、课程选择、Study submission、ASR session
- [ ] 停止/排空后台任务：legacy 没有持久队列，但有 `review_service` 线程；等待在途请求完成
- [ ] 终止仍会写旧库的活跃 session/WebSocket（legacy `/api/v1/realtime/asr/ws` 直接返回 503）
- [ ] 确认 5 分钟内 legacy 写请求数为零（Nginx access log 过滤 `POST|PUT|PATCH|DELETE`）

### 5.2 最终备份与快照

重复 4.3 的全部步骤，生成 `$CUT/final/`。冻结后 checksum 必须稳定；若两次导出 checksum 不同，中止。

### 5.3 最终协调与核对

```bash
# preflight（只读）
docker run --rm --network langear-prod-review \
  --env-file /srv/langear/prod/env/review.env \
  -v "$CUT/final:/cutover:ro" \
  --entrypoint python langear-release:<RELEASE_SHA_A> \
  -m core.reconcile /cutover/legacy-snapshot.json --source final

# apply（单事务，失败整批回滚）
docker run --rm --network langear-prod-review \
  --env-file /srv/langear/prod/env/review.env \
  -v "$CUT/final:/cutover:ro" \
  --entrypoint python langear-release:<RELEASE_SHA_A> \
  -m core.reconcile /cutover/legacy-snapshot.json --source final --apply

# verify（只读）
docker run --rm --network langear-prod-review \
  --env-file /srv/langear/prod/env/review.env \
  -v "$CUT/final:/cutover:ro" \
  --entrypoint python langear-release:<RELEASE_SHA_A> \
  -m core.reconcile /cutover/legacy-snapshot.json --source final --verify
```

中止条件：

- preflight 存在未解决冲突
- 源 checksum 在 apply 前后变化
- apply 报告 `SNAPSHOT_CHANGED`
- verify 的 `replicated`、`missing_assets`、`missing_references` 不为通过值
- 数量核对与 4.5 的批准结果不一致

### 5.4 抽样验证

- [ ] 既有用户名账号登录（密码哈希来自 legacy）
- [ ] 既有邮箱账号登录
- [ ] 课程加入/退出状态与 legacy 一致
- [ ] 一张卡片的 due、interval、steps、FSRS 状态与快照一致
- [ ] Dashboard 今日新卡/复习数与快照学习状态吻合

### 5.5 legacy 转只读

```bash
# production，授权后执行；不删除数据，只撤销写权限
docker exec langear-prod-postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
   -c "ALTER DATABASE \"$POSTGRES_DB\" SET default_transaction_read_only = on"'
```

不得继续双写。回滚 release 也只能写 core。

## 6. 阶段 3/4：Release A → Release B

### 6.1 生成 Release A

```bash
# Mac
gh workflow run frontend-dev-deploy.yml --ref <已批准分支> \
  -f runtime=core -f api_base_url=/api/content/v1
gh run list --workflow frontend-dev-deploy.yml --limit 5
python3 scripts/release/manage.py stage --run <RUN_ID_A>
```

staging 验收后记录证据：

```bash
python3 scripts/release/manage.py approve --checks '<登录、Dashboard、课程、Review、上传、ASR、AI feedback、Dialogue、alias 路径>'
python3 scripts/release/manage.py promote --sha <SHA_A>       # 仅计划
# 获得生产授权后
python3 scripts/release/manage.py promote --sha <SHA_A> --execute
```

Release A 后端健康后，立即从 Nginx 移除 5.1 的 `$legacy_write` 写拦截并 reload；否则 core 的写请求仍会收到 503。维护窗口到此结束。

Release A 的 Nginx 必须增加 alias 路由（生产主机 `langear-frontend`）：

```nginx
location /api/content/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
}
```

验证：

- [ ] Release A 前端（`/api/content/v1`）+ Release A 后端
- [ ] Release A 前端 + Release B 后端（alias 仍可用）
- [ ] 不存在前端先发、后端后发的窗口
- [ ] `/api/v1/auth/me`、`/api/content/v1/auth/me` 均返回 401
- [ ] cookie `Path` 分别为 `/api/v1` 与 `/api/content/v1`
- [ ] CSRF、CORS、WebSocket upgrade 均通过

### 6.2 生成 Release B

```bash
gh workflow run frontend-dev-deploy.yml --ref <已批准分支或 SHA> \
  -f runtime=core-v1 -f api_base_url=/api/v1
python3 scripts/release/manage.py stage --run <RUN_ID_B>
python3 scripts/release/manage.py approve --checks '<Release B 验收步骤>'
python3 scripts/release/manage.py promote --sha <SHA_B>       # 仅计划
# 获得生产授权后
python3 scripts/release/manage.py promote --sha <SHA_B> --execute
```

Release B 明确接受一次强制重新登录，并清理旧 `/api/content/v1` path cookie。在 Release B 的 Nginx `/api/` location 中临时加入过期指令：

```nginx
location /api/ {
    add_header Set-Cookie "langear_core_session=; Path=/api/content/v1; Max-Age=0; HttpOnly; Secure; SameSite=Lax" always;
    # 原有 proxy_pass 配置保持不变
}
```

该指令只清除旧 path cookie，不影响新 `/api/v1` cookie；alias 删除时必须一并移除。

验证：

- [ ] `/api/v1/auth/me` 正常
- [ ] `/api/content/v1/auth/me` 仍返回 401（alias 保留）
- [ ] 旧 `/api/content/v1` cookie 在响应头中被 `Max-Age=0` 清除
- [ ] 用户完成一次重新登录
- [ ] WebSocket `/api/v1/realtime/asr/ws` 与 `/api/v1/dialogue/sessions/{id}/ws` 正常
- [ ] 回滚目标固定为已批准的 `<SHA_A>`

### 6.3 24 小时 legacy 业务路由零调用

Release A 上线后，除健康检查和迁移管理请求外，连续 24 小时确认 production legacy 业务路由调用为零。仓库中 legacy 独占前缀为：

```text
/api/v1/my-courses
/api/v1/user-decks
/api/v1/study
/api/v1/oss
/api/v1/realtime
```

```bash
sudo zgrep -hE '"(GET|POST|PUT|PATCH|DELETE) /api/v1/(my-courses|user-decks|study|oss|realtime)' \
  /var/log/nginx/access.log* | wc -l
```

结果必须为 `0`。`/api/v1/decks`、`/api/v1/dashboard`、`/api/v1/settings` 由 legacy 与 core 共用，需按第二阶段盘点结果和请求形态人工复核。

### 6.4 alias 退场

`/api/v1` 稳定且 `/api/content/v1` 连续 7 天无业务请求后：

```bash
rg -n "api/content|content-api" /var/log/nginx/access.log*
```

命中数为零后，删除 Nginx `/api/content/` location、后端 alias 和 cookie path rewrite。此步骤属于第 5 节，未授权不得执行。

## 7. 阶段 5/6/7：清理状态

已在本地仓库完成（不涉及 production）：

- [x] 删除 `backend/app/`、`backend/migrations/`、旧 Alembic 配置和 `app/release.py`
- [x] 删除 `/auth/legacy`、`legacy_identity_url`、legacy token 验证
- [x] 删除 `legacy_selection.py`、`/review/legacy-lessons` 和数字 ID 兼容接口
- [x] 删除 legacy 专属测试、fixture、mock、`test-backend.sh`
- [x] 删除 `legacy` / `review` 运行时合同和 manifest 的 `backend-pytest` 检查

仍需 Release B 稳定且 7 天等待期结束后执行：

- [ ] 删除 `backend/core/release_app.py`、`backend/core/core_only.py`，入口收敛为 `core.main:app`
- [ ] 删除 `/api/content`、`/content-api` 代理和 cookie path rewrite
- [ ] 删除旧 `/study/:lessonId`、`/summary/:lessonId` 路由（各自连续 7 天命中为零后）

完成清理后的回归命令：

```bash
rg 'VITE_CONTENT_CORE|VITE_LIBRARY_CONTENT_EDITOR|libraryContent|auth/legacy|legacy-lessons|/api/content|content-api|app\.release' frontend backend scripts
```

当前该命令仍会命中 `/api/content` alias 和旧 SPA 路由的过渡代码，属预期；第 5 节剩余项完成后必须无结果。

收口检查：

- [x] 运行配置只有一个数据库 URL（`CORE_DATABASE_URL`）
- [x] 只有一套迁移 head（`lan33_0011`）
- [ ] 只有一个后端启动入口（目前仍是 `core.core_only:app`，alias 删除后收敛）
- [x] core 后端全量测试、迁移测试通过（本地 236 passed）
- [x] 前端单测、类型检查、构建、lint 通过
- [x] release tooling 测试通过
- [ ] 实际执行一次 artifact 回滚和前滚，证明不回退旧库、不丢 core 写入

## 8. 回滚

应用回滚只切换已验证 artifact，不恢复数据库备份。

```bash
python3 scripts/release/manage.py rollback prod             # 计划
python3 scripts/release/manage.py rollback prod --execute   # 授权后
```

- Release B 的回滚目标固定为 `<SHA_A>`。
- Release A 的回滚目标只能是更早的 core-only 版本。`legacy` / `review` 运行时已删除，发布工具会拒绝回滚到 pre-core artifact。
- 数据库备份恢复仅用于数据库灾难，需要单独授权。
- 回滚后 legacy 数据库保持只读。

RTO / RPO 按 4.6 的批准值执行；已提交 core 写入的 RPO 为 0。

## 9. 证据记录模板

```text
cutover_id:
authorized_by:
authorized_at:
freeze_start / freeze_end:
legacy_snapshot_checksum:
legacy_revision:
core_revision:
release_a_sha / image_id:
release_b_sha / image_id:
preflight_conflicts:
apply_report:
verify_report:
sampling_results:
observation_window:
rollback_target_sha:
rto_actual:
rpo_actual:
incidents:
```

## 10. 本轮代码变更

- 删除 `backend/app/`、`backend/migrations/`、旧 Alembic 配置、legacy 测试和只依赖 `app` 的脚本。
- 删除 `/api/v1/auth/legacy`、`legacy_identity_url`、`legacy_selection`、`/review/legacy-lessons` 和 `make_release_app`。
- 保留 `core.core_only:app` 与 `/api/content` alias，等 7 天等待期后删除。
- `scripts/release/host.py`、`package.py` 只接受 `core` / `core-v1`；manifest 不再要求 `backend-pytest`，只要求 `collection-core-pytest`。
- CI 工作流支持 `workflow_dispatch` 的 `runtime` / `api_base_url` 输入，并校验二者组合；push/PR 默认 `core` + `/api/content/v1`。
- `backend/scripts/export_legacy_core.py` 支持 `--environment staging|prod`，并拒绝跨环境容器名。
- `test-core.sh` 固定 `PGTZ=UTC`，避免本地非 UTC PostgreSQL 造成学习日期断言漂移。

本地验证结果：

- core PostgreSQL 全量测试：236 passed。
- release tooling：18 passed。
- 前端 Vitest：116 passed；`vue-tsc` 与 `vite build` 通过；lint 0 error。
- 浏览器功能确认：注册、Dashboard、题库资源、我的课程、设置、建卡、Review 显示答案与评分全部通过，无未捕获页面错误。
