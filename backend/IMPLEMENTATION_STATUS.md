# LanGear Backend 实施状态报告

**版本**: v2.0 (异步架构)
**更新时间**: 2026-02-08
**状态**: ✅ 核心功能已完成，待测试

---

## ✅ 已完成的工作

### 阶段 1: 更新 Adapters（已完成）

#### 1. OSS Adapter (`app/adapters/oss_adapter.py`)
- ✅ 新增 `generate_sts_token()` - STS 临时凭证生成（AssumeRole）
- ✅ 新增 `generate_signed_url()` - 生成签名 URL（用于 ASR）
- ✅ 保留原有 `upload_audio()` 和 `get_url()` 方法

#### 2. ASR Adapter (`app/adapters/asr_adapter.py`)
- ✅ 从 Paraformer 迁移到 **qwen3-asr-flash** 模型
- ✅ 输入方式改为 OSS 签名 URL（不再是 base64）
- ✅ 返回格式包含：完整文本 + 词级时间戳
- ✅ 时间戳格式：`[{word, start, end}, ...]`

#### 3. Gemini Adapter (`app/adapters/gemini_adapter.py`)
- ✅ 移除 `overall_score` 数值评分
- ✅ 建议字段增加可选的 `timestamp`（关联到 ASR 时间戳）
- ✅ 新增 `_associate_timestamps()` 方法
- ✅ Prompt 模板支持时间戳关联

#### 4. ReviewLog 模型 (`app/models/review_log.py`)
- ✅ 新增 `status` 字段：processing/completed/failed
- ✅ 新增 `error_code` 字段：失败时的错误码
- ✅ 新增 `error_message` 字段：失败时的错误信息

### 阶段 2: 后台任务处理器（已完成）

#### `app/tasks/review_task.py`
- ✅ 实现异步处理逻辑：
  1. 生成 OSS 签名 URL
  2. ASR 转写（获取时间戳）
  3. Gemini 评测
  4. FSRS 更新
  5. 数据库事务写入
- ✅ 完整的异常处理（更新失败状态）
- ✅ 日志记录

### 阶段 3: Service 层（已完成）

#### 1. ReviewService (`app/services/review_service.py`)
- ✅ `submit_card_review()` - 提交训练（立即返回）
- ✅ `get_submission_result()` - 轮询获取结果
- ✅ 参数校验（rating、card、lesson、OSS 路径）
- ✅ 后台任务启动（threading）

#### 2. ContentService (`app/services/content_service.py`)
- ✅ `get_deck_tree()` - 获取教材树（sources -> units -> lessons）
- ✅ `get_lesson_cards()` - 获取课文卡片列表

#### 3. DashboardService (`app/services/dashboard_service.py`)
- ✅ `get_dashboard_stats()` - Dashboard 统计
- ✅ 连续学习天数计算
- ✅ 热力图生成（90天）

#### 4. SettingsService (`app/services/settings_service.py`)
- ✅ `get_settings()` - 读取系统配置
- ✅ `update_settings()` - 更新系统配置
- ✅ 配置校验

### 阶段 4: Router 层（已完成）

#### 1. Health Router (`app/routers/health.py`)
- ✅ `GET /health` - 健康检查

#### 2. OSS Router (`app/routers/oss.py`)
- ✅ `GET /api/v1/oss/sts-token` - 获取 STS 临时凭证

#### 3. Decks Router (`app/routers/decks.py`)
- ✅ `GET /api/v1/decks/tree` - 获取教材树
- ✅ `GET /api/v1/decks/{lesson_id}/cards` - 获取课文卡片

#### 4. Study Router (`app/routers/study.py`)
- ✅ `POST /api/v1/study/submissions` - 提交训练（异步）
- ✅ `GET /api/v1/study/submissions/{id}` - 轮询获取结果

#### 5. Dashboard Router (`app/routers/dashboard.py`)
- ✅ `GET /api/v1/dashboard` - Dashboard 统计

#### 6. Settings Router (`app/routers/settings.py`)
- ✅ `GET /api/v1/settings` - 读取配置
- ✅ `PUT /api/v1/settings` - 更新配置

### 阶段 5: 数据库迁移（已完成）

- ✅ 创建 `alembic.ini` 配置文件
- ✅ 初始化 Alembic migrations 目录
- ✅ 配置 `migrations/env.py`（导入所有模型）
- ✅ 生成初始迁移（包含 status 字段）
- ✅ 运行迁移创建数据库表

### 其他配置（已完成）

- ✅ 更新 `pyproject.toml`（添加 dashscope 和 STS 依赖）
- ✅ 创建 `app/main.py`（FastAPI 入口 + CORS）
- ✅ 更新 `app/config.py`（添加 OSS_REGION 和 ALIYUN_ROLE_ARN）
- ✅ 创建 `.env` 示例文件
- ✅ 启动测试通过

---

## ⏳ 待完成的工作

### 1. 数据种子脚本（1-2h）

**文件**: `scripts/seed_data.py`

需要实现：
- 从 `2_processed_output.old/archive_processed/` 导入种子数据
- 上传音频到 OSS（教材音频为 public-read）
- 创建 source/unit/lesson 层级结构
- 创建 cards（front_text, back_text, audio_path）

### 2. API 测试（2-3h）

**目录**: `tests/`

需要创建：
- `tests/test_oss.py` - STS token 生成测试
- `tests/test_study.py` - 异步训练流程测试
- `tests/test_decks.py` - 教材内容查询测试
- `tests/test_dashboard.py` - Dashboard 统计测试

重点测试场景：
- STS 凭证生成和权限验证
- 异步训练完整流程（提交 → 轮询 → 完成）
- ASR 时间戳返回格式
- Gemini 时间戳关联
- 失败场景（ASR 失败、Gemini 失败）

