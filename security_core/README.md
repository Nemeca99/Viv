# Viv `security_core` — Rust Security Layer

**Path:** `L:\Continue\Viv\security_core\`  
**Role:** First and last line of defense. Bidirectional IN/OUT gate around the three Python foundation mains.

## Doctrine

- **Security MUST be Rust** — immutable law enforcement, fail-closed.
- **Ingress (IN):** nothing external reaches `foundation/` without passing Security IN.
- **Egress (OUT):** nothing leaves to External without passing Security OUT.
- **120 in → 120 out:** same integrity contract both directions.

Python (`L:\Continue\Viv\foundation\`) orchestrates. Rust enforces.

## Build

```powershell
cd L:\Continue\Viv\security_core
.\scripts\build.ps1
.\scripts\build.ps1 -Install -BackupManifest <verified-manifest>
```

PyO3 module output: `target\release\security_core.dll`  
The default command builds without installing. The explicit installer requires
a verified snapshot containing the active module, then stages, hashes, smokes,
and transactionally installs to `security_core\runtime\security_core.pyd`.
The shared `.venv` 0.2.5 module remains untouched. Do not copy the DLL manually:
the Python bridge fails closed unless the Viv-local module and sidecar agree.

## Native CLI

```powershell
cargo run --release --bin security_core_cli -- check-in "hello" --s-n 0.56
cargo run --release --bin security_core_cli -- check-out "response text" --s-n 0.56
```

## Python API (PyO3)

```python
import security_core

security_core.check_ingress("user text", 0.56)  # dict: allowed, direction, stage, reason, s_n
security_core.check_egress("response text", 0.56)
security_core.enforce_morality("write_file", '{"path":"L:/Continue/Viv/..."}', 0.56, "")
security_core.dormancy_threshold()  # 0.45
```

Version 0.2.7 exposes typed training capabilities:

- `authorize_training`
- `begin_training_lease` / `commit_training_lease`
- `freeze_training_registry`
- `quarantine_training_payload` / `read_training_quarantine`
- `verify_training_ledger`

Training leases are process-bound, single-use, resource-capped, and bound to
the model role, artifact class, source hashes, paths, manifest, and LoRA
envelope. LoRA commits scan safetensors structure and every value for
non-finite data before an atomic final move. `DEPLOY` is compiled closed.

It also exposes typed backup capabilities:

- `authorize_backup`
- `verify_backup_ledger`

The backup capability matrix keeps replication closed, permits snapshots only
from allowlisted Viv/exact security-module paths into the vault, limits restore
reconstruction to sandbox staging, and requires explicit Architect approval for
live restore commit.

## Operator entry

```powershell
L:\Continue\.venv\Scripts\python.exe L:\Continue\Viv\security_core\security_main.py check-in "hello"
```

## Layer position

```text
External → SECURITY IN → foundation (rid · auto · uml) → SECURITY OUT → External
```

Next layers above: Memory, GPU/Voice, Training.
