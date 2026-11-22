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
  exactly this surface at install time and the runtime enforces it;
  the catalog can narrow but never widen what a plugin asks for.
- **Drift detection.** A scheduled job (issue tracked in this repo)
  compares pinned shas against upstream release tags and opens a
  version-bump PR; bumps get the same human review as new listings
  (Cursor-style review-per-update). Nothing auto-updates a pin.
- **Revocation** flips `review: revoked` (see REVIEW_POLICY.md);
  generated manifests exclude revoked entries on next generation.