### 3. 环境变量配置

**需要真实配置的环境变量**：
```bash
GEMINI_API_KEY=          # 实际的 Gemini API 密钥
DASHSCOPE_API_KEY=       # 实际的 DashScope API 密钥
OSS_ACCESS_KEY_ID=       # 实际的 OSS AccessKey ID
OSS_ACCESS_KEY_SECRET=   # 实际的 OSS AccessKey Secret
OSS_ENDPOINT=            # OSS Endpoint
OSS_BUCKET_NAME=         # OSS Bucket 名称
OSS_PUBLIC_BASE_URL=     # OSS 公开访问基础 URL
OSS_REGION=              # OSS 区域（如 cn-shanghai）
ALIYUN_ROLE_ARN=         # RAM 角色 ARN（用于 STS）
```

### 4. 前端对接（前端团队）

前端需要实现：
1. 获取 STS 凭证 → 直传音频到 OSS
2. 提交训练请求 → 轮询获取结果
3. 显示 ASR 转写文本和时间戳
4. 点击建议跳转到音频对应位置

### 5. 课级总结功能（可选）

**文件**: `app/routers/decks.py`（新增端点）

```python
@router.get("/{lesson_id}/summary")
def get_lesson_summary(lesson_id: int, db: Session = Depends(get_db)):
    """获取课级总结（若未生成则触发生成）"""
    pass
```

需要实现：
- 检查课文是否全部完成
- 拉取该课文全部单句反馈
- 调用 Gemini 生成总结
- 持久化到 review_log（result_type='summary'）

---

## 🔧 已知问题和警告

### 1. 依赖警告
- **google-generativeai**: 官方建议迁移到 `google.genai`
  - 当前代码使用 `google.generativeai`
  - 功能正常，但未来可能停止维护
  - **建议**: 后续迁移到 `google.genai`

- **oss2**: SyntaxWarning（无效的转义序列）
  - 来自 oss2 库内部
  - 不影响功能
  - **影响**: 无

### 2. ASR API 格式未验证
- **qwen3-asr-flash** 的实际响应格式需要实测
- 当前实现基于文档推测
- **建议**: 使用真实音频测试并调整解析逻辑

### 3. STS AssumeRole 权限配置
- 需要在阿里云 RAM 中配置：
  1. 创建 RAM 角色（如 `LanGearOSSRole`）
  2. 角色信任策略允许当前账户 AssumeRole
  3. 角色权限策略允许 `oss:PutObject` 到 `recordings/*` 路径

---

## 📋 验收检查清单

### 核心功能
- [ ] STS 凭证生成成功（前端可用凭证上传）
- [ ] 异步训练流程完整（提交 → 处理 → 完成）
- [ ] ASR 返回词级时间戳
- [ ] Gemini 建议关联时间戳
- [ ] 失败场景正确处理（状态更新为 failed）

### API 端点
- [ ] GET /health
- [ ] GET /api/v1/oss/sts-token
- [ ] GET /api/v1/decks/tree
- [ ] GET /api/v1/decks/{lesson_id}/cards
- [ ] POST /api/v1/study/submissions
- [ ] GET /api/v1/study/submissions/{id}
- [ ] GET /api/v1/dashboard
- [ ] GET /api/v1/settings
- [ ] PUT /api/v1/settings

### 数据库
- [ ] 所有表创建成功（6张表）
- [ ] review_log 包含 status/error_code/error_message 字段
- [ ] 索引正确创建

---

## 🚀 启动命令

```bash
# 1. 安装依赖
cd backend
uv sync

# 2. 配置环境变量（编辑 .env）
nano .env

# 3. 运行数据库迁移
uv run alembic upgrade head

# 4. （可选）运行数据种子脚本
uv run python scripts/seed_data.py

# 5. 启动 API 服务
uv run uvicorn app.main:app --reload --port 8000

# 6. 访问 API 文档
# http://localhost:8000/docs
```

---

## 📊 项目结构概览

```
backend/
├── app/
│   ├── adapters/          # ✅ 外部服务封装
│   │   ├── oss_adapter.py       (STS + 签名 URL)
│   │   ├── asr_adapter.py       (qwen3-asr-flash + timestamps)
│   │   ├── gemini_adapter.py    (无评分 + timestamp 关联)
│   │   └── fsrs_adapter.py
│   ├── models/            # ✅ 数据库模型
│   ├── repositories/      # ✅ 数据访问层
│   ├── services/          # ✅ 业务逻辑层
│   ├── tasks/             # ✅ 后台任务处理器
│   ├── routers/           # ✅ API 路由层
│   ├── config.py          # ✅ 环境变量配置
│   ├── database.py        # ✅ 数据库配置
│   └── main.py            # ✅ FastAPI 入口
├── migrations/            # ✅ Alembic 迁移
├── scripts/               # ⏳ 数据种子（待实现）
├── tests/                 # ⏳ API 测试（待实现）
├── data/
│   └── langear.db         # ✅ SQLite 数据库
├── alembic.ini            # ✅ Alembic 配置
├── pyproject.toml         # ✅ 项目依赖
└── .env                   # ✅ 环境变量（需填真实值）
```

---

## 🎯 下一步行动

1. **配置真实环境变量**（重要）
   - 申请 Gemini API Key
   - 申请 DashScope API Key
   - 配置阿里云 OSS + STS 权限

2. **实现数据种子脚本**
   - 导入教材内容
   - 上传音频到 OSS

3. **端到端测试**
   - 真实音频上传测试
   - ASR + Gemini 异步流程测试
   - 时间戳跳转功能测试

4. **前后端联调**
   - STS 上传流程
   - 轮询结果展示
   - 时间戳跳转交互

---

**状态**: 🟢 核心功能已完成，可以开始测试和联调
