# Domain Docs

This repository uses a single-context layout rooted at the repository root.

Preferred lookup order:
1. `CONTEXT.md`
2. `docs/adr/`

Current state:
- `CONTEXT.md` is present at the repository root
- `docs/adr/` is not present yet

Use `CONTEXT.md` first for repository-level domain vocabulary and product language. When ADRs are absent, use `AGENTS.md`, `README.md`, `PRD.md`, and `PRD_BASELINE.md` as supporting context.

If the repository later adopts multiple context roots, replace this setup with a `CONTEXT-MAP.md` based layout.
