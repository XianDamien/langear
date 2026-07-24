---
name: managing-langear
description: Manage LanGear Linear issues for the LanGear0/langear0 Linear workspace and team LAN. Use this whenever the user asks about LanGear tickets, Linear issues, active work, issue triage, creating or updating tasks, converting plans into Linear issues, or checking LAN issues, even if they only say "issue", "ticket", "任务", "Linear", or "LAN".
---

# Managing LanGear

Manage LanGear work in Linear using the project-level defaults for this repo.

## Scope

- Workspace name: `LanGear0`
- Workspace URL key: `langear0`
- Team key: `LAN`
- Team name: `LanGear0`
- Team all view: `https://linear.app/langear0/team/LAN/all`
- Default project: `LanGear`
- Default project URL: `https://linear.app/langear0/project/langear-bb9f8fd94119/issues`
- Default project slug ID: `bb9f8fd94119`
- API credential: `~/.linear/config`
- API path: reuse the `meeting-to-linear` GraphQL client and scripts, not GitHub Issues

## Prerequisites

Before calling Linear, verify the API key exists without printing it:

```bash
test -s ~/.linear/config
```

If it is missing, tell the user to create a Linear personal API key and save only the raw token:

```bash
mkdir -p ~/.linear
echo 'lin_api_xxxxxx' > ~/.linear/config
chmod 600 ~/.linear/config
```

The shared Linear helper lives at:

```text
/Users/damien/.agents/skills/meeting-to-linear/scripts/linear_graphql.py
```

Use it by adding that scripts directory to `sys.path`:

```python
import sys
sys.path.insert(0, "/Users/damien/.agents/skills/meeting-to-linear/scripts")
from linear_graphql import LinearGraphQL
client = LinearGraphQL()
```

## Operating Rules

1. Read Linear first before creating or updating anything.
2. Default every query and write to team key `LAN`.
3. Bind new LanGear issues to the `LanGear` project by default, unless the user explicitly asks for team-only issues or a different project.
4. Treat the `LanGear` project issue list as the default issue queue. Use the team all view when the user asks for team-level LAN issues.
5. Check for duplicates and related issues before creating new issues.
6. Draft proposed creates or updates for the user to review.
7. Do not create, update, close, assign, relabel, or comment on a Linear issue until the user explicitly confirms the exact action.
8. Use the default triage labels from `docs/agents/triage-labels.md` when a skill asks for triage vocabulary.
9. Do not use GitHub Issues for LanGear task tracking.

## Common Queries

### Check Access And Defaults

Use this to verify that the token can see the `LanGear0` workspace, `LAN` team, and `LanGear` project.

```bash
python3 - <<'PY'
import sys
sys.path.insert(0, "/Users/damien/.agents/skills/meeting-to-linear/scripts")
from linear_graphql import LinearGraphQL

client = LinearGraphQL()
team = client.get_team_by_name("LAN")
if not team:
    raise SystemExit("LAN team not found")

data = client.execute("query Org { organization { name urlKey } }")
org = data["organization"]
project = client.get_project_by_name("LanGear")

print(f"workspace={org['name']} url_key={org['urlKey']}")
print(f"team={team['name']} key={team['key']} id={team['id']}")
print(f"project={project['name']} slug={project['slugId']} id={project['id']}" if project else "project=LanGear not found")
PY
```

### List LAN Issues

The existing helper's `get_issues()` can list recent LAN issues. For open/active work, filter terminal states client-side.

```bash
python3 - <<'PY'
import sys
sys.path.insert(0, "/Users/damien/.agents/skills/meeting-to-linear/scripts")
from linear_graphql import LinearGraphQL

client = LinearGraphQL()
issues = client.get_issues(team_key="LAN", limit=50)
terminal = {"Done", "Canceled", "Cancelled", "Duplicate"}
for issue in issues:
    state = issue.get("state", {}).get("name", "")
    if state in terminal:
        continue
    assignee = issue.get("assignee") or {}
    print(f"{issue['identifier']} [{state}] {issue['title']} assignee={assignee.get('displayName') or assignee.get('name') or '-'}")
    print(issue["url"])
PY
```

### Read One Issue

```python
issue = client.get_issue("LAN-296")
```

Return or summarize:

- identifier and URL
- title
- state
- priority
- assignee
- labels
- parent
- description summary

### Create Issues From A Plan

Follow the `to-tickets` publishing rules, but publish to Linear only after approval.

Draft each issue with:

- title
- Markdown description
- priority: `P0`, `P1`, `P2`, or `P3`
- status: usually `Todo` unless the user asks for another state
- assignee, if known
- labels, usually including `ready-for-agent` for agent-executable work
- blockers or parent relationship, if applicable

For confirmed batch creation, prefer the existing script:

```bash
python3 /Users/damien/.agents/skills/meeting-to-linear/scripts/create_linear_issues.py \
  --issues "/path/to/issues-input.json" \
  --team "LAN" \
  --project "LanGear" \
  --output "/path/to/issues-output.json"
```

Omit `--project` only when the user explicitly asks for team-only issues.

If the user explicitly wants issues added to the active cycle, add:

```bash
--cycle active
```

Do not add `--cycle active` merely because the user referenced the LAN all view. The team all view is the issue queue; an active cycle is a separate Linear feature.

### Update Existing Issues

Use `client.update_issue("LAN-123", ...)` after confirmation.

Common fields:

- `description`
- `priority`
- `stateId`
- `assigneeId`
- `labelIds`
- `parentId`

Before updating status, labels, assignee, or parent links, resolve names to IDs using the helper methods:

- `get_workflow_states(team_id)`
- `get_issue_labels(team_id)` and workspace labels
- `get_users()`
- `get_issue(identifier)`

## Output Style

When reporting Linear results, keep it compact:

```text
LAN-123 - Title
State: Todo
Priority: P2
Assignee: -
URL: https://linear.app/...
```

For proposed writes, present a short action list and ask for explicit confirmation before making API calls.
