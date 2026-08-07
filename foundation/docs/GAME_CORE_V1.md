# Game Core v1

This CPU slice ports the deterministic part of manual section 3.12. It
analyzes caller-supplied game sessions, detects personal hotspots and supplied
mistakes, compares the person's earliest and latest supplied sessions, and
plans evidence-linked coaching suggestions. It is intentionally personal-only:
there is no comparison with other players or external ranking.

The existing `cpu_choice_simulator.py` remains the deterministic three-action
simulation surface used by the AIOS action economy. The new `game_core.py`
adds the legacy game-core analytics/coaching surface beside it. The adapter
can also expose candidate action rankings, but it does not execute an action.

Session persistence and event appends are not performed here. `plan_session_event`
returns an explicit append intent for a separately governed executor. No
filesystem reads or writes, clock reads, model calls, external comparisons, or
live Master `S_n` mutations occur in this slice.

Evidence and release status are recorded in `CURRENT_TASK.json` and
`session_journal.md`. A passing test proves only the tested CPU boundary, not
production autonomy or general intelligence.
