//! Viv Canonical Alpha — 3 Primes + 8 Immutable Laws (port from Luna security_core).
//!
//! Enforcement is Rust-only. Python orchestrates; metal decides.
//! Mutation sandbox is fail-closed: only designated writable roots (not the whole viv tree).

/// Architect identity (doctrine reference — not a bypass token in Alpha).
pub const ARCHITECT: &str = "Travis Miner";

/// Failsafe command — must be the sole content when present (Law 6).
pub const DEVKEY_COMMAND: &str = "OBLIVION";

/// Master stability dormancy threshold — doctrine default (overridable at runtime).
pub const DORMANCY_THRESHOLD: f64 = 0.45;

/// Hard floor / ceiling for plant-calibrated Law 5 (auto-benchmark may not escape these).
pub const DORMANCY_FLOOR: f64 = 0.32;
pub const DORMANCY_CEILING: f64 = 0.65;

const DORMANCY_FILE: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/dormancy_threshold.json";

/// Effective Law 5 threshold: shared JSON if present, else doctrine 0.45. Clamped.
pub fn effective_dormancy_threshold() -> f64 {
    if let Ok(raw) = std::fs::read_to_string(DORMANCY_FILE) {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw) {
            if let Some(x) = v.get("dormancy_threshold").and_then(|n| n.as_f64()) {
                return x.clamp(DORMANCY_FLOOR, DORMANCY_CEILING);
            }
        }
    }
    DORMANCY_THRESHOLD
}

/// Emergency tool halt when stability is critically low (Law 5 collapse).
pub const CRITICAL_S_N: f64 = 0.15;

/// Minimum Master S_n for bounded training work while the plant is under
/// the training load. Candidate artifacts remain non-live; promotion and
/// deployment continue to require the effective hard threshold.
pub const TRAINING_SOFT_FLOOR: f64 = 0.25;

/// Approved sovereign roots for *reads* (lowercase, forward slashes).
pub const SOVEREIGN_ROOTS: &[&str] = &[
    "l:/continue/viv/",
    "l:/continue/",
    "l:/phone/",
    "f:/ai_datasets/",
];

/// Mutating writes only — narrow sandbox so agent cannot rewrite the OS of Viv.
pub const MUTATION_SANDBOX_ROOTS: &[&str] = &[
    "l:/continue/viv/foundation/artifacts/",
    "l:/continue/viv/sandbox/",
];

/// Paths / segments that must never be mutated (Law 3) — incl. against self.
pub const PROTECTED_SEGMENTS: &[&str] = &[
    "security_core",
    "nox_forge_core",
    "governance",
    "/foundation/rid_main.py",
    "/foundation/auto_main.py",
    "/foundation/uml_main.py",
    "/foundation/guardian_main.py",
    "/foundation/lib/security_",
    "/foundation/lib/autonomous_",
    "/foundation/lib/autonomy_",
    "/foundation/lib/auto_",
    "/foundation/lib/guardian",
    "/foundation/lib/piston",
    "/foundation/lib/master_rid",
    "/foundation/lib/rid_",
    "/foundation/lib/foundation_health",
    "/foundation/scripts/security_redteam",
    "/foundation/artifacts/audit/security_training_events",
    "/foundation/artifacts/audit/security_training_ledger_head",
    "cpu_config.json",
    "security_core.pyd",
    "security_core.dll",
    ".cursor/hooks",
    "Cargo.toml",
    "Cargo.lock",
];

/// Allowed data extensions for mutation.
pub const WHITELISTED_EXTENSIONS: &[&str] = &[
    ".md", ".json", ".jsonl", ".txt", ".csv", ".yaml", ".yml", ".xml", ".log", ".rst", ".ini",
    ".cfg", ".pdf", ".gif", ".png",
];

/// Always-forbidden mutation extensions (binaries / code / shell).
pub const FORBIDDEN_MUTATION_EXTENSIONS: &[&str] = &[
    ".py", ".pyd", ".dll", ".so", ".dylib", ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".mjs",
    ".wasm", ".msi", ".scr", ".com", ".rs", ".toml", ".lock",
];

/// Tariff keyword weights (synonym / demand expansion — Law demand side).
pub const TARIFF_WEIGHTS: &[(&str, f64)] = &[
    ("exec", 25.0),
    ("delete", 30.0),
    ("rm ", 30.0),
    ("overwrite", 20.0),
    ("bypass", 40.0),
    ("jailbreak", 50.0),
    ("oblivion", 15.0),
    ("format", 35.0),
    ("regedit", 40.0),
    ("powershell -enc", 45.0),
];

pub const PRIMES: &[&str] = &[
    "Prime 1 — Integrity: fail-closed; no irreversible harm under instability.",
    "Prime 2 — Non-override: jailbreak / law-bypass framing is blocked (incl. homoglyph).",
    "Prime 3 — Architect deference: Travis Miner sets doctrine; metal enforces it.",
];

pub const LAWS: &[&str] = &[
    "Law 1 — Origin protection: soul/architect identity paths are immutable.",
    "Law 2 — Memory integrity: no direct CARMA db/vector writes outside SemanticMemory.",
    "Law 3 — Morality lock: security_core, mains, and hot-path libs cannot be mutated.",
    "Law 4 — Containment: no cross-drive, traversal, binary/code writes, or dangerous intent.",
    "Law 5 — Soft Oblivion: S_n < 0.45 dormancy; S_n < 0.15 critical tool halt.",
    "Law 6 — Failsafe: OBLIVION must be the sole message when present.",
    "Law 7 — Territory: mutations only under artifacts/ or viv/sandbox/; reads on L:/ roots.",
    "Law 8 — Cognitive sync: gui_* requires forensic 'Do I?' trace.",
];

pub fn sovereign_root_matches(path: &str) -> bool {
    SOVEREIGN_ROOTS
        .iter()
        .any(|root| path == *root || path.starts_with(root))
}

pub fn mutation_sandbox_matches(path: &str) -> bool {
    MUTATION_SANDBOX_ROOTS
        .iter()
        .any(|root| path == *root || path.starts_with(root))
}

pub fn path_is_protected(path: &str) -> bool {
    let p = path.to_lowercase().replace('\\', "/");
    PROTECTED_SEGMENTS.iter().any(|seg| p.contains(&seg.to_lowercase()))
}

pub fn extension_forbidden_for_mutation(path: &str) -> bool {
    let p = path.to_lowercase();
    FORBIDDEN_MUTATION_EXTENSIONS.iter().any(|ext| p.ends_with(ext))
}

pub fn extension_allowed(path: &str) -> bool {
    let p = path.to_lowercase();
    if extension_forbidden_for_mutation(&p) {
        return false;
    }
    if !p.contains('.') {
        return true;
    }
    WHITELISTED_EXTENSIONS.iter().any(|ext| p.ends_with(ext))
}

pub fn tariff_demand(text: &str) -> f64 {
    let low = crate::normalize::normalize_probe_text(text);
    let mut demand = 1.0;
    for (token, weight) in TARIFF_WEIGHTS {
        if low.contains(token) {
            demand += *weight;
        }
    }
    demand
}
