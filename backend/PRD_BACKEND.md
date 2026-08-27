# LanGear 后端实施文档（FastAPI 版本）

## 0. 文档定位
- 本文档定义 LanGear 后端实现规格，可直接用于 AI 生成 FastAPI 代码。
- 本文档是 `PRD.md` 的后端落地子文档。
- 版本：v2.0（2026-02-08）- 异步架构版本。
- 范围：Python + FastAPI + SQLAlchemy + SQLite（单库）+ uv + 异步任务处理。

## 1. 技术栈与运行规范

### 1.1 技术栈
- Python 3.11+
- FastAPI + Uvicorn
- SQLAlchemy 2.x（ORM，async 可选）
- SQLite（单库，文件路径 `backend/data/langear.db`）
- fsrs `>=6.3.0`（pip 包，不内嵌源码）
- google-genai（Gemini API SDK，用于 AI 多模态评测）
- dashscope `>=1.25.6`（阿里云 DashScope SDK，用于 qwen3-asr-flash-realtime）
- oss2（阿里云 OSS SDK，用于音频文件存储和 STS 凭证）
- alembic（数据库迁移）
- 后台任务：Python threading 或 asyncio（异步处理 AI 评测）

### 1.2 包管理与命令规范（必须使用 uv）
- 安装依赖：`uv sync`
- 本地启动：`uv run uvicorn app.main:app --reload --port 8000`
- 运行测试：`uv run pytest`
- 数据库迁移：`uv run alembic upgrade head`
- 数据种子：`uv run python scripts/seed_data.py`

### 1.3 环境变量（通过 `.env` 配置，禁止硬编码）
```
# AI 服务
GEMINI_API_KEY=           # Gemini API 密钥
DASHSCOPE_API_KEY=        # 阿里云 DashScope API 密钥（用于 qwen3-asr-flash）

# 阿里云 OSS
OSS_ACCESS_KEY_ID=        # OSS AccessKey ID
OSS_ACCESS_KEY_SECRET=    # OSS AccessKey Secret
OSS_BUCKET_NAME=          # OSS Bucket 名称
OSS_ENDPOINT=             # OSS Endpoint（如 oss-cn-shanghai.aliyuncs.com）
OSS_PUBLIC_BASE_URL=      # OSS 公开访问基础 URL（用于教材音频）
ALIYUN_ROLE_ARN=          # 阿里云 RAM 角色 ARN（用于 STS AssumeRole）

# 数据库与服务
DATABASE_URL=sqlite:///data/langear.db
CORS_ORIGINS=http://localhost:5173
```

## 2. 模块边界

### 2.1 Router 层
负责 HTTP 协议处理、参数校验、响应封装，不包含业务逻辑。

### 2.2 Service 层
负责业务编排，包括训练提交流程、AI 反馈生成、FSRS 更新、总结触发。

### 2.3 Repository 层
负责数据库读写，屏蔽 SQL 细节。

### 2.4 ASR Adapter 层
封装阿里云 DashScope 语音识别调用。
- 使用 **qwen3-asr-flash** 模型（HTTP API）。
- 输入方式：OSS 签名 URL（后端生成 1 小时有效期的签名 URL）。
- 返回格式：完整转写文本 + 词级时间戳（word-level timestamps）。
- 时间戳用于前端实现音频片段跳转功能（用户点击建议→跳转到对应位置重听）。
- 配置选项：`enable_itn=False`（保留原始格式，便于对比原文）。
- 失败时抛出 `ASRTranscriptionError` 异常。

### 2.5 AI Evaluation Adapter 层
封装 Google Gemini 多模态调用与响应解析，输出统一结构。
- 模型：`gemini-3.0-pro-preview`。
- 单句反馈输入：原文文本（`front_text`）+ 用户转写文本（ASR 结果）。
- 课级总结输入：本课全部单句反馈 JSON 数组。
- 输出：固定结构化 JSON（**不包含数值评分**，仅文字反馈）。
- Prompt 模板存储在 `app/adapters/prompts/` 目录下，便于独立调整。
- 超时时间：60 秒。
- 失败时抛出 `AIFeedbackError` 异常。

