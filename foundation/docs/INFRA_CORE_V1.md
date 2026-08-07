# Infra Core v1

The F and D infra sources contain deployment, Docker/Railway, CI, monitoring,
performance, and rollback tooling. Those operations have external effects and
remain separately governed.

This CPU slice accepts caller-supplied metrics, SLO thresholds, and CI stage
receipts. It evaluates the evidence, plans CI/deployment/rollback handoffs,
and keeps deployment and rollback unauthorized. The existing
`cpu_infra_ops_judge.py` remains the health/SLO observation surface; the new
planner and adapter provide the missing registry-facing CPU boundary without
starting stress tests, services, containers, or network calls.
