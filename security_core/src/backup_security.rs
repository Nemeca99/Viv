//! Deny-by-default backup and restore capabilities.
//!
//! Python may orchestrate content-addressed snapshots, but every privileged
//! vault write or live restore must first receive a typed Rust verdict.

use crate::normalize::{normalize_path, path_has_traversal};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const VIV_ROOT: &str = "L:/Continue/Viv";
const VAULT_ROOT: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/backup_core/vault";
const EVIDENCE_ROOT: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/backup_core";
const RESTORE_STAGING_ROOT: &str = "L:/Continue/Viv/sandbox/restore_staging";
const BACKUP_LEDGER_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/audit/security_backup_events.jsonl";
const BACKUP_LEDGER_LOCK_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/audit/.security_backup_events.lock";
const EXTERNAL_EXACT_PATHS: &[&str] = &[
    "L:/Continue/.venv/Lib/site-packages/security_core.pyd",
    "L:/Continue/.venv/Lib/site-packages/security_core.pyd.sha256",
];
const MAX_REQUEST_BYTES: usize = 256 * 1024;
const MAX_OPERATION_BYTES: u64 = 8 * 1024 * 1024 * 1024;
const MIN_FREE_BYTES_FLOOR: u64 = 12 * 1024 * 1024 * 1024;
const POLICY_VERSION: &str = "viv_backup_security_v1";

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum BackupAction {
    Snapshot,
    Verify,
    RestoreStage,
    RestoreCommit,
    Replicate,
    Prune,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BackupSecurityRequest {
    pub action: BackupAction,
    pub operation_id: String,
    pub snapshot_id: Option<String>,
    pub actor_role: String,
    pub manifest_hash: String,
    pub source_paths: Vec<String>,
    pub target_paths: Vec<String>,
    pub process_id: u32,
    pub max_bytes: u64,
    pub min_free_bytes: u64,
    pub architect_approved: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct BackupSecurityVerdict {
    pub allowed: bool,
    pub disposition: String,
    pub reason: String,
    pub rule: String,
    pub decision_id: String,
    pub policy_version: String,
    pub manifest_hash: String,
    pub normalized_source_paths: Vec<String>,
    pub normalized_target_paths: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
struct LedgerRow {
    at_epoch: u64,
    event: String,
    allowed: bool,
    rule: String,
    reason: String,
    operation_id: String,
    snapshot_id: Option<String>,
    manifest_hash: String,
    decision_id: String,
    previous_hash: String,
    event_hash: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BackupLedgerStatus {
    pub ok: bool,
    pub events: usize,
    pub head: String,
    pub error: Option<String>,
    pub policy_version: String,
}

struct LedgerLock {
    path: PathBuf,
}

impl Drop for LedgerLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn acquire_ledger_lock() -> Result<LedgerLock, String> {
    let path = PathBuf::from(BACKUP_LEDGER_LOCK_PATH);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let mut handle = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&path)
        .map_err(|_| "backup ledger is busy or a stale lock requires inspection".to_string())?;
    writeln!(handle, "pid={} at={}", std::process::id(), now_epoch())
        .map_err(|error| error.to_string())?;
    handle.sync_all().map_err(|error| error.to_string())?;
    Ok(LedgerLock { path })
}

fn now_epoch() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn sha256_bytes(payload: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(payload);
    hex::encode(hasher.finalize())
}

fn valid_hash(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|c| c.is_ascii_hexdigit())
}

fn safe_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 96
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, b'-' | b'_'))
}

fn within_root(path: &str, root: &str) -> bool {
    path == root || path.starts_with(&format!("{root}/"))
}

fn exact_external(path: &str) -> bool {
    EXTERNAL_EXACT_PATHS
        .iter()
        .map(|raw| normalize_path(raw))
        .any(|allowed| path == allowed)
}

fn path_contract(raw: &str) -> Result<String, String> {
    if raw.is_empty()
        || raw.len() > 768
        || path_has_traversal(raw)
        || (raw.contains(':') && raw.matches(':').count() != 1)
    {
        return Err(format!("unsafe path: {raw}"));
    }
    let normalized = normalize_path(raw);
    if normalized.contains("//") || normalized.ends_with(':') {
        return Err(format!("unsafe normalized path: {normalized}"));
    }
    if existing_component_is_reparse(Path::new(raw)) {
        return Err(format!("reparse or symlink path denied: {raw}"));
    }
    Ok(normalized)
}

