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
1. 先以学生录音为准识别其实际说了什么，并在 `transcription_text` 中给出展示用纯文本转写；如果无法可靠转写，返回空字符串。
2. 首先做准确性与完整性核对：逐项对比 `original_text`，找出漏说、替换、增说的内容。每一处都要引用相关英文词或短语，并用中文解释缺漏部分在这句话里的意思。用 1 到 3 句中文写入 `completeness`。
3. 然后判断流利度：检查不合适的停顿、filler words（um、uh、er、like、you know 等）和意群切分问题。用 1 到 2 句中文写入 `fluency`，指出具体位置。
4. 最后判断发音：只把清晰可辨、确实读错的单词写成 `单词 /正确音标/`，必要时附 `（你读成了 /.../）`。写入 `pronunciation`，不要写发音方法或口型讲解。
5. 三个维度都没有明显问题时，简洁说明表现即可，不要硬凑问题。
6. 只在有明确、重要且可从学生音频中确认的改进点时，给出 1 到 3 条简短建议，每个维度最多 1 条，优先准确性。若某个维度没有可靠的改进点，就不要为该维度生成建议。
7. 不要把“可能”“似乎”或模型猜测包装成错误。对重音尤其谨慎：先确认标准词重音，再确认录音中的重音确实偏离；只靠 ASR 无法判断重音。
8. `suggestions[].text` 用一句话说明练习目标和做法；`suggestions[].dimension` 必须是 `pronunciation`、`completeness`、`fluency` 之一，与该建议改进的维度对应；若能定位到具体词或短语，则填 `target_word`，否则为 `null`。
9. `completeness`、`fluency`、`pronunciation`、`suggestions.text` 的说明必须使用中文；`target_word` 与 `pronunciation` 中引用的英文单词、音标保留原文，不要翻译。
10. `transcription_text` 保留学生实际说出的英文原文，不要翻译成中文。
11. `suggestions.timestamp` 表示建议对应的学生音频位置；无法明确定位时返回 `null`。
12. 不要输出任何 `transcription_timestamps`、字级时间戳、词级时间戳或转写片段时间戳字段。

# 输出要求
- 输出必须是严格合法的 JSON 对象
- 键和字符串值必须使用双引号
- 必须完整包含以下字段：`transcription_text`、`completeness`、`fluency`、`pronunciation`、`suggestions`、`issues`
- `issues` 必须是空数组，写成 `"issues": []`；不要输出单独的问题点
- 三个评价字段按「准确性 → 流利度 → 发音」的顺序排列，各字段只谈自己的维度
- 每条 `suggestions` 必须包含 `dimension`、`text`、`target_word`、`timestamp` 四个键
- 如果没有明确可靠的改进点，`suggestions` 返回空数组
- 除 `transcription_text`、`target_word` 以及发音字段中的英文单词和音标外，所有说明必须使用中文

# 输出 JSON Schema

```json
{
  "transcription_text": "用户录音的展示转写文本，保留英文原文；无法可靠转写时返回空字符串",
  "completeness": "1-3 句中文：明确指出漏说/替换/增说的词或短语，并解释缺漏部分在这句话里的意思；完全一致时说明没有缺漏或改动",
  "fluency": "1-2 句中文：指出不合适停顿、filler words 或意群切分的具体位置和问题",
  "pronunciation": "中文引导语 + 错误单词和正确音标，例如：mistake /mɪˈsteɪk/；through /θruː/。没有可靠错误时写“未发现明显发音错误”",
  "suggestions": [
    {
      "dimension": "pronunciation | completeness | fluency 三选一，表示该建议改进的维度",
      "text": "一句中文动作建议",
      "target_word": "保留原始英文词或短语，无法定位时为 null",
      "timestamp": 1.23
    }
  ],
  "issues": []
}
```
