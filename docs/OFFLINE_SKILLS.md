# Bundled minimal offline skill set

Veasel ships a minimal skill set inside `veasel-labs/veasel` itself so a
fresh install works with zero network and zero catalog access. The set
is intentionally tiny; everything else installs from this catalog via
the Library (veasel-labs/veasel#706).

| Skill | Source | Why bundled |
| --- | --- | --- |
| output-handshake | this repo, `plugins/veasel-essentials/skills/output-handshake/` (copied verbatim from ulises-jeremias/agent-toolkit@ec993aa5 `skills/core/output-handshake/`, MIT) | Output contract every other skill composes with; no network, no MCP, no shell |

Admission rules for the bundled set: no network, no MCP servers, no
shell execution, no hooks, MIT-compatible license, and a maintainer
review recorded in the registry entry. Anything needing more stays
catalog-only.