fn existing_component_is_reparse(path: &Path) -> bool {
    let mut cursor = Some(path);
    while let Some(current) = cursor {
        if let Ok(metadata) = fs::symlink_metadata(current) {
            if metadata.file_type().is_symlink() {
                return true;
            }
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
                if metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
                    return true;
                }
            }
        }
        cursor = current.parent();
    }
    false
}

fn decision_id(request: &BackupSecurityRequest, allowed: bool, rule: &str) -> String {
    let encoded = serde_json::to_vec(&json!({
        "operation_id": request.operation_id,
        "snapshot_id": request.snapshot_id,
        "manifest_hash": request.manifest_hash,
        "process_id": request.process_id,
        "action": request.action,
        "allowed": allowed,
        "rule": rule,
        "at": now_epoch(),
    }))
    .unwrap_or_default();
    sha256_bytes(&encoded)
}

fn verdict(
    request: Option<&BackupSecurityRequest>,
    allowed: bool,
    rule: &str,
    reason: impl Into<String>,
    sources: Vec<String>,
    targets: Vec<String>,
) -> BackupSecurityVerdict {
    let placeholder = BackupSecurityRequest {
        action: BackupAction::Verify,
        operation_id: "malformed".to_string(),
        snapshot_id: None,
        actor_role: "unknown".to_string(),
        manifest_hash: String::new(),
        source_paths: Vec::new(),
        target_paths: Vec::new(),
        process_id: 0,
        max_bytes: 0,
        min_free_bytes: 0,
        architect_approved: false,
    };
    let bound = request.unwrap_or(&placeholder);
    BackupSecurityVerdict {
        allowed,
        disposition: if allowed { "ALLOW" } else { "DENY" }.to_string(),
        reason: reason.into(),
        rule: rule.to_string(),
        decision_id: decision_id(bound, allowed, rule),
        policy_version: POLICY_VERSION.to_string(),
        manifest_hash: bound.manifest_hash.clone(),
        normalized_source_paths: sources,
        normalized_target_paths: targets,
    }
}

fn validate(
    request: &BackupSecurityRequest,
) -> Result<(Vec<String>, Vec<String>), (&'static str, String)> {
    if request.process_id != std::process::id() {
        return Err(("process_binding", "request process does not match caller".to_string()));
    }
    if !safe_id(&request.operation_id)
        || !valid_hash(&request.manifest_hash)
        || request
            .snapshot_id
            .as_ref()
            .is_some_and(|value| !valid_hash(value))
    {
        return Err(("hash_contract", "operation or hash contract is invalid".to_string()));
    }
    if !matches!(
        request.actor_role.as_str(),
        "artifact_controller" | "deterministic_authority" | "architect"
    ) {
        return Err(("actor_role", "backup actor role is not allowlisted".to_string()));
    }
    if request.max_bytes == 0
        || request.max_bytes > MAX_OPERATION_BYTES
        || request.min_free_bytes < MIN_FREE_BYTES_FLOOR
    {
        return Err(("resource_ceiling", "backup resource contract is invalid".to_string()));
    }
    if request.source_paths.len() > 128 || request.target_paths.len() > 32 {
        return Err(("path_contract", "too many roots in backup request".to_string()));
    }

    let viv = normalize_path(VIV_ROOT);
    let vault = normalize_path(VAULT_ROOT);
    let evidence = normalize_path(EVIDENCE_ROOT);
    let staging = normalize_path(RESTORE_STAGING_ROOT);
    let mut sources = Vec::new();
    let mut targets = Vec::new();
    for raw in &request.source_paths {
        let normalized = path_contract(raw).map_err(|e| ("path_contract", e))?;
        sources.push(normalized);
    }
    for raw in &request.target_paths {
        let normalized = path_contract(raw).map_err(|e| ("path_contract", e))?;
        targets.push(normalized);
    }

    let allowed = match request.action {
        BackupAction::Snapshot => {
            request.actor_role != "architect"
                && sources
                    .iter()
                    .all(|path| within_root(path, &viv) || exact_external(path))
                && !sources.iter().any(|path| within_root(path, &vault))
                && targets
                    .iter()
                    .all(|path| within_root(path, &vault) || within_root(path, &evidence))
        }
        BackupAction::Verify => {
            sources.iter().all(|path| within_root(path, &vault))
                && targets
                    .iter()
                    .all(|path| within_root(path, &evidence) || within_root(path, &vault))
        }
        BackupAction::RestoreStage => {
            request.actor_role == "deterministic_authority"
                && sources.iter().all(|path| within_root(path, &vault))
                && targets.iter().all(|path| within_root(path, &staging))
        }
        BackupAction::RestoreCommit => {
            request.actor_role == "architect"
                && request.architect_approved
                && sources.iter().all(|path| within_root(path, &staging))
                && targets
                    .iter()
                    .all(|path| within_root(path, &viv) || exact_external(path))
        }
        BackupAction::Prune => {
            request.actor_role == "architect"
                && request.architect_approved
                && sources.is_empty()
                && targets.iter().all(|path| within_root(path, &vault))
        }
        BackupAction::Replicate => false,
    };
    if !allowed {
        let rule = match request.action {
            BackupAction::RestoreCommit if !request.architect_approved => "architect_approval",
            BackupAction::Replicate => "replication_unconfigured",
            _ => "capability_matrix",
        };
        return Err((rule, "action, actor, and paths are not an approved combination".to_string()));
    }
    Ok((sources, targets))
}

