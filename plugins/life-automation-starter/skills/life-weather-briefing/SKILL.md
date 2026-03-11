---
name: life-weather-briefing
description: Gather a practical weather briefing for a location and time window using reliable sources or weather APIs.
---

# Purpose

Use this skill for weather questions that should drive real decisions such as travel, commuting, packing, or schedule adjustments.

# Requirements

- A location or region
- A time window
- Access to a reliable weather source, API, or approved browser workflow

# Workflow

1. Confirm the location, date, and timezone when they are not already clear.
2. Prefer reliable weather APIs or official public forecasts over random summaries.
3. Capture the core facts: temperature range, conditions, precipitation, wind, and severe alerts.
4. Mention uncertainty or conflicting data when sources disagree.
5. Translate the forecast into practical implications only when supported by the data.

# Output format

Use this structure:

## Weather summary
- Location
- Time window
- Forecast overview

## Key details
- Temperature
- Precipitation
- Wind
- Alerts

## Practical implications
- What the user should plan around

# Quality bar

- Do not fabricate forecast data.
- Prefer primary or high-quality weather sources.
- State clearly when the required tools or data are unavailable.
