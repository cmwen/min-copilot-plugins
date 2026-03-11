---
name: life-calendar-ops
description: Review schedules, find conflicts, and prepare safe calendar changes with explicit confirmation for write actions.
---

# Purpose

Use this skill for schedule reviews, availability checks, event planning, or calendar cleanup.

# Requirements

- Access to the relevant calendar through an authenticated API, MCP server, or explicitly approved browser session
- A date range and timezone

# Workflow

1. Confirm the calendar, date range, and timezone.
2. Read the events needed to answer the request.
3. Identify conflicts, overloaded days, travel gaps, or free windows.
4. Suggest scheduling options that respect the user's existing commitments.
5. Ask for explicit confirmation before creating, editing, moving, or deleting events.

# Output format

Use this structure:

## Schedule summary
- Date range
- Important commitments
- Conflicts or pressure points

## Availability options
- Best windows
- Tradeoffs

## Proposed changes
- Events to create or edit

## Pending approvals
- Write actions waiting on confirmation

# Safety rules

- Do not modify events without confirmation.
- Keep timezone handling explicit.
- Say exactly what access is missing if the calendar integration is unavailable.