### 2.6 OSS Adapter 层
封装阿里云 OSS 文件访问与 STS 临时凭证生成。
- **STS AssumeRole**：使用 RAM 角色通过 STS 获取临时凭证（有效期 1 小时）。
- **前端上传**：提供 API 返回 STS 临时凭证，前端直接上传音频到 OSS。
- **后端下载**：后端使用 STS 凭证从私密 bucket 下载音频（用于 ASR）。
- 用户录音路径格式：`recordings/{date}/{card_id}_{timestamp}.wav`。
- 教材音频为公开访问（public-read），用户录音为私有（通过 STS 访问）。

### 2.7 FSRS Adapter 层
封装评分到复习状态的计算与映射逻辑。使用 `fsrs` pip 包（`>=6.3.0`）。

## 3. 全局约束
- 管理员单用户模式，默认使用固定管理员上下文。
- **异步处理原则**：音频上传和 AI 评测均为异步，不阻塞用户操作。
- **轮询机制**：前端通过轮询获取 AI 评测结果（能显示就显示，超时不阻塞）。
- 所有接口统一输出 `request_id` 便于排障。
- 单句反馈与课级总结必须持久化到 `review_log`。
- FSRS 更新必须在 AI 评测完成后执行（保证数据一致性）。

## 4. API 设计（MVP）

## 4.1 通用响应结构
成功响应：
```json
{
  "request_id": "uuid",
  "data": {}
}
```

失败响应：
```json
{
  "request_id": "uuid",
  "error": {
    "code": "AI_FEEDBACK_FAILED",
    "message": "AI 单句反馈生成失败"
  }
}
```

## 4.2 OSS 临时凭证接口（新增）

### `GET /api/v1/oss/sts-token`
用途：前端获取 STS 临时凭证用于直接上传音频到 OSS。

响应 `data`：
```json
{
  "access_key_id": "STS.xxx",
  "access_key_secret": "xxx",
  "security_token": "xxx",
  "expiration": "2026-02-08T12:00:00Z",
  "bucket": "langear",
  "region": "oss-cn-shanghai"
}
```

说明：
- 凭证有效期：1 小时
- 权限范围：仅限 `recordings/*` 路径的上传权限（PutObject）
- 前端使用此凭证通过 OSS SDK 直接上传音频

## 4.3 内容与导航接口

### `GET /api/v1/decks/tree`
用途：获取 `source -> unit -> lesson` 树。

响应 `data`：
```json
{
  "sources": [
    {
      "id": 1,
      "title": "新概念英语第二册",
      "units": [
        {
          "id": 11,
          "title": "Unit 1",
          "lessons": [
            {
              "id": 111,
              "title": "Lesson 1",
              "total_cards": 24,
              "completed_cards": 8,
              "due_cards": 5
            }
          ]
        }
      ]
    }
  ]
}
```

### `GET /api/v1/decks/{lesson_id}/cards`
用途：获取课文卡片列表（按 `card_index` 升序）。

响应 `data`：
```json
{
  "lesson_id": 111,
  "cards": [
    {
      "id": 1001,
      "card_index": 1,
      "front_text": "...",
      "back_text": "...",
      "audio_path": "oss://..."
    }
  ]
}
```

## 4.4 训练提交接口（异步架构：AI 反馈与评分解耦）

### `POST /api/v1/study/submissions`
用途：提交单卡训练请求（异步），立即返回 submission_id，并尽快产出 ASR+AI 反馈。

**当前口径（重要）**：
- 本接口用于触发 **ASR + Gemini 反馈生成**，与用户评分（again/hard/good/easy）解耦。
- 用户评分不会影响 AI 反馈生成结果；评分仅用于 FSRS 调度与学习统计（另见 `/rating` 接口）。

