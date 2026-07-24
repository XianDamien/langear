# Issue Tracker

LanGear uses Linear as its issue tracker rather than GitHub Issues.

Default workspace: `LanGear0` (`langear0`)
Default team key: `LAN`
Default project: `LanGear`
Default project queue: `https://linear.app/langear0/project/langear-bb9f8fd94119/issues`

For LanGear issue management, use the project-level `managing-langear` skill over generic GitHub issue workflows.

Project Linear scope:
- Workspace name: `LanGear0`
- Workspace URL key: `langear0`
- Team key: `LAN`
- Team name: `LanGear0`
- Team all view: `https://linear.app/langear0/team/LAN/all`
- Default project: `LanGear`
- Default project URL: `https://linear.app/langear0/project/langear-bb9f8fd94119/issues`
- Default project slug ID: `bb9f8fd94119`
- Credential path: `~/.linear/config`
- API approach: reuse the `meeting-to-linear` GraphQL client and scripts

Use this workflow when the task involves:
- checking for existing LanGear issues
- deciding whether to create a new issue, update an existing issue, or add a comment
- turning discussions, notes, transcripts, or media into issue drafts
- updating issue descriptions, status, priority, or comments
- preparing or sending LanGear issue notification emails

Default operating rule:
1. Check for duplicates and related existing issues first
2. Decide whether the work belongs in a new issue, an existing issue, or a comment
3. Produce a draft before writing
4. Do not write to Linear until the user explicitly confirms
