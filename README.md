# Veasel Agent Toolkit — official plugin distribution & community marketplace

The official plugin catalog for [Veasel](https://github.com/veasel-labs/veasel).
This repository owns **distribution only**: curated official plugins,
a Git-backed registry of externally maintained community plugins,
provenance, review policy, version pinning, and generated client
marketplace manifests. Runtime, sessions, and security enforcement live
exclusively in `veasel-labs/veasel` — there is no second engine, CLI, or
plugin runtime here.

Not to be confused with
[`ulises-jeremias/agent-toolkit`](https://github.com/ulises-jeremias/agent-toolkit):
that is the maintainer's personal, portable plugin collection. It stays
independent and may publish its plugins into this catalog **by
reference** (repo + ref + pinned sha) without duplicating source — see
the first entry in [`registry/registry.yaml`](registry/registry.yaml).

## Layout

| Path | What |
| --- | --- |
| `plugins/` | Curated official Veasel plugins (bundled sources) |
| `registry/registry.yaml` | Community registry: external plugins pinned by sha |
| `schemas/` | Canonical schemas copied from agent-toolkit (see [ATTRIBUTION.md](ATTRIBUTION.md)) |
| `.claude-plugin/marketplace.json` | Generated Claude Code marketplace manifest |
| `docs/REVIEW_POLICY.md` | Review, pinning, and revocation rules |
| `tests/` | Registry/manifest consistency tests (stdlib Python) |

## Design lineage

Git-backed catalog + per-plugin manifests (Claude Code marketplaces,
Agent Plugins 1.0), manual review of every listing and update (Cursor
Marketplace), multi-client generated manifests (Claude/Cursor/Codex/
Copilot plugin formats), sha-pinned provenance (agent-toolkit
upstream-lock). Veasel's TUI/Desktop Library consumes this catalog for
discovery, install, update, permission review, and removal; bundled
minimal offline skills ship with Veasel itself so a fresh install works
without network.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT — see [LICENSE](LICENSE) and [ATTRIBUTION.md](ATTRIBUTION.md).
