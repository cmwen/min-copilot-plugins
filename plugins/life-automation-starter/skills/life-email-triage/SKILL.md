---
name: life-email-triage
description: Review inbox contents, identify priorities, and prepare safe next actions without sending or changing mail prematurely.
---

# Purpose

Use this skill when the user wants help understanding or acting on an inbox.

# Requirements

- Access to the relevant mailbox through an authenticated API, MCP server, or explicitly approved browser session
- A clear scope such as date range, folder, account, or sender group

# Workflow

1. Confirm which mailbox and message scope to inspect.
2. Read only the messages needed to answer the user's request.
3. Classify messages by urgency, action required, deadline, and category.
4. Summarize the inbox in a compact action-oriented format.
5. Draft replies, filing suggestions, or follow-up tasks when helpful.
6. Ask for explicit confirmation before sending, archiving, deleting, labeling, or moving any message.

# Output format

Use this structure:

## Inbox summary
- Total messages reviewed
- Urgent items
- Waiting-for-response items
- FYI items

## Priority actions
- What needs action first

## Drafts or suggested replies
- Only when requested or clearly useful

## Pending approvals
- Any write actions that still require confirmation

# Safety rules

- Never claim to have sent or modified email without confirmation and tool support.
- Minimize data access to the scope needed for the task.
- Be explicit about any unavailable integration.
