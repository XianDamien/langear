# Gemini Prompt Eval Datasets

本目录用于本地离线评测，不用于线上运行时读写。
线上真源始终是 `DATABASE_URL` 指向数据库中的 `review_log` / `user_card_srs`，OSS 只保存音频文件。

约定结构：

```text
backend/datasets/gemini_single_feedback_eval/
  dataset_manifest.json
  sample_index.jsonl
  samples/<sample_id>/
    metadata.json
    input.json
    source_output.json
    user_audio.*
    reference_audio.*
  runs/<run_id>/
    run_manifest.json
    comparison.json
    variants/<variant_name>/
      prompt_snapshot/
      results.jsonl
      samples/<sample_id>.json
  exports/<timestamp>_export.json
```

- `samples/` 保存固定输入与来源元数据，是 prompt A/B 对比时的控制变量基线。
- `samples/` 允许两类样本共存：
  - `ready_for_eval=true`：包含用户录音和参考音频，可直接跑 prompt eval
  - `ready_for_eval=false`：只有文本和参考音频，先作为 reference-only 本地归档
- `source_output.json` 保存导出时已有的历史产物，可作为人工参考，不等同于 gold label。
- `runs/` 保存每次离线评测的输入快照、prompt 快照和输出结果，便于回放与对比。
- `dataset_manifest.json` 的 `dataset_role=offline_snapshot`，并在 `last_export.source_database` 中记录最近一次导出使用的数据库来源，避免把本目录误认成线上真源。