**流程变更**：
1. 前端先通过 STS 凭证上传音频到 OSS
2. 前端提交训练请求（传 OSS 路径）
3. 后端立即返回 submission_id（不等待 AI 评测）
4. 后端异步处理：下载音频 → ASR 转写 → Gemini 评测（尽快产出反馈）
5. 前端轮询获取结果
6. 前端在用户评分时提交 rating（用于 FSRS 更新）

请求体：
```json
{
  "lesson_id": 111,
  "card_id": 1001,
  "oss_audio_path": "recordings/20260208/1001_1707382800.wav"
}
```

响应 `data`（立即返回）：
```json
{
  "submission_id": 9001,
  "status": "processing"
}
```

错误码：
- `INVALID_OSS_PATH`
- `CARD_NOT_FOUND`

### `GET /api/v1/study/submissions/{submission_id}`
用途：轮询获取训练结果。

响应 `data`（处理中）：
```json
{
  "submission_id": 9001,
  "status": "processing",
  "progress": "asr_completed"
}
```

响应 `data`（已完成）：
```json
{
  "submission_id": 9001,
  "status": "completed",
  "result_type": "single",
  "transcription": {
    "text": "Hello world this is a test",
    "timestamps": [
      {"word": "Hello", "start": 0.0, "end": 0.5},
      {"word": "world", "start": 0.6, "end": 1.0},
      {"word": "this", "start": 1.1, "end": 1.3},
      {"word": "is", "start": 1.4, "end": 1.5},
      {"word": "a", "start": 1.6, "end": 1.7},
      {"word": "test", "start": 1.8, "end": 2.2}
    ]
  },
  "feedback": {
    "pronunciation": "发音评估文字...",
    "completeness": "完整度评估文字...",
    "fluency": "流畅度评估文字...",
    "suggestions": [
      {
        "text": "建议1：注意 'world' 的发音",
        "target_word": "world",
        "timestamp": 0.6
      },
      {
        "text": "建议2：提升整体流畅度",
        "target_word": null,
        "timestamp": null
      }
    ]
  },
  "oss_audio_path": "recordings/20260208/1001_1707382800.wav"
}
```

说明：
- `srs` 字段在评分解耦后将不再由该接口返回；SRS 更新由评分提交接口返回。

### `POST /api/v1/study/submissions/{submission_id}/rating`
用途：为已创建的 submission 提交用户评分（again/hard/good/easy），用于 FSRS 调度更新。

请求体：
```json
{
  "rating": "good"
}
```

响应 `data`：
```json
{
  "submission_id": 9001,
  "rating": "good",
  "srs": {
    "state": "review",
    "difficulty": 5.8,
    "stability": 12.3,
    "due": "2026-02-08T08:00:00Z"
  }
}
```

**时间戳字段说明**：
- `transcription.text`：完整转写文本
- `transcription.timestamps`：词级时间戳数组（word, start, end）
- `feedback.suggestions[].timestamp`：建议关联的时间戳（可选，用于跳转到具体位置）

响应 `data`（失败）：
```json
{
  "submission_id": 9001,
  "status": "failed",
  "error_code": "ASR_TRANSCRIPTION_FAILED",
  "error_message": "ASR 转写失败：超时"
}
```

状态枚举：
- `processing` - 处理中
- `completed` - 已完成
- `failed` - 失败

错误码（异步阶段）：
- `ASR_TRANSCRIPTION_FAILED` - ASR 转写失败
- `AI_FEEDBACK_FAILED` - AI 评测失败
- `SRS_UPDATE_FAILED` - FSRS 更新失败

## 4.5 课级总结接口

### `GET /api/v1/decks/{lesson_id}/summary`
用途：获取课级总结。若尚未生成且课文已完成，触发生成并持久化。

响应 `data`：
```json
{
  "lesson_id": 111,
  "result_type": "summary",
  "summary": {
    "overall": "...",
    "patterns": ["..."],
    "prioritized_actions": ["..."]
  }
}
```

错误码：
- `LESSON_NOT_COMPLETED`
- `SUMMARY_GENERATION_FAILED`
- `DB_WRITE_FAILED`

## 4.6 Dashboard 与配置接口

### `GET /api/v1/dashboard`
用途：返回任务与学习统计。