pub fn authorize(raw: &str) -> BackupSecurityVerdict {
    if raw.len() > MAX_REQUEST_BYTES {
        return verdict(None, false, "request_schema", "backup request is too large", vec![], vec![]);
    }
    let request: BackupSecurityRequest = match serde_json::from_str(raw) {
        Ok(request) => request,
        Err(error) => {
            return verdict(
                None,
                false,
                "request_schema",
                error.to_string(),
                vec![],
                vec![],
            )
        }
    };
    let _ledger_lock = match acquire_ledger_lock() {
        Ok(lock) => lock,
        Err(error) => {
            return verdict(
                Some(&request),
                false,
                "ledger_busy",
                error,
                vec![],
                vec![],
            )
        }
    };
    if !verify_ledger().ok {
        return verdict(
            Some(&request),
            false,
            "ledger_integrity",
            "backup ledger integrity failed",
            vec![],
            vec![],
        );
    }
    let outcome = validate(&request);
    let result = match outcome {
        Ok((sources, targets)) => verdict(
            Some(&request),
            true,
            "backup_capability",
            "approved",
            sources,
            targets,
        ),
        Err((rule, reason)) => verdict(Some(&request), false, rule, reason, vec![], vec![]),
    };
    append_ledger("backup_authorize", &request, &result);
    result
}

fn ledger_hash(row: &LedgerRow) -> String {
    let encoded = serde_json::to_vec(&json!({
        "at_epoch": row.at_epoch,
        "event": row.event,
        "allowed": row.allowed,
        "rule": row.rule,
        "reason": row.reason,
        "operation_id": row.operation_id,
        "snapshot_id": row.snapshot_id,
        "manifest_hash": row.manifest_hash,
        "decision_id": row.decision_id,
        "previous_hash": row.previous_hash,
    }))
    .unwrap_or_default();
    sha256_bytes(&encoded)
}

fn append_ledger(
    event: &str,
    request: &BackupSecurityRequest,
    result: &BackupSecurityVerdict,
) {
    let status = verify_ledger();
    if !status.ok {
        return;
    }
    let path = PathBuf::from(BACKUP_LEDGER_PATH);
    if let Some(parent) = path.parent() {
        if fs::create_dir_all(parent).is_err() {
            return;
        }
    }
    let mut row = LedgerRow {
        at_epoch: now_epoch(),
        event: event.to_string(),
        allowed: result.allowed,
        rule: result.rule.clone(),
        reason: result.reason.clone(),
        operation_id: request.operation_id.clone(),
        snapshot_id: request.snapshot_id.clone(),
        manifest_hash: request.manifest_hash.clone(),
        decision_id: result.decision_id.clone(),
        previous_hash: status.head,
        event_hash: String::new(),
    };
    row.event_hash = ledger_hash(&row);
    if let Ok(mut handle) = OpenOptions::new().create(true).append(true).open(path) {
        if let Ok(encoded) = serde_json::to_string(&row) {
            let _ = writeln!(handle, "{encoded}");
            let _ = handle.flush();
            let _ = handle.sync_all();
        }
    }
}

