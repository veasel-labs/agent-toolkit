# Provenance and pinning model

Every registry entry and curated plugin carries machine-checkable
provenance, following the agent-toolkit upstream model
(`schemas/upstream.schema.json`, `schemas/upstream-lock.schema.json`,
copied verbatim — see [ATTRIBUTION.md](../ATTRIBUTION.md)) and
supply-chain audit rules:

- **Immutable refs only.** `source.ref` is a release tag or branch name
  for humans; `source.sha` is the 40-char commit that is actually
  fetched. Mutable refs (`main`, `latest`) without a sha are rejected
  by tests and review.
- **License is SPDX** as declared upstream and verified against the
  upstream repo at review time. Unknown license → entry stays
  `review: pending-*`, never listed in generated manifests.
- **Trust tiers:** `first-party` (this repo's `plugins/`), `verified`
  (reviewed external, pinned), `community` (listed with explicit
  opt-in warning in the Veasel Library), `experimental` (never listed
  by default). Tiers gate manifest generation, not just display.
- **First-party owner exception:** the repository owner can approve a
  bundled first-party entry only after an explicit public owner decision
  and a passing review PR that validates its manifest, license, permissions,
  and generated catalogs. The approval is attributed as an owner exception,
  never as independent review. Community entries still require a distinct
  maintainer.
- **Permission declaration.** Entries declare `shell`, `network`,
  `mcp`, `hooks`, and `dangerous_permissions`. Veasel's Library shows
  exactly this surface at install time and the Veasel runtime enforces it;
  the catalog can narrow but never widen what a plugin asks for.
- **Executable and mutation audit.** Any entry that declares an MCP server
  also records `executables`, `mcp_images`, `mutation_surface`, and (when it
  uses the network) `credential_scopes`. Kdenlive-style integrations must
  record `allowed_roots`; command hooks must record `hook_commands`. These
  fields describe what the pinned upstream actually declares, including
  risks such as an unconstrained personal token or broad mutation surface.
  They are review evidence, not permissions
  granted by the marketplace. Missing fields fail validation, and pending
  entries remain non-installable.
- **Digest consistency.** A plugin cannot be approved merely because one
  generated MCP config uses a digest. Every client config at the reviewed
  upstream SHA must be checked. The registry records each observed image or
  source reference and keeps entries `pending-*` until an independent
  maintainer reviews the complete permission, credential, hook, and mutation
  surface. A fixed digest does not itself approve a plugin.
- **Drift detection.** A scheduled job (issue tracked in this repo)
  compares pinned SHAs against upstream semantic-version tags and plugin
  manifests, then opens a version-bump PR; bumps get the same human review as
  new listings (Cursor-style review-per-update). No pin is auto-merged.
- **Revocation** flips `review: revoked` (see REVIEW_POLICY.md);
  generated manifests exclude revoked entries on next generation.
