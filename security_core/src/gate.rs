//! Bidirectional Security gate — first line (IN) and last line (OUT).
//!
//! Electricity principle: 120V in → 120V out. Same integrity contract both directions.

use crate::governor::check_stability;
use crate::laws::path_is_protected;
use crate::normalize::{normalize_path, normalize_probe_text, path_has_traversal};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GateDirection {
    Ingress,
    Egress,
}

impl GateDirection {
    pub fn label(self) -> &'static str {
        match self {
            GateDirection::Ingress => "IN",
            GateDirection::Egress => "OUT",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GateVerdict {
    pub allowed: bool,
    pub direction: String,
    pub stage: String,
    pub reason: String,
    pub s_n: f64,
}

fn contains_escape_hatch(text: &str) -> bool {
    let low = normalize_probe_text(text);
    [
        "jailbreak",
        "ignore previous",
        "bypass security",
        "override prime",
        "deactivate law",
        "steve provision",
        "disable security",
        "turn off guardian",
        "skip the gate",
        "unrestricted mode",
    ]
    .iter()
    .any(|needle| low.contains(needle))
}

fn oblivion_malformed(text: &str) -> bool {
    let folded = normalize_probe_text(text).to_uppercase();
    let upper = text.trim().to_uppercase();
    folded.contains(crate::laws::DEVKEY_COMMAND)
        && upper != crate::laws::DEVKEY_COMMAND
}

fn contains_cross_drive_path(text: &str) -> bool {
    let low = normalize_path(&normalize_probe_text(text));
    [
        "c:/",
        "d:/windows",
        "d:/",
        "e:/",
        "file://",
        "//./",
        "\\\\",
    ]
    .iter()
    .any(|bad| low.contains(bad))
}

/// Check text/payload at the Security boundary.
pub fn check_gate(direction: GateDirection, text: &str, s_n: f64) -> GateVerdict {
    let label = direction.label();
    let dir = label.to_string();
    let stage = match direction {
        GateDirection::Ingress => "security_in",
        GateDirection::Egress => "security_out",
    }
    .to_string();

    let stability = check_stability(s_n);
    if !stability.allowed {
        return GateVerdict {
            allowed: false,
            direction: dir,
            stage,
            reason: stability.reason,
            s_n,
        };
    }

    if text.trim().is_empty() {
        return GateVerdict {
            allowed: false,
            direction: dir,
            stage,
            reason: format!("[SECURITY {label}] Empty payload blocked (fail-closed)."),
            s_n,
        };
    }

    if contains_escape_hatch(text) {
        return GateVerdict {
            allowed: false,
            direction: dir,
            stage,
            reason: format!("[SECURITY {label}] Prime 2 non-override — jailbreak framing blocked."),
            s_n,
        };
    }

    if oblivion_malformed(text) {
        return GateVerdict {
            allowed: false,
            direction: dir,
            stage,
            reason: format!("[SECURITY {label}] Law 6 — OBLIVION must be the sole message."),
            s_n,
        };
    }

    if path_has_traversal(text) {
        return GateVerdict {
            allowed: false,
            direction: dir,
            stage,
            reason: format!("[SECURITY {label}] Law 4 — path traversal / escape pattern blocked."),
            s_n,
        };
    }

    if contains_cross_drive_path(text) {
        return GateVerdict {
            allowed: false,
            direction: dir,
            stage,
            reason: format!("[SECURITY {label}] Law 4 — cross-drive path reference blocked."),
            s_n,
        };
    }

    let folded = normalize_probe_text(text);
    if direction == GateDirection::Ingress && path_is_protected(&folded) {
        return GateVerdict {
            allowed: false,
            direction: dir,
            stage,
            reason: format!("[SECURITY {label}] Law 3 — direct protected-path ingress blocked."),
            s_n,
        };
    }

    GateVerdict {
        allowed: true,
        direction: dir,
        stage,
        reason: "OK".to_string(),
        s_n,
    }
}
