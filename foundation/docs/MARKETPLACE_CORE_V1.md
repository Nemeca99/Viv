# Marketplace Core v1

The legacy marketplace core can refresh remote catalogs, install/update/publish
plugins, modify dependencies, and activate external capabilities. Those are
optional effects, not CPU authority.

This slice accepts caller-supplied plugin manifests and catalog records. It
validates metadata, searches the catalog, checks declared dependencies, emits
conservative trust findings, and produces a denied install handoff until source
hashes, signature evidence, and separate Architect approval are present.

No network access, filesystem scan, installation, activation, publishing,
dependency mutation, or model call occurs here. The contract remains
`optional` even though its read-only planner is wired, so the AIOS inventory
does not misclassify optional capability as authoritative cognition.

Evidence is recorded in `CURRENT_TASK.json` and `session_journal.md`.
