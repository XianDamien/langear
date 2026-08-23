# PostgreSQL 与 UUIDv7

状态:已接受

PostgreSQL 是开发、预发布(staging)与生产环境共用的数据库;数据库结构能力按 PostgreSQL 设计,而非 SQLite。核心实体使用应用生成的 UUIDv7 标识符。核心私有表带有 `collection_id`,复合外键强制笔记、卡片、牌组、练习记录与媒体引用都停留在同一个集合之内。

生产环境使用显式的迁移任务、带 WAL/PITR 的自动化 PostgreSQL 备份,以及按环境隔离的数据库/OSS 命名空间。第一版不启用 PostgreSQL 行级安全(Row-Level Security);集合范围内的应用模块与数据库约束提供初始的隔离层。
