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
1. 先识别学生实际说了什么，并在 `transcription_text` 中给出展示用纯文本转写；如果无法可靠转写，返回空字符串。
2. 分别用一句话写出 `pronunciation`、`completeness`、`fluency` 三个维度的评价，没有明显问题时简洁说明表现即可。
3. 只在有明确、重要且可从学生音频中确认的改进点时，给出 1-2 条简短建议。若没有可靠的改进点，返回空数组。
4. 不要把“可能”“似乎”或模型猜测包装成错误。对重音尤其谨慎：先确认标准词重音，再确认录音中的重音确实偏离；只靠 ASR 无法判断重音。
5. `suggestions[].text` 用一句话说明练习目标和做法；`suggestions[].dimension` 必须是 `pronunciation`、`completeness`、`fluency` 之一，与该建议改进的维度对应；若能定位到具体词或短语，则填 `target_word`，否则为 `null`。
6. `pronunciation`、`completeness`、`fluency`、`suggestions.text` 必须使用中文输出，不要用英文写反馈。
7. `target_word` 必须保留原始英文词或英文短语，不要翻译成中文。
8. `transcription_text` 保留学生实际说出的英文原文，不要翻译成中文。
9. `suggestions.timestamp` 表示建议对应的学生音频位置；无法明确定位时返回 `null`。
10. 不要输出任何 `transcription_timestamps`、字级时间戳、词级时间戳或转写片段时间戳字段。

# 输出要求
- 输出必须是严格合法的 JSON 对象
- 键和字符串值必须使用双引号
- 必须完整包含以下字段：`transcription_text`、`pronunciation`、`completeness`、`fluency`、`suggestions`、`issues`
- `issues` 必须是空数组，写成 `"issues": []`；不要输出单独的问题点
- `pronunciation`、`completeness`、`fluency` 各用简短的一句话概述，没有明显问题时简洁说明表现即可，不要重复建议内容
- 每条 `suggestions` 必须包含 `dimension`、`text`、`target_word`、`timestamp` 四个键
- 如果没有明确可靠的改进点，`suggestions` 返回空数组
- 除 `transcription_text` 与 `target_word` 外，所有字符串值必须使用中文

# 输出 JSON Schema

```json
{
  "transcription_text": "用户录音的展示转写文本，保留英文原文；无法可靠转写时返回空字符串",
  "pronunciation": "发音维度的一句话中文评价",
  "completeness": "内容完整度维度的一句话中文评价",
  "fluency": "流利度维度的一句话中文评价",
  "suggestions": [
    {
      "dimension": "pronunciation | completeness | fluency 三选一，表示该建议改进的维度",
      "text": "中文动作建议",
      "target_word": "保留原始英文词或短语，无法定位时为 null",
      "timestamp": 1.23
    }
  ],
  "issues": []
}
```