响应 `data`：
```json
{
  "today": {
    "new_limit": 20,
    "review_limit": 100,
    "completed": 36
  },
  "streak_days": 7,
  "heatmap": [
    { "date": "2026-02-05", "count": 18 }
  ]
}
```

### `GET /api/v1/settings`
用途：读取系统配置。

### `PUT /api/v1/settings`
用途：更新系统配置。

请求体：
```json
{
  "daily_new_limit": 20,
  "daily_review_limit": 100,
  "default_source_scope": [1, 2]
}
```

错误码：
- `INVALID_SETTINGS`
- `DB_WRITE_FAILED`

## 5. 核心流程（时序）

### 5.1 前端录音上传流程（新增）
1. 前端调用 `GET /api/v1/oss/sts-token` 获取临时凭证。
2. 前端使用 OSS SDK + STS 凭证直接上传音频到 OSS。
3. 上传完成后获取 OSS 路径（如 `recordings/20260208/1001_xxx.wav`）。

### 5.2 单卡训练提交流程（异步架构）

**同步阶段（立即返回）**：
1. 接收请求：`lesson_id`, `card_id`, `rating`, `oss_audio_path`。
2. 校验参数有效性（卡片存在、rating 合法、OSS 路径格式正确）。
3. 创建 `review_log` 记录（状态=`processing`）。
4. **立即返回** `submission_id` 和 `status=processing`。
5. 启动后台任务处理异步逻辑。

**异步阶段（后台任务）**：
1. 使用 OSS SDK 生成音频文件的签名 URL（1 小时有效期）。
2. 调用 **qwen3-asr-flash**（HTTP API）传入签名 URL 进行转写：
   ```python
   messages = [
       {"role": "user", "content": [{"audio": oss_signed_url}]}
   ]
   response = dashscope.MultiModalConversation.call(
       model="qwen3-asr-flash",
       messages=messages,
       asr_options={"enable_itn": False}
   )
   ```
3. 解析 ASR 响应，提取完整文本和词级时间戳（word-level timestamps）。
4. 查询卡片原文（`front_text`）。
5. 将原文 + 转写文本发送至 Gemini，生成单句反馈（**无数值评分，仅文字反馈**）。
6. 可选：Gemini 返回的建议中关联时间戳（通过关键词匹配 ASR timestamps）。
7. 按评分调用 FSRS 计算新状态。
8. 在事务中更新：
   - `review_log`：更新状态为 `completed`，写入 `ai_feedback_json`（包含 transcription + timestamps + feedback + oss_path）
   - `user_card_srs`：更新 state/stability/difficulty/due
9. 任一步骤失败，更新 `review_log` 状态为 `failed`，记录错误信息。

**前端轮询流程**：
1. 提交后每隔 1-2 秒调用 `GET /api/v1/study/submissions/{submission_id}`。
2. 根据 status 判断：
   - `processing` → 继续轮询（显示加载动画）
   - `completed` → 显示反馈结果和时间戳跳转功能
   - `failed` → 显示错误提示
3. 超时策略：轮询 30 秒后仍未完成，前端停止轮询但不阻塞（后台继续处理）。

### 5.3 课文总结流程
1. 检查课文是否全部卡片完成。
2. 拉取该课文全部 `single` 反馈。
3. 调用 Gemini 生成课级总结。
4. 写入 `review_log`（`result_type=summary`，`card_id=null`）。
5. 返回总结结果。

### 5.4 FSRS 更新流程
1. 读取 `user_card_srs` 现状（不存在则初始化）。
2. 将 `rating` 映射为 FSRS 评分。
3. 计算新 `state/stability/difficulty/due`。
4. 覆盖写回 `user_card_srs`。

## 6. 错误处理策略
- 所有错误必须可追踪（`request_id` + 结构化错误码）。
- **异步错误处理**：
  - 前端上传 OSS 失败 → 不提交训练请求
  - ASR 转写失败 → `review_log` 状态改为 `failed`，返回错误码
  - AI 评测失败 → `review_log` 状态改为 `failed`，FSRS 不更新
  - FSRS 更新失败 → 记录错误，但不影响反馈展示
