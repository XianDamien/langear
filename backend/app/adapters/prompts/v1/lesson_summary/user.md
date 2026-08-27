# 输入数据

### 1. `feedbacks_json`
```json
{feedbacks_json}
```

# 处理指令
1. 阅读所有单句反馈，判断整节课表现最稳定的优点和最突出的短板。
2. `overall` 写成 1 段简洁总结。
3. `patterns` 只保留重复出现的共性问题或优势，不要罗列零散现象。
4. `prioritized_actions` 必须是学生下一轮练习时可以直接执行的动作建议。

# 输出要求
- 输出必须是严格合法的 JSON 对象
- 键和字符串值必须使用双引号
- 必须完整包含 `overall`、`patterns`、`prioritized_actions`

# 输出 JSON Schema

```json
{
  "overall": "overall performance summary",
  "patterns": ["recurring pattern 1", "recurring pattern 2"],
  "prioritized_actions": ["highest priority action", "second priority action"]
}
```
