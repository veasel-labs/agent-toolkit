# Review policy

Borrowed from Cursor Marketplace (manual review of every plugin and
every update) and Claude Code marketplaces (Git-backed catalog, pinned
sources), tightened with this repo's provenance rules.

1. **Independent review is the default.** Every community or verified plugin
   change in `registry/registry.yaml` — new plugin, version bump, `ref`/`sha`
   change — requires a PR reviewed by a maintainer who is not the submitter.
   The repository owner may approve a bundled `trust: first-party` entry only
   when the owner explicitly authorizes the exception in a public governance
   issue and the approval PR records that issue, validates the bundled
   manifest/license/permission surface, and passes registry/security tests.
   Record `reviewed_by` as an owner-approved first-party exception; never
   imply that an independent reviewer approved it. This narrow exception does
   not apply to external or community entries, which remain fail-closed until
   a genuinely distinct maintainer reviews them.
2. **Pin verification.** Reviewer confirms the pinned `sha` exists in
   the upstream repo at `ref`, that the plugin manifest at that sha
   validates against `schemas/agent-plugins/1.0.0/plugin.schema.json`,
   and that the declared `license` matches the upstream repo.
   An approved external entry must record `reviewed_source_sha` equal to
   `source.sha`, `reviewed_at`, and a public GitHub PR or issue URL in
   `review_evidence`. Any pin change invalidates the recorded approval until
   the new source is reviewed and all three fields are updated. These fields
   do not apply to the owner-approved bundled first-party exception.
3. **Permission surface.** Reviewer lists every MCP server, hook, and
   executable the plugin declares. Anything undisclosed is grounds for
   rejection. Veasel shows this same surface at install time; the
   catalog never widens it.
4. **No source duplication.** Community plugins are referenced, never
   vendored. Curated official plugins live under `plugins/` in this
   repo and follow the same manifest + test rules.
5. **Revocation.** A plugin can be yanked by PR setting
   `review: revoked` with a reason; generated manifests stop offering
   it, installed copies are flagged in the Veasel Library, never
   silently removed.
6. **Security reports** go through GitHub private vulnerability
   reporting on this repo; runtime/session security bugs belong to
   `veasel-labs/veasel`, not here.
