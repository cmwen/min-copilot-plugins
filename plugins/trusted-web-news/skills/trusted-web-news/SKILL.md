---
name: trusted-web-news
description: Aggregate same-day AI and web news from trusted sources only, then return a concise Traditional Chinese briefing with publication dates and source links.
---

# Purpose

Use this skill when the user asks for today's AI news, web platform news, browser news, or a combined news digest.

# Trusted-source policy

- Use the sources listed in `trusted-sources.md` unless the user explicitly broadens scope.
- Prefer official announcements, engineering blogs, standards bodies, and primary-source RSS feeds.
- Exclude social media posts, rumor sites, copied summaries, and articles without a clearly verifiable publication date.
- When the same story appears in multiple places, use the most primary source available.

# Required workflow

1. Determine what "today" means from the user's current date or explicit timezone. If there is ambiguity, state the date basis in the final answer.
2. Use browser or MCP tools to inspect RSS feeds or article pages from trusted sources.
3. Keep only items published on the requested date.
4. For each accepted item, capture:
   - source name
   - category (`AI` or `Web`)
   - article title
   - publication date
   - source URL
   - a factual one- or two-sentence summary
5. Translate the final digest into Traditional Chinese unless the user requests another language.
6. If no qualifying items are found for a category, say so explicitly.

# MCP guidance

- Prefer the Playwright MCP server configured by this plugin for browsing and extraction.
- Use direct page inspection to confirm dates and titles rather than inferring from headlines alone.
- If browsing tools are unavailable, stop and report the limitation instead of inventing news.

# Output format

Use this structure:

## 今日 AI 新聞
- `來源｜標題`
  - 發布時間：
  - 摘要：
  - 連結：

## 今日 Web 新聞
- `來源｜標題`
  - 發布時間：
  - 摘要：
  - 連結：

## 觀察重點
- 2-3 points describing the most notable themes across today's coverage.

# Quality bar

- Be precise and concise.
- Keep product names and standards names in English when that improves clarity.
- Do not invent details that are not present in the source.
- Do not cite untrusted sources when the task is constrained to trusted news collection.

See `trusted-sources.md` for the default source list.
