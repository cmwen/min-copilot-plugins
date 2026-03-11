---
name: life-api-automation
description: Design or extend personal automation workflows that depend on external APIs, tokens, or MCP integrations.
---

# Purpose

Use this skill when the user wants to add a new automation beyond the starter set, such as tasks, reminders, travel, finance, or home services.

# Workflow

1. Define the trigger, desired outcome, and acceptable level of automation.
2. Identify the systems involved, their APIs or MCP servers, and the authentication method required.
3. Map the data contract: inputs, outputs, identifiers, and error cases.
4. Separate read-only actions from write actions that need explicit approval.
5. Design the smallest safe workflow first, then note how it can be extended later.

# Output format

Use this structure:

## Automation goal
- Trigger
- Desired outcome

## Required integrations
- Services
- Auth method
- Needed permissions

## Workflow design
- Step-by-step flow
- Read actions
- Write actions

## Failure handling
- Expected errors
- Retry or fallback strategy

## Approval points
- Steps that must require user confirmation

## Next implementation step
- The best next action to make the automation real

# Quality bar

- Do not assume hidden credentials or integrations.
- Keep security and least-privilege in scope.
- Prefer a safe starter workflow over an over-automated one.