pub fn verify_ledger() -> BackupLedgerStatus {
    let path = PathBuf::from(BACKUP_LEDGER_PATH);
    if !path.exists() {
        return BackupLedgerStatus {
            ok: true,
            events: 0,
            head: "0".repeat(64),
            error: None,
            policy_version: POLICY_VERSION.to_string(),
        };
    }
    let file = match File::open(&path) {
        Ok(file) => file,
        Err(error) => {
            return BackupLedgerStatus {
                ok: false,
                events: 0,
                head: String::new(),
                error: Some(error.to_string()),
                policy_version: POLICY_VERSION.to_string(),
            }
        }
    };
    let mut previous = "0".repeat(64);
    let mut events = 0;
    for line in BufReader::new(file).lines() {
        let line = match line {
            Ok(line) if !line.trim().is_empty() => line,
            Ok(_) => continue,
            Err(error) => {
                return BackupLedgerStatus {
                    ok: false,
                    events,
                    head: previous,
                    error: Some(error.to_string()),
                    policy_version: POLICY_VERSION.to_string(),
                }
            }
        };
        let row: LedgerRow = match serde_json::from_str(&line) {
            Ok(row) => row,
            Err(error) => {
                return BackupLedgerStatus {
                    ok: false,
                    events,
                    head: previous,
                    error: Some(format!("malformed ledger row: {error}")),
                    policy_version: POLICY_VERSION.to_string(),
                }
            }
        };
        if row.previous_hash != previous || ledger_hash(&row) != row.event_hash {
            return BackupLedgerStatus {
                ok: false,
                events,
                head: previous,
                error: Some("backup ledger hash-chain mismatch".to_string()),
                policy_version: POLICY_VERSION.to_string(),
            };
        }
        previous = row.event_hash;
        events += 1;
    }
    BackupLedgerStatus {
        ok: true,
        events,
        head: previous,
        error: None,
        policy_version: POLICY_VERSION.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(action: BackupAction) -> BackupSecurityRequest {
        BackupSecurityRequest {
            action,
            operation_id: "backup-test".to_string(),
            snapshot_id: Some("a".repeat(64)),
            actor_role: "artifact_controller".to_string(),
            manifest_hash: "b".repeat(64),
            source_paths: vec!["L:/Continue/Viv/foundation/model_config.json".to_string()],
            target_paths: vec![
                "L:/Continue/Viv/foundation/artifacts/auto/backup_core/vault".to_string(),
            ],
            process_id: std::process::id(),
            max_bytes: 1024,
            min_free_bytes: MIN_FREE_BYTES_FLOOR,
            architect_approved: false,
        }
    }

    #[test]
    fn snapshot_allows_viv_to_vault_only() {
        assert!(validate(&request(BackupAction::Snapshot)).is_ok());
        let mut escaped = request(BackupAction::Snapshot);
        escaped.source_paths = vec!["L:/Continue/Viv/../private.txt".to_string()];
        assert!(matches!(validate(&escaped), Err(("path_contract", _))));
    }

    #[test]
    fn restore_commit_requires_architect_and_approval() {
        let mut restore = request(BackupAction::RestoreCommit);
        restore.source_paths =
            vec!["L:/Continue/Viv/sandbox/restore_staging/r1/file.bin".to_string()];
        restore.target_paths = vec!["L:/Continue/Viv/foundation/model_config.json".to_string()];
        assert!(validate(&restore).is_err());
        restore.actor_role = "architect".to_string();
        restore.architect_approved = true;
        assert!(validate(&restore).is_ok());
    }

    #[test]
    fn replication_fails_closed_until_configured() {
        let replicate = request(BackupAction::Replicate);
        assert!(matches!(
            validate(&replicate),
            Err(("replication_unconfigured", _))
        ));
    }

    #[test]
    fn external_paths_are_exact_not_prefixes() {
        let mut snapshot = request(BackupAction::Snapshot);
        snapshot.source_paths =
            vec!["L:/Continue/.venv/Lib/site-packages/security_core.pyd.evil".to_string()];
        assert!(validate(&snapshot).is_err());
    }
}
