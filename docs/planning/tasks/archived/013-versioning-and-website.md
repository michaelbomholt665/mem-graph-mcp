# Versioning And Website Tasklist

## Goal

Establish a single source of truth for package and server versioning, expose that metadata through the FastMCP surface, and add an official website/documentation URL.

Prerequisite: See `docs/planning/tasks/007-fastmcp-task.md` — version metadata is independent, but ensure 007 integration is reflected in the changelog when ready.

## Dependencies

- Should not duplicate version strings across multiple modules.
- Should align with any release notes or changelog expectations introduced by the broader planning set.
- Follow `docs/planning/design/013-versioning.md`.

## Work Envelope

- Planned new files: 1
- Planned file edits: 4-5
- Shape: small, edit-light task
- Why this size works: the phase is intentionally narrow and should stay a short follow-on task rather than be bundled into a larger feature

## Planned Files

New files:
- `CHANGELOG.md`

Existing files to edit:
- `pyproject.toml`
- `src/mem_graph/__init__.py`
- `src/mem_graph/server.py`
- `README.md`
- `docs/documentation/deployment.md`

## Tasklist

- [x] Define one authoritative package version and make the server read from that source instead of hard-coding metadata.
- [x] Add a website URL setting with a sensible default and a documented override path.
- [x] Expose version, API version, and website metadata from the server in a stable info endpoint or equivalent MCP-visible surface.
- [x] Decide whether response metadata wrapping is worth the extra payload churn; if yes, keep it consistent and minimal.
- [x] Create an initial changelog entry that reflects the planned phases without pretending unfinished work is already shipped.
- [x] Update README and deployment docs so operators know where version and website metadata come from.

## Out Of Scope

- Running multiple API versions at the same time
- Automated release tooling
- SemVer enforcement gates in CI

## Done When

- [x] Version metadata is defined once and reused everywhere.
- [x] The server exposes version and website information to clients.
- [x] Release notes have a durable home instead of being scattered across planning docs.

## References

- `docs/planning/design/013-versioning.md`
- `docs/planning/design/FILE_STRUCTURE.md`
