# 输入数据

### 1. `original_text`
```text
{original_text}
```

### 2. `reference_audio_url`
```text
{reference_audio_url}
```

### 3. `user_audio_url`
```text
{user_audio_url}
```

说明：
- 第 1 段音频是标准参考音频。
- 第 2 段音频是学生录音。
- URL 仅作为输入标识；你需要重点比较两段音频内容与 `original_text`。

# 处理指令
1. 先识别学生实际说了什么，并在 `transcription_text` 中给出简洁纯文本转写；如果无法可靠转写，返回空字符串。
2. 再分别生成 `pronunciation`、`completeness`、`fluency` 三段简洁反馈，每段聚焦最关键的问题或优点。
3. 提取最多 5 个具体问题写入 `issues`。
4. 提取最多 3 个最值得优先改进的建议写入 `suggestions`。
5. `suggestions.text` 必须是可直接练习的动作建议；若能定位到具体词或短语，则填 `target_word`，否则为 `null`。

# 输出要求
- 输出必须是严格合法的 JSON 对象
- 键和字符串值必须使用双引号
- 必须完整包含以下字段：`transcription_text`、`pronunciation`、`completeness`、`fluency`、`suggestions`、`issues`
- 如果某类问题不存在，返回空数组，不要省略字段

# 输出 JSON Schema

```json
{
  "transcription_text": "optional transcription of user audio in plain text, or empty string",
  "pronunciation": "text feedback",
  "completeness": "text feedback",
  "fluency": "text feedback",
  "suggestions": [
    {
      "text": "actionable suggestion",
      "target_word": "word or phrase if applicable, otherwise null",
      "timestamp": 1.23
    }
  ],
  "issues": [
    {
      "problem": "specific issue description",
      "timestamp": 1.23
    }
  ]
}
```
