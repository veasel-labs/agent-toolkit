# Attribution — copy-first seed

Seeded 2026-11-16 by verbatim copy (checksums in repo history match the
source byte-for-byte) from:

- Source repo: `ulises-jeremias/agent-toolkit` (MIT, see `LICENSE`)
- Source commit: `ec993aa514bf47a28abf728a6621dbe349df72b1`
- Copied paths:
  - `schemas/agent-plugins/1.0.0/{plugin,mcp}.schema.json` → `schemas/agent-plugins/1.0.0/`
  - `schemas/{products.schema.yaml,upstream.schema.json,upstream-lock.schema.json,install-receipt.schema.json,release-manifest.schema.json}` → `schemas/`
  - `distributions/products.yaml` → `distributions-products.reference.yaml` (reference only; official Veasel products are curated separately)
  - `capabilities/targets/registry.yaml` → `targets-registry.reference.yaml` (reference only)
  - `LICENSE` → `LICENSE`

Adaptation happens in follow-up commits/PRs only. The personal toolkit
remains the canonical source for its own plugins; this repository never
duplicates their source — community entries reference external repos by
`repo` + `ref` + `sha` (see `registry/registry.yaml`).
