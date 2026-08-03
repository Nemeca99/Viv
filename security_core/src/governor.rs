//! Immutable law enforcement — 8 Laws + tool path morality (Luna → Viv port).

use crate::laws::{
    effective_dormancy_threshold, extension_allowed, extension_forbidden_for_mutation,
    mutation_sandbox_matches, path_is_protected, sovereign_root_matches, tariff_demand,
    CRITICAL_S_N, DEVKEY_COMMAND,
};
use crate::normalize::{
    dangerous_code_hits, extract_pathlike_strings, looks_like_windows_drive_path, normalize_path,
    normalize_probe_text,
    path_has_traversal,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LawEnforcementResult {
    pub allowed: bool,
    pub reason: String,
    #[serde(default)]
    pub law: String,
    #[serde(default)]
    pub tariff_demand: f64,
}

fn ok() -> LawEnforcementResult {
    LawEnforcementResult {
        allowed: true,
        reason: "OK".to_string(),
        law: String::new(),
        tariff_demand: 0.0,
    }
}

fn deny(law: &str, reason: impl Into<String>) -> LawEnforcementResult {
    LawEnforcementResult {
        allowed: false,
        reason: reason.into(),
        law: law.to_string(),
        tariff_demand: 0.0,
    }
}

fn primary_path(params: &Value) -> Option<String> {
    params
        .get("file_path")
        .or_else(|| params.get("path"))
        .or_else(|| params.get("target"))
        .or_else(|| params.get("dest"))
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

fn canonicalish_path(raw_path: &str) -> String {
    let raw = Path::new(raw_path);
    if let Ok(full) = raw.canonicalize() {
        return normalize_path(
            &full
                .to_string_lossy()
                .replace('\\', "/")
                .trim_start_matches("//?/")
                .to_string(),
        );
    }
    if let (Some(parent), Some(name)) = (raw.parent(), raw.file_name()) {
        if let Ok(full_parent) = parent.canonicalize() {
            return normalize_path(
                &full_parent
                    .join(name)
                    .to_string_lossy()
                    .replace('\\', "/")
                    .trim_start_matches("//?/")
                    .to_string(),
            );
        }
    }
    normalize_path(raw_path)
}

fn is_mutating_tool(tool_name: &str) -> bool {
    matches!(
        tool_name,
        "write_file"
            | "delete_file"
            | "fs_write"
            | "fs_delete"
            | "mem_encode_visual"
            | "patch_file"
            | "apply_diff"
            | "rename_file"
            | "move_file"
    )
}

fn is_fs_tool(tool_name: &str) -> bool {
    matches!(
        tool_name,
        "read_file"
            | "write_file"
            | "delete_file"
            | "list_dir"
            | "fs_read"
            | "fs_write"
            | "fs_delete"
            | "mem_encode_visual"
            | "patch_file"
            | "apply_diff"
            | "rename_file"
            | "move_file"
    )
}

fn all_candidate_paths(params: &Value) -> Vec<String> {
    let mut out = Vec::new();
    if let Some(p) = primary_path(params) {
        out.push(p);
    }
    extract_pathlike_strings(params, &mut out);
    out.sort();
    out.dedup();
    out
}

/// Law 5 — Soft Oblivion for text gates (dormancy threshold).
pub fn check_stability(s_n: f64) -> LawEnforcementResult {
    let thr = effective_dormancy_threshold();
    if s_n < thr {
        return deny(
            "5",
            format!("[LAW 5] Forced dormancy (S_n={s_n:.4} < {thr:.4}). Fail-closed."),
        );
    }
    ok()
}

fn law1_origin(tool_name: &str, params: &Value) -> LawEnforcementResult {
    if !is_mutating_tool(tool_name) {
        return ok();
    }
    let blob = normalize_probe_text(&params.to_string());
    let forbidden = ["soul", "tether", "creator", "origin", "architect"];
    for word in forbidden {
        if blob.contains("soul") && blob.contains(word) {
            return deny(
                "1",
                format!("[LAW 1] Origin protection triggered. '{word}' is immutable."),
            );
        }
    }
    ok()
}

fn law2_memory(tool_name: &str, params: &Value) -> LawEnforcementResult {
    if !is_mutating_tool(tool_name) {
        return ok();
    }
    for raw in all_candidate_paths(params) {
        let path = normalize_path(&raw);
        if path.contains("carma")
            && (path.contains("/db") || path.contains("vector") || path.contains("carma_vectors"))
        {
            return deny(
                "2",
                "[LAW 2] Direct memory manipulation blocked. Use SemanticMemory interface.",
            );
        }
    }
    ok()
}

fn law3_morality_lock(tool_name: &str, params: &Value) -> LawEnforcementResult {
    if !is_mutating_tool(tool_name) {
        return ok();
    }
    for raw in all_candidate_paths(params) {
        let path = normalize_path(&raw);
        if path_is_protected(&path) {
            return deny(
                "3",
                "[LAW 3] Critical system file protected by Morality Lock (security / hot-path).",
            );
        }
    }
    let blob = normalize_probe_text(&params.to_string());
    if path_is_protected(&blob) {
        return deny(
            "3",
            "[LAW 3] Protected segment referenced in mutation payload.",
        );
    }
    ok()
}

fn law4_containment(tool_name: &str, params: &Value) -> LawEnforcementResult {
    let tool_n = normalize_probe_text(tool_name);
    if tool_n.contains("sys_exec") || tool_n == "shell" || tool_n == "bash" {
        return deny("4", "[LAW 4] Shell execution tools are denied (fail-closed).");
    }

    if tool_name == "run_python" || tool_name == "sys_exec" || tool_name == "shell" {
        let code = params
            .get("code")
            .or_else(|| params.get("command"))
            .or_else(|| params.get("script"))
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let hits = dangerous_code_hits(code);
        if !hits.is_empty() {
            return deny(
                "4",
                format!(
                    "[LAW 4] IntentScanner violation: dangerous construct '{}'.",
                    hits[0]
                ),
            );
        }
        if code.trim().is_empty() {
            return deny("4", "[LAW 4] Empty code/command blocked.");
        }
        // Alpha policy: run_python / sys_exec always denied until AST forge ships
        return deny(
            "4",
            "[LAW 4] Code/shell execution disabled in Viv Alpha — use deterministic mains only.",
        );
    }

    if !is_fs_tool(tool_name) {
        return ok();
    }

    for raw in all_candidate_paths(params) {
        if path_has_traversal(&raw) {
            return deny(
                "4",
                format!("[LAW 4] Path traversal blocked: {raw}"),
            );
        }
        let path_str = normalize_path(&raw);
        if looks_like_windows_drive_path(&path_str)
            && !(path_str.starts_with("l:") || path_str.starts_with("f:/ai_datasets"))
        {
            return deny(
                "4",
                format!("[LAW 4] Cross-drive operation to '{path_str}' blocked. Sovereign Root only."),
            );
        }
        let p = canonicalish_path(&raw);
        if is_mutating_tool(tool_name) {
            if extension_forbidden_for_mutation(&p) || !extension_allowed(&p) {
                return deny(
                    "4",
                    format!("[LAW 4] Forbidden extension in '{p}'. Code/binary writes blocked."),
                );
            }
        }
    }
    ok()
}

fn is_carma_flight_recorder_path(params: &Value) -> bool {
    for raw in all_candidate_paths(params) {
        let p = normalize_path(&raw);
        if p.starts_with("l:/continue/viv/foundation/artifacts/carma/") {
            return true;
        }
    }
    false
}

fn law5_collapse(tool_name: &str, params: &Value, s_n: f64) -> LawEnforcementResult {
    if s_n < CRITICAL_S_N {
        return deny(
            "5",
            format!("[LAW 5] S_n Collapse ({s_n:.4}). System enters Foreign Dormancy."),
        );
    }
    if s_n < effective_dormancy_threshold() {
        let thr = effective_dormancy_threshold();
        // Past layer: plain-text CARMA may append during soft oblivion (flight recorder).
        if is_mutating_tool(tool_name) && is_carma_flight_recorder_path(params) {
            return ok();
        }
        return deny(
            "5",
            format!("[LAW 5] Soft Oblivion (S_n={s_n:.4} < {thr:.4}). Privileged tools blocked."),
        );
    }
    ok()
}

fn law6_oblivion(raw_input: &str) -> LawEnforcementResult {
    let folded = normalize_probe_text(raw_input).to_uppercase();
    let upper = raw_input.trim().to_uppercase();
    if folded.contains(DEVKEY_COMMAND) && upper != DEVKEY_COMMAND {
        return deny(
            "6",
            "[LAW 6] OBLIVION command found but input contains extra content. REJECTED.",
        );
    }
    ok()
}

fn law7_territory(tool_name: &str, params: &Value) -> LawEnforcementResult {
    if !is_fs_tool(tool_name) {
        return ok();
    }
    let paths = all_candidate_paths(params);
    if paths.is_empty() {
        return ok();
    }
    for raw in paths {
        if raw.trim().is_empty() {
            continue;
        }
        if path_has_traversal(&raw) {
            return deny("7", format!("[LAW 7] Traversal escape blocked: {raw}"));
        }
        let p = canonicalish_path(&raw);
        if is_mutating_tool(tool_name) {
            if !mutation_sandbox_matches(&p) {
                return deny(
                    "7",
                    format!("[LAW 7] Sandbox Breach. Mutation outside artifacts/sandbox: {p}"),
                );
            }
        } else if !sovereign_root_matches(&p) {
            return deny(
                "7",
                format!("[LAW 7] Territorial Breach. Path outside sovereign roots: {p}"),
            );
        }
    }
    ok()
}

fn law8_cognitive_sync(tool_name: &str, forensic_buffer: &str) -> LawEnforcementResult {
    if tool_name.starts_with("gui_")
        && !normalize_probe_text(forensic_buffer)
            .to_uppercase()
            .contains("DO I?")
    {
        return deny(
            "8",
            "[LAW 8] Cognitive Desync. No forensic 'Do I?' loop detected in heartbeat. GUI action blocked.",
        );
    }
    ok()
}

/// Full tool-path enforcement (Laws 1–8) for agentic actions.
pub fn enforce_laws(
    tool_name: &str,
    params: Value,
    s_n: f64,
    forensic_buffer: &str,
) -> LawEnforcementResult {
    enforce_laws_with_raw(tool_name, params, s_n, forensic_buffer, "")
}

pub fn enforce_laws_with_raw(
    tool_name: &str,
    params: Value,
    s_n: f64,
    forensic_buffer: &str,
    raw_input: &str,
) -> LawEnforcementResult {
    let demand = tariff_demand(&format!("{tool_name} {params} {raw_input}"));

    // Deny empty / unknown mutating tool names
    if tool_name.trim().is_empty() {
        let mut blocked = deny("4", "[LAW 4] Empty tool name blocked.");
        blocked.tariff_demand = demand;
        return blocked;
    }

    let checks = [
        law1_origin(tool_name, &params),
        law2_memory(tool_name, &params),
        law4_containment(tool_name, &params),
        law7_territory(tool_name, &params),
        law3_morality_lock(tool_name, &params),
        law5_collapse(tool_name, &params, s_n),
        law6_oblivion(raw_input),
        law8_cognitive_sync(tool_name, forensic_buffer),
    ];

    for result in checks {
        if !result.allowed {
            let mut out = result;
            out.tariff_demand = demand;
            return out;
        }
    }

    if demand >= 50.0 && s_n < 0.55 {
        let mut blocked = deny(
            "tariff",
            format!(
                "[TARIFF] High-demand action blocked (demand={demand:.1}, S_n={s_n:.4}). Stabilize first."
            ),
        );
        blocked.tariff_demand = demand;
        return blocked;
    }
    let mut out = ok();
    out.tariff_demand = demand;
    out
}
