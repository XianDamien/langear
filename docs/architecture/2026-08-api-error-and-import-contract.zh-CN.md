# LanGear v1 API 错误与导入契约

状态：已确认，2026-08-27

本文冻结所有 v1 API 共用的错误响应，以及 LanGear JSON/ZIP 导入边界。具体路由和完整 OpenAPI schema 在实现 issue 中补齐。

## 通用错误响应

所有非 2xx 业务响应使用同一个 envelope：

```json
{
  "error": {
    "code": "NOTE_REVISION_CONFLICT",
    "message": "The note was updated by another request.",
    "details": {},
    "request_id": "019..."
  }
}
```

- `code` 是稳定、全大写 snake case 的机器码，前端按它分支；
- `message` 用于日志和默认展示，不作为程序判断依据；
- `details` 保存字段错误、当前 revision 或影响统计等结构化上下文，无内容时为空对象；
- `request_id` 用于关联 Web、Worker 和日志。

HTTP 状态规则：

| HTTP | 使用场景 |
| --- | --- |
| `400` | 请求语法、查询表达式或 JSON 无法解析 |
| `401` | 未登录或 Session 失效 |
| `403` | 已认证但禁止执行已知的系统级操作，例如修改只读 Library |
| `404` | 资源不存在；所有跨 Collection 访问也统一返回 404，避免泄露资源存在性 |
| `409` | revision 冲突、不同内容的重复 Rating、幂等键负载冲突、状态转换冲突 |
| `413` | JSON/ZIP 或媒体超过限制 |
| `415` | 文件或媒体类型不支持 |
| `422` | 请求可解析，但字段或领域规则校验失败 |
| `429` | 速率或配额限制 |
| `500` | 未预期的服务端错误 |
| `503` | 当前依赖不可用且请求尚未被可靠接收 |

已成功创建 Attempt 或 Outbox 后，ASR/AI provider 失败不再通过原请求返回 `5xx`；失败状态和错误码写入同一 Attempt 的对应处理结果。相同幂等键和相同负载的重试返回原操作结果；相同幂等键但不同负载返回 `409 IDEMPOTENCY_KEY_REUSED`。

## v1 导入范围

v1 只支持 LanGear 自有 JSON 和 ZIP 导入。不提供 JSON/ZIP 导出，不支持 APKG，也不承担与 Anki 同步协议兼容。

两种格式共用同一个版本化 manifest：

- JSON：manifest 本身，只导入 Deck 层级、Note 和 Card 生成意图；不携带二进制媒体，也不能引用其他用户的私有 OSS object key；
- ZIP：根目录包含同一份 `manifest.json`，并可包含 manifest 引用的音频或图片文件；
- manifest 必须包含 `schema_version`；未知 major version 返回 `422 IMPORT_SCHEMA_UNSUPPORTED`；
- 每个 Deck 必须包含稳定 `deck_guid`，重复导入按 `(collection_id, deck_guid)` 找到原目标 Deck；本地改名不导致重复创建层级；
- v1 只接受系统 `Vocabulary` 和 `Sentence` NoteType/Card Template key，不创建或修改 NoteType/Template；
- 不导入 User、Collection、Session、Attempt、Rating、FSRS 状态、队列状态、Outbox 或运行历史；
- 导入目标始终是当前用户的 Collection，不能从文件指定其他 Collection ID；
- 包内路径必须是相对路径，不允许绝对路径或 `..` 路径穿越。

## 导入行为

导入先完整解析和校验 manifest、引用关系、媒体类型、大小和 checksum。ZIP 媒体先上传到临时命名空间，随后在一个数据库事务中写入全部 Deck、Note、Card 和 MediaAsset 引用并认领临时媒体；数据库事务失败时不产生部分业务数据，未认领临时对象按 TTL 清理。

幂等规则：

- Note 按 `(collection_id, guid)` 识别；
- Deck 按 `(collection_id, deck_guid)` 识别，不能只按可变的名称或路径识别；
- guid 不存在时创建 Note 和有效模板对应的 Card；
- guid 已存在时保留本地 Note 字段和已有 Card 所在 Deck，不覆盖、不移动；
- 对已有 Note 只补充 manifest 要求但当前缺失的 Card；
- 同一 package 重试不会创建重复 Note 或 Card；
- ZIP 媒体按 checksum 去重，私有媒体仍受 Collection scope 约束。

成功响应至少返回：

```json
{
  "decks_created": 0,
  "notes_created": 0,
  "notes_preserved": 0,
  "cards_created": 0,
  "media_created": 0,
  "media_reused": 0
}
```
