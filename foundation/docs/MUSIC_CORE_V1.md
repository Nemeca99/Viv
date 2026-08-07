# Music Core v1

The legacy music core combines local-library scanning, random selection,
timestamped play-history writes, mood mapping, preference learning, and audio
playback. Those are optional peripheral effects.

This CPU slice accepts caller-supplied track metadata and play history. It
validates tracks, maps moods to declared genres, deterministically selects and
orders a playlist, summarizes supplied preferences, and emits a play intent.
Playback, library scans, random selection, clock reads, and history writes are
closed. Preference summaries are observations only and are not persisted.

The contract remains `optional` even though the read-only planner is wired, so
music cannot become authoritative cognition. Evidence is recorded in
`CURRENT_TASK.json` and `session_journal.md`.