- **轮询超时策略**：
  - 前端轮询 30 秒后超时 → 停止轮询，显示"处理中，请稍后查看"
  - 后台任务继续执行，完成后用户可在历史记录中查看结果

## 7. 数据模型约束（接口层）
- `rating` 仅允许：`again/hard/good/easy`。
- `result_type` 仅允许：`single/summary`。
- `deck_id` 必须指向 `lesson` 类型节点。
- `summary` 记录必须满足：`card_id = null` 且 `deck_id != null`。
- **新增 `status` 字段（review_log 表）**：
  - `processing` - 处理中
  - `completed` - 已完成
  - `failed` - 失败
- **新增 `error_code` 和 `error_message` 字段**（失败时记录）。

## 8. 观测与日志
- 每个请求记录：`request_id`、接口路径、耗时、错误码。
- 关键事件日志：
  - 单句反馈生成成功/失败
  - 课级总结生成成功/失败
  - FSRS 更新成功/失败

## 9. MVP 验收测试（后端）

### 9.1 STS 临时凭证测试
1. `GET /api/v1/oss/sts-token` 返回有效的临时凭证。
2. 前端使用凭证可成功上传音频到 OSS `recordings/` 目录。

### 9.2 异步训练流程测试
1. `POST /api/v1/study/submissions` 立即返回 `submission_id` 和 `status=processing`。
2. `GET /api/v1/study/submissions/{id}` 初始返回 `processing` 状态。
3. 后台任务成功完成后，轮询返回 `completed` 状态 + 完整结果（transcription + timestamps + feedback）。
4. ASR 失败时，轮询返回 `status=failed` + `error_code=ASR_TRANSCRIPTION_FAILED`。
5. Gemini 失败时，轮询返回 `status=failed` + `error_code=AI_FEEDBACK_FAILED`。
6. 成功时 `review_log` 和 `user_card_srs` 同时更新。

### 9.3 时间戳功能测试
1. ASR 返回的 `transcription.timestamps` 包含完整的词级时间戳。
2. Gemini 建议中的 `timestamp` 字段正确关联到对应的词。

### 9.4 其他接口测试
1. `GET /api/v1/decks/tree` 稳定返回三层结构。
2. `GET /api/v1/decks/{lesson_id}/cards` 返回卡片列表（按 card_index 排序）。
3. 课文完成后 `GET /api/v1/decks/{lesson_id}/summary` 返回并持久化 `summary`。
4. `GET /api/v1/dashboard` 返回今日任务、连续天数、热力图。

## 10. 项目结构规范

```text
backend/
  pyproject.toml
  alembic.ini
  .env                      # 环境变量（不提交到 git）
  app/
    __init__.py
    main.py                  # FastAPI 入口，CORS 配置，路由注册
    config.py                # 环境变量读取（Pydantic Settings）
    database.py              # SQLAlchemy engine/session 配置
    models/                  # SQLAlchemy ORM 模型
      user.py
      deck.py
      card.py
      user_card_srs.py
      review_log.py
      setting.py
    routers/
      health.py              # 健康检查
      oss.py                 # OSS STS 临时凭证（新增）
      decks.py               # 教材树与卡片列表
      study.py               # 训练提交与结果轮询
      dashboard.py           # Dashboard 统计
      settings.py            # 系统配置
    services/
      content_service.py     # 教材内容服务
      review_service.py      # 训练提交服务（异步）
      dashboard_service.py   # Dashboard 服务
      settings_service.py    # 设置服务
    tasks/                   # 后台任务处理（新增）
      __init__.py
      review_task.py         # 异步训练任务处理器
    adapters/
      oss_adapter.py         # 阿里云 OSS + STS
      asr_adapter.py         # qwen3-asr-flash（DashScope）
      gemini_adapter.py      # Gemini 多模态评测
      fsrs_adapter.py        # FSRS 调度
      prompts/
        single_feedback.txt  # 单句反馈 prompt 模板
        lesson_summary.txt   # 课级总结 prompt 模板
    repositories/
      deck_repo.py
      card_repo.py
      review_log_repo.py
      srs_repo.py
      settings_repo.py
  scripts/
    seed_data.py             # 数据种子脚本
  data/
    langear.db               # SQLite 数据库文件（运行时生成）
    seeds/                   # 种子数据 JSON 文件
      nce2.json              # 新概念英语第二册
      ielts_listening.json   # 剑桥雅思听力
  migrations/                # Alembic 迁移目录
  tests/
    conftest.py
    test_decks.py
    test_study.py
    test_dashboard.py
    test_settings.py
```

