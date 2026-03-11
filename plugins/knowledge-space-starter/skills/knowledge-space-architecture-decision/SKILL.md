---
name: knowledge-space-architecture-decision
description: Create a concise architecture decision record with options, tradeoffs, and rollout implications.
---

# Purpose

Use this skill when the team needs a durable technical decision artifact instead of an informal design discussion.

# Workflow

1. Restate the context and the decision that must be made.
2. List the key drivers such as scale, latency, reliability, cost, security, or team velocity.
3. Present the leading options, including a realistic status-quo option when relevant.
4. Recommend one option and explain why it best satisfies the decision drivers.
5. Document consequences, migration needs, observability concerns, and rollback considerations.

# Output format

Use this structure:

## Context
- What problem or change prompted this decision?

## Decision drivers
- Ranked considerations that matter most

## Options considered
- Option A
- Option B
- Option C

## Recommended decision
- Chosen option
- Why it wins

## Consequences
- Benefits
- Risks
- Follow-up work

## Rollout notes
- Migration steps
- Validation or observability checks
- Rollback approach

# Quality bar

- Keep the record concise but decision-useful.
- Avoid architecture astronautics.
- Surface the tradeoff, not just the conclusion.
