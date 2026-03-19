---
name: plugin-marketplace-wiring
description: Publish or update a Copilot CLI plugin in a repository marketplace by wiring marketplace metadata, source paths, README guidance, and install instructions.
---

# Purpose

Use this skill when a new or updated plugin should be discoverable through a Copilot CLI plugin marketplace instead of only by direct path installation.

# Required workflow

1. Update `.github/plugin/marketplace.json`.
2. Add or update the plugin entry with:
   - `name`
   - `description`
   - `version`
   - `source`
3. Keep the marketplace metadata current when the repository scope changes materially.
4. Use a source path rooted at the repository, such as `plugins/<plugin-name>`.
5. Update the repository README so users can:
   - see the plugin in the published list
   - install it from the marketplace
   - install it directly from the repository path
6. Make sure the install commands use the plugin name exactly as defined in `plugin.json`.

# Output expectations

Summarize:

- the marketplace entry that was added or updated
- any version changes that were needed
- the install commands users should run
- any documentation sections that changed

# Quality bar

- Keep marketplace and plugin versions aligned when they refer to the same release.
- Do not add a marketplace entry that points at a missing directory.
- Keep descriptions concise and accurate so the plugin is easy to browse.
- Update the README at the same time so users are not forced to infer how to install the new plugin.
