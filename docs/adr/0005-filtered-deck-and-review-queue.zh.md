# 筛选牌组(Filtered Deck)与运行时复习队列

状态:已接受

筛选牌组(Filtered Deck)将卡片从它们的标准牌组(Standard Deck)临时移出,同时保留原始放置数据,以便卡片无需单独的成员关系表即可归还。一张卡片同一时刻最多只能属于一个筛选牌组。复习队列是运行时状态:系统可以在内存或 Redis 中维护一个短生命周期的卡片 ID 队列,并在丢失时重建;它不持久化学习会话(Study Session)或队列表。卡片内容仍由当前的笔记与卡片模板动态渲染。

Filtered Deck 的 search terms 定义查询、数量上限和排序规则。Rebuild 会创建有序的运行时 Card ID 队列；本次 build 的主顺序保持稳定，分钟级 learning Card 可以按到期时刻动态插回。不同于 Anki 持久化 `due`/`odue` 位置的编码方式，LanGear 不向 Card 写入 Filtered Deck 排序位置或原始 due；只有实际 Rating 触发重新调度时才修改正式调度字段。

v1 在 Filtered Deck 中复习时始终正式重新调度 Card，不提供 Preview 模式，也不持久化 `preview_repeat` queue。

卡片存储 Anki 风格的 `type` 与 `queue` 值,包括用于挂起(suspended)与搁置(buried)状态的负队列值。集合时区决定学习日的分界;绝对时间戳以 UTC PostgreSQL `timestamptz` 值存储。