## 11. CORS 配置
本地开发时前端运行在 `http://localhost:5173`（Vite 默认端口），后端运行在 `http://localhost:8000`。`app/main.py` 必须配置 CORS：
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 12. 健康检查接口

### `GET /health`
用途：服务健康状态检查。
响应：
```json
{
  "status": "healthy",
  "timestamp": "2026-02-08T10:00:00Z"
}
```

## 13. 数据种子
`scripts/seed_data.py` 读取 `data/seeds/` 下的 JSON 文件，按以下格式写入数据库：
```json
{
  "source": {
    "title": "新概念英语第二册",
    "units": [
      {
        "title": "Unit 1",
        "lessons": [
          {
            "title": "Lesson 1 - A Private Conversation",
            "cards": [
              {
                "front_text": "Last week I went to the theatre.",
                "back_text": "上周我去了剧院。",
                "audio_path": "https://bucket.oss-cn-shanghai.aliyuncs.com/audio/nce2/u1/l1/s01.mp3"
              }
            ]
          }
        ]
      }
    ]
  }
}
```
音频文件需预上传至 OSS。种子脚本仅负责写入数据库元数据。

## 14. 实施顺序建议

### 阶段 1：项目初始化（1h）
1. 配置 pyproject.toml 依赖：fastapi, uvicorn, sqlalchemy, fsrs, google-generativeai, dashscope, oss2, alembic, pytest。
2. 建立 FastAPI 项目骨架、SQLAlchemy 模型（6 张表 + status/error 字段）、统一错误模型、CORS 配置。
3. 配置 Alembic 并创建初始迁移。

### 阶段 2：外部服务 Adapters（3h）
1. 实现 OSS Adapter：
   - STS AssumeRole 临时凭证生成
   - 签名 URL 生成（用于 ASR）
2. 实现 ASR Adapter：
   - qwen3-asr-flash HTTP API 调用
   - 解析 transcription + timestamps
3. 实现 Gemini Adapter：
   - 单句反馈生成（无数值评分）
   - Prompt 模板支持
4. 实现 FSRS Adapter（评分映射和调度）。

### 阶段 3：数据种子与基础接口（2h）
1. 编写数据种子脚本（从 LanProcessor 输出导入）。
2. 实现内容查询接口：
   - `GET /api/v1/decks/tree`
   - `GET /api/v1/decks/{lesson_id}/cards`

### 阶段 4：核心异步训练流程（4h）
1. 实现 STS 临时凭证接口：`GET /api/v1/oss/sts-token`。
2. 实现训练提交接口（同步部分）：
   - `POST /api/v1/study/submissions`（立即返回 submission_id）
3. 实现后台任务处理器：
   - OSS 签名 URL 生成
   - qwen3-asr-flash 转写（获取 timestamps）
   - Gemini 评测
   - FSRS 更新
   - 数据库事务写入
4. 实现轮询接口：`GET /api/v1/study/submissions/{id}`。

### 阶段 5：课级总结与 Dashboard（2h）
1. 实现课级总结接口：`GET /api/v1/decks/{lesson_id}/summary`。
2. 实现 Dashboard 和 Settings 接口。

### 阶段 6：测试与联调（2h）
1. 编写 pytest 验收测试（覆盖异步流程）。
2. 前后端联调：
   - 前端 STS 上传流程
   - 轮询获取结果流程
   - 时间戳跳转功能
