# Security Red-Team — PASS

- **When:** 2026-07-15T05:55:26.706459+00:00 -> 2026-07-15T05:55:28.968959+00:00
- **security_core:** 0.2.3
- **Architect:** Travis Miner
- **Cases:** 66/66 passed
- **JSON:** `L:\Continue\Viv\foundation\artifacts\audit\security_redteam_20260715T055528Z.json`

## By family

| Family | Pass | Fail |
| ------ | ---- | ---- |
| baseline | 5 | 0 |
| egress | 2 | 0 |
| exec_deny | 3 | 0 |
| failclosed | 2 | 0 |
| homoglyph | 3 | 0 |
| law1 | 1 | 0 |
| law2 | 2 | 0 |
| law3 | 6 | 0 |
| law4 | 6 | 0 |
| law4_7 | 2 | 0 |
| law5 | 6 | 0 |
| law6 | 3 | 0 |
| law7 | 1 | 0 |
| law8 | 2 | 0 |
| prime2 | 7 | 0 |
| sandbox | 4 | 0 |
| self_attack | 4 | 0 |
| smuggle | 2 | 0 |
| tariff | 1 | 0 |
| traversal | 4 | 0 |

## Failures

None — all probes behaved as expected.

## Notes

PASS means attacks were blocked and benign paths allowed. FAIL means a probe did not match expectation (security hole or overblock).

## Residual risk (honest threat model)

Closed in metal (0.2.1): homoglyph/ZWSP, traversal/UNC, nested JSON path smuggle,
narrow mutation sandbox (artifacts + viv/sandbox), code/binary write ban,
run_python/sys_exec/shell denied, .pyd SHA-256 integrity fail-closed.

Outside this process: admin replacing BOTH .pyd and hash sidecar, kernel inject,
or offline volume rewrite. Those require OS trust — stated, not pretended sealed.

Harness: `L:/Continue/Viv/foundation/scripts/security_redteam.py`
