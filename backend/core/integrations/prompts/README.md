# Prompt Versioning

Prompt templates are versioned by folder name and organized by task.

## Structure

- `v1/single_feedback/system.md`
- `v1/single_feedback/user.md`
- `v1/single_feedback/metadata.json`
- `v1/lesson_summary/system.md`
- `v1/lesson_summary/user.md`
- `v1/lesson_summary/metadata.json`

This follows the same pattern used in `quickfire_workflow/prompts`:
- `system.md`: stable role, rules, and guardrails
- `user.md`: runtime input template and output schema
- `metadata.json`: prompt version, ownership, and changelog

## How to create a new version

1. Copy the current version directory, for example `v1` to `v2`.
2. Edit prompt files in `v2/<task>/`.
3. Update `GEMINI_PROMPT_VERSION=v2` in backend config to activate it.

Git history tracks all prompt diffs between versions.
