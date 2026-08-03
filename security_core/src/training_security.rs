//! Deny-by-default training capabilities.
//!
//! This module does not widen the ordinary filesystem governor.  It grants
//! short-lived, process-bound leases for one isolated staging directory and
//! performs the only allowed commit into `models/Training/runs`.

use crate::laws::{effective_dormancy_threshold, TRAINING_SOFT_FLOOR};
use crate::normalize::{normalize_path, path_has_traversal};
use hex::encode as hex_encode;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use windows_sys::Win32::Foundation::LocalFree;
#[cfg(windows)]
use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
use windows_sys::Win32::Security::Cryptography::{
    BCryptGenRandom, CryptProtectData, CryptUnprotectData, BCRYPT_USE_SYSTEM_PREFERRED_RNG,
    CRYPTPROTECT_UI_FORBIDDEN, CRYPT_INTEGER_BLOB,
};
#[cfg(windows)]
use windows_sys::Win32::Storage::FileSystem::{
    CreateFileW, GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION, FILE_ATTRIBUTE_NORMAL,
    FILE_FLAG_OPEN_REPARSE_POINT, FILE_READ_ATTRIBUTES, FILE_SHARE_DELETE, FILE_SHARE_READ,
    FILE_SHARE_WRITE, OPEN_EXISTING,
};

const STAGING_ROOT: &str = "L:/Continue/Viv/sandbox/training_staging";
const RUNS_ROOT: &str = "L:/Continue/Viv/foundation/models/Training/runs";
const QUARANTINE_ROOT: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/security_training_quarantine";
const LEDGER_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/audit/security_training_events.jsonl";
const LEDGER_LOCK_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/audit/security_training_events.lock";
const STAGE1_REGISTRY_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_training_tree/stage1/stage1_registry_v1.json";
const STAGE1_CORPUS_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_training_tree/stage1/stage1_judged_v1.jsonl";
const MOUTH_IDENTITY_REGISTRY_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_training_tree/stage1_mouth_identity_v1/stage1_mouth_identity_registry_v1.json";
const MOUTH_IDENTITY_CORPUS_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_training_tree/stage1_mouth_identity_v1/stage1_mouth_identity_judged_v1.jsonl";
const MOUTH_IDENTITY_V2_REGISTRY_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_training_tree/stage1_mouth_identity_v2/stage1_mouth_identity_registry_v1.json";
const MOUTH_IDENTITY_V2_CORPUS_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_training_tree/stage1_mouth_identity_v2/stage1_mouth_identity_judged_v1.jsonl";
const MOUTH_IDENTITY_V2_1_REGISTRY_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_training_tree/stage1_mouth_identity_v2_1/stage1_mouth_identity_registry_v1.json";
const MOUTH_IDENTITY_V2_1_CORPUS_PATH: &str =
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_training_tree/stage1_mouth_identity_v2_1/stage1_mouth_identity_judged_v1.jsonl";
const PREEXISTING_FROZEN_PATHS: &[&str] = &[
    "L:/Continue/Viv/foundation/artifacts/auto/shadow_judge/holdout_registry.json",
    "L:/Continue/Viv/foundation/artifacts/auto/shadow_judge/holdout_pack.jsonl",
    "L:/Continue/Viv/foundation/artifacts/auto/shadow_judge/deploy_test_registry.json",
    "L:/Continue/Viv/foundation/artifacts/auto/shadow_judge/deploy_test_pack.jsonl",
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_parity/development_registry_v1.json",
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_parity/development_pack_v1.jsonl",
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_parity/multiturn_registry_v1.json",
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_parity/multiturn_pack_v1.json",
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_training_tree/seed_registry_v2.json",
    "L:/Continue/Viv/foundation/artifacts/auto/openaster_training_tree/seed_nodes_v2.jsonl",
];
const MAX_REQUEST_BYTES: usize = 256 * 1024;
const MAX_QUARANTINE_BYTES: usize = 1024 * 1024;
const MAX_LEASE_SECONDS: u64 = 4 * 60 * 60;
const MAX_VRAM_MIB: u64 = 8192;
const MAX_RAM_MIB: u64 = 28672;
const MAX_DISK_MIB: u64 = 8192;
const MAX_SEQUENCE_CAP: u64 = 384;

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum TrainingAction {
    Ingest,
    Draft,
    Judge,
    Quarantine,
    BeginRun,
    CommitRun,
    Evaluate,
    Freeze,
    Promote,
    Deploy,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TrainingSecurityRequest {
    pub action: TrainingAction,
    pub stage_id: String,
    pub run_id: String,
    pub model_role: String,
    pub manifest_hash: String,
    pub source_hashes: Vec<String>,
    pub paths: Vec<String>,
    pub artifact_class: String,
    pub master_s_n: f64,
    pub process_id: u32,
    pub max_duration_s: u64,
    pub max_vram_mib: u64,
    pub max_ram_mib: u64,
    pub max_disk_mib: u64,
    pub sequence_cap: u64,
    pub lora_rank: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct TrainingSecurityVerdict {
    pub allowed: bool,
    pub disposition: String,
    pub reason: String,
    pub rule: String,
    pub decision_id: String,
    pub policy_version: String,
    pub manifest_hash: String,
    pub normalized_paths: Vec<String>,
    pub lease_token: Option<String>,
    pub staging_root: Option<String>,
    pub final_root: Option<String>,
    pub quarantine_id: Option<String>,
    pub payload: Option<String>,
    pub training_soft_band: bool,
    pub master_s_n: Option<f64>,
    pub training_soft_floor: Option<f64>,
    pub hard_threshold: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct LedgerStatus {
    pub ok: bool,
    pub events: usize,
    pub head: String,
    pub error: Option<String>,
    pub policy_version: String,
}

#[derive(Debug, Clone)]
struct Lease {
    token_hash: String,
    binding_hash: String,
    run_id: String,
    stage_id: String,
    manifest_hash: String,
    process_id: u32,
    staging_root: PathBuf,
    final_root: PathBuf,
    expires_at: u64,
    max_disk_bytes: u64,
    lora_rank: u64,
    consumed: bool,
}

#[derive(Default)]
struct SecurityState {
    leases: HashMap<String, Lease>,
    previous_event_hash: String,
}

static STATE: OnceLock<Mutex<SecurityState>> = OnceLock::new();

fn state() -> &'static Mutex<SecurityState> {
    STATE.get_or_init(|| Mutex::new(SecurityState::default()))
}

fn now_epoch() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn sha256_bytes(data: &[u8]) -> String {
    hex_encode(Sha256::digest(data))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct FreezeTarget {
    registry_path: &'static str,
    corpus_path: &'static str,
    stage_id: &'static str,
}

const FREEZE_TARGETS: &[FreezeTarget] = &[
    FreezeTarget {
        registry_path: STAGE1_REGISTRY_PATH,
        corpus_path: STAGE1_CORPUS_PATH,
        stage_id: "evidence_truth",
    },
    FreezeTarget {
        registry_path: MOUTH_IDENTITY_REGISTRY_PATH,
        corpus_path: MOUTH_IDENTITY_CORPUS_PATH,
        stage_id: "mouth_identity",
    },
    FreezeTarget {
        registry_path: MOUTH_IDENTITY_V2_REGISTRY_PATH,
        corpus_path: MOUTH_IDENTITY_V2_CORPUS_PATH,
        stage_id: "mouth_identity",
    },
    FreezeTarget {
        registry_path: MOUTH_IDENTITY_V2_1_REGISTRY_PATH,
        corpus_path: MOUTH_IDENTITY_V2_1_CORPUS_PATH,
        stage_id: "mouth_identity",
    },
];

fn freeze_target_for_registry(normalized: &str) -> Option<FreezeTarget> {
    FREEZE_TARGETS
        .iter()
        .copied()
        .find(|target| normalized == normalize_path(target.registry_path))
}

fn registry_for_frozen_corpus(normalized: &str) -> Option<&'static str> {
    FREEZE_TARGETS
        .iter()
        .find(|target| normalized == normalize_path(target.corpus_path))
        .map(|target| target.registry_path)
}

fn resolve_freeze_target(
    paths: &[String],
    stage_id: &str,
) -> Result<FreezeTarget, (&'static str, String)> {
    if paths.len() != 1 {
        return Err((
            "freeze_target",
            "freeze requires exactly one allowlisted registry target".to_string(),
        ));
    }
    let Some(target) = freeze_target_for_registry(&paths[0]) else {
        return Err((
            "freeze_target",
            "only an exact allowlisted training registry supports create-once freeze".to_string(),
        ));
    };
    if stage_id != target.stage_id {
        return Err((
            "freeze_stage",
            format!("registry target requires stage_id {}", target.stage_id),
        ));
    }
    Ok(target)
}

fn lease_binding_hash(request: &TrainingSecurityRequest) -> String {
    let value = json!({
        "stage_id": request.stage_id,
        "run_id": request.run_id,
        "model_role": request.model_role,
        "manifest_hash": request.manifest_hash,
        "source_hashes": request.source_hashes,
        "paths": request.paths,
        "artifact_class": request.artifact_class,
        "process_id": request.process_id,
        "max_duration_s": request.max_duration_s,
        "max_vram_mib": request.max_vram_mib,
        "max_ram_mib": request.max_ram_mib,
        "max_disk_mib": request.max_disk_mib,
        "sequence_cap": request.sequence_cap,
        "lora_rank": request.lora_rank,
    });
    sha256_bytes(&serde_json::to_vec(&value).unwrap_or_default())
}

fn valid_hash(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn safe_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
        && !value.contains("..")
}

fn within_root(path: &str, root: &str) -> bool {
    path == root
        || path
            .strip_prefix(root)
            .is_some_and(|suffix| suffix.starts_with('/'))
}

fn require_plain_root(path: &Path) -> Result<(), String> {
    if !path.is_dir() {
        return Err(format!("trusted root missing: {}", path.display()));
    }
    if is_reparse(path)? {
        return Err(format!(
            "trusted root is a reparse point: {}",
            path.display()
        ));
    }
    Ok(())
}

fn deny(
    request: Option<&TrainingSecurityRequest>,
    rule: &str,
    reason: impl Into<String>,
) -> TrainingSecurityVerdict {
    let manifest = request.map(|r| r.manifest_hash.clone()).unwrap_or_default();
    let hard_threshold = effective_dormancy_threshold();
    let training_soft_band = request.is_some_and(|r| {
        matches!(r.action, TrainingAction::BeginRun | TrainingAction::CommitRun)
            && r.master_s_n.is_finite()
            && r.master_s_n >= TRAINING_SOFT_FLOOR
            && r.master_s_n < hard_threshold
    });
    let reason_string = reason.into();
    let decision_id =
        random_hex(16).unwrap_or_else(|_| sha256_bytes(reason_string.as_bytes())[..32].to_string());
    let verdict = TrainingSecurityVerdict {
        allowed: false,
        disposition: "DENY".to_string(),
        reason: reason_string,
        rule: rule.to_string(),
        decision_id,
        policy_version: env!("CARGO_PKG_VERSION").to_string(),
        manifest_hash: manifest,
        normalized_paths: vec![],
        lease_token: None,
        staging_root: None,
        final_root: None,
        quarantine_id: None,
        payload: None,
        training_soft_band,
        master_s_n: request.map(|r| r.master_s_n),
        training_soft_floor: request.map(|_| TRAINING_SOFT_FLOOR),
        hard_threshold: request.map(|_| hard_threshold),
    };
    append_ledger("deny", &verdict, json!({}));
    verdict
}

fn allow(
    request: &TrainingSecurityRequest,
    rule: &str,
    normalized_paths: Vec<String>,
) -> TrainingSecurityVerdict {
    let hard_threshold = effective_dormancy_threshold();
    let training_soft_band = matches!(
        request.action,
        TrainingAction::BeginRun | TrainingAction::CommitRun
    ) && request.master_s_n.is_finite()
        && request.master_s_n >= TRAINING_SOFT_FLOOR
        && request.master_s_n < hard_threshold;
    let verdict = TrainingSecurityVerdict {
        allowed: true,
        disposition: "ALLOW".to_string(),
        reason: "OK".to_string(),
        rule: rule.to_string(),
        decision_id: random_hex(16)
            .unwrap_or_else(|_| sha256_bytes(request.manifest_hash.as_bytes())[..32].to_string()),
        policy_version: env!("CARGO_PKG_VERSION").to_string(),
        manifest_hash: request.manifest_hash.clone(),
        normalized_paths,
        lease_token: None,
        staging_root: None,
        final_root: None,
        quarantine_id: None,
        payload: None,
        training_soft_band,
        master_s_n: Some(request.master_s_n),
        training_soft_floor: Some(TRAINING_SOFT_FLOOR),
        hard_threshold: Some(hard_threshold),
    };
    append_ledger(
        "allow",
        &verdict,
        json!({"action": request.action, "run_id": request.run_id}),
    );
    verdict
}

fn parse_request(raw: &str) -> Result<TrainingSecurityRequest, String> {
    if raw.is_empty() || raw.len() > MAX_REQUEST_BYTES {
        return Err("request_size_invalid".to_string());
    }
    let mut deserializer = serde_json::Deserializer::from_str(raw);
    let request = TrainingSecurityRequest::deserialize(&mut deserializer)
        .map_err(|error| format!("request_schema:{error}"))?;
    deserializer
        .end()
        .map_err(|error| format!("request_trailing_data:{error}"))?;
    Ok(request)
}

fn validate_request(
    request: &TrainingSecurityRequest,
) -> Result<Vec<String>, (&'static str, String)> {
    if let Err(error) = verify_ledger_file(Path::new(LEDGER_PATH)) {
        return Err(("ledger_integrity", error));
    }
    if request.action == TrainingAction::Deploy {
        return Err((
            "training_deploy_disabled",
            "DEPLOY is disabled for this milestone".to_string(),
        ));
    }
    if request.process_id != std::process::id() {
        return Err((
            "process_binding",
            "request process_id does not match caller".to_string(),
        ));
    }
    let hard_threshold = effective_dormancy_threshold();
    let stability_floor = if matches!(
        request.action,
        TrainingAction::BeginRun | TrainingAction::CommitRun
    ) {
        TRAINING_SOFT_FLOOR
    } else {
        hard_threshold
    };
    if !request.master_s_n.is_finite() || request.master_s_n < stability_floor {
        return Err((
            "law5_stability",
            format!(
                "Master S_n {:.4} is below {:.4}",
                request.master_s_n,
                stability_floor
            ),
        ));
    }
    if !safe_id(&request.run_id) || !safe_id(&request.stage_id) {
        return Err(("identifier", "run_id or stage_id is unsafe".to_string()));
    }
    if !valid_hash(&request.manifest_hash)
        || request.source_hashes.iter().any(|hash| !valid_hash(hash))
    {
        return Err((
            "hash_contract",
            "manifest/source hash is invalid".to_string(),
        ));
    }
    if !matches!(
        request.model_role.as_str(),
        "qwen_teacher"
            | "openaster_target"
            | "parity_mouth_eval"
            | "cpu_semantic_sensor"
            | "deterministic_authority"
            | "artifact_controller"
    ) {
        return Err(("model_role", "model role is not allowlisted".to_string()));
    }
    if request.max_duration_s == 0
        || request.max_duration_s > MAX_LEASE_SECONDS
        || request.max_vram_mib > MAX_VRAM_MIB
        || request.max_ram_mib > MAX_RAM_MIB
        || request.max_disk_mib == 0
        || request.max_disk_mib > MAX_DISK_MIB
        || request.sequence_cap == 0
        || request.sequence_cap > MAX_SEQUENCE_CAP
        || request.lora_rank > 16
    {
        return Err((
            "resource_ceiling",
            "requested resource ceiling is invalid".to_string(),
        ));
    }
    if !matches!(
        request.artifact_class.as_str(),
        "curriculum_record"
            | "draft_set"
            | "judge_record"
            | "training_evidence"
            | "lora_adapter"
            | "evaluation_report"
            | "candidate_pointer"
            | "encrypted_quarantine"
    ) {
        return Err((
            "artifact_class",
            "artifact class is not allowlisted".to_string(),
        ));
    }
    let capability_ok = match request.action {
        TrainingAction::Ingest => {
            request.artifact_class == "curriculum_record"
                && matches!(
                    request.model_role.as_str(),
                    "artifact_controller" | "deterministic_authority"
                )
        }
        TrainingAction::Draft => {
            request.artifact_class == "draft_set" && request.model_role == "qwen_teacher"
        }
        TrainingAction::Judge => {
            request.artifact_class == "judge_record"
                && matches!(
                    request.model_role.as_str(),
                    "cpu_semantic_sensor" | "deterministic_authority"
                )
        }
        TrainingAction::Quarantine => {
            request.artifact_class == "encrypted_quarantine"
                && request.model_role == "deterministic_authority"
        }
        TrainingAction::BeginRun | TrainingAction::CommitRun => {
            (request.artifact_class == "lora_adapter" && request.model_role == "openaster_target")
                || (request.artifact_class == "draft_set" && request.model_role == "qwen_teacher")
        }
        TrainingAction::Evaluate => {
            matches!(
                request.artifact_class.as_str(),
                "training_evidence" | "evaluation_report" | "judge_record"
            ) && matches!(
                request.model_role.as_str(),
                "qwen_teacher"
                    | "openaster_target"
                    | "parity_mouth_eval"
                    | "deterministic_authority"
                    | "artifact_controller"
            )
        }
        TrainingAction::Freeze => {
            request.artifact_class == "training_evidence"
                && request.model_role == "deterministic_authority"
        }
        TrainingAction::Promote => {
            request.artifact_class == "candidate_pointer"
                && request.model_role == "deterministic_authority"
        }
        TrainingAction::Deploy => false,
    };
    if !capability_ok {
        return Err((
            "capability_matrix",
            "action, model role, and artifact class are not an approved combination".to_string(),
        ));
    }
    let mut paths = Vec::new();
    for raw in &request.paths {
        if raw.len() > 512
            || path_has_traversal(raw)
            || raw.contains(':') && raw.matches(':').count() > 1
        {
            return Err(("path_contract", format!("unsafe path: {raw}")));
        }
        let normalized = normalize_path(raw);
        let allowed = within_root(&normalized, &normalize_path(STAGING_ROOT))
            || within_root(&normalized, &normalize_path(RUNS_ROOT))
            || within_root(&normalized, &normalize_path(QUARANTINE_ROOT))
            || within_root(&normalized, "l:/continue/viv/foundation/artifacts");
        if !allowed {
            return Err((
                "path_contract",
                format!("path outside training roots: {normalized}"),
            ));
        }
        if normalized == normalize_path(LEDGER_PATH) {
            return Err((
                "ledger_protected",
                "the training ledger cannot authorize its own overwrite".to_string(),
            ));
        }
        if PREEXISTING_FROZEN_PATHS
            .iter()
            .any(|path| normalized == normalize_path(path))
        {
            return Err((
                "preexisting_frozen_artifact",
                "frozen evaluation or seed artifact is immutable in this milestone".to_string(),
            ));
        }
        if freeze_target_for_registry(&normalized).is_some()
            && request.action != TrainingAction::Freeze
        {
            return Err((
                "frozen_registry",
                "training registry is create-once through FREEZE".to_string(),
            ));
        }
        if let Some(registry_path) = registry_for_frozen_corpus(&normalized) {
            if Path::new(registry_path).exists() {
                return Err((
                    "frozen_corpus",
                    "training corpus is immutable after registry freeze".to_string(),
                ));
            }
        }
        if !matches!(
            request.action,
            TrainingAction::BeginRun | TrainingAction::CommitRun
        ) {
            let extension = Path::new(&normalized)
                .extension()
                .and_then(|value| value.to_str())
                .unwrap_or("");
            if !matches!(extension, "json" | "jsonl" | "md" | "log") {
                return Err((
                    "artifact_extension",
                    format!("typed training artifact extension denied: {extension}"),
                ));
            }
        }
        paths.push(normalized);
    }
    Ok(paths)
}

pub fn authorize(raw: &str) -> TrainingSecurityVerdict {
    let request = match parse_request(raw) {
        Ok(request) => request,
        Err(error) => return deny(None, "request_schema", error),
    };
    if matches!(
        request.action,
        TrainingAction::BeginRun | TrainingAction::CommitRun
    ) {
        return deny(
            Some(&request),
            "lease",
            "run lifecycle actions require the dedicated lease API",
        );
    }
    match validate_request(&request) {
        Ok(paths) => allow(&request, "training_authorize", paths),
        Err((rule, reason)) => deny(Some(&request), rule, reason),
    }
}

pub fn freeze_registry(raw: &str, payload: &str) -> TrainingSecurityVerdict {
    let request = match parse_request(raw) {
        Ok(request) => request,
        Err(error) => return deny(None, "request_schema", error),
    };
    if request.action != TrainingAction::Freeze {
        return deny(Some(&request), "action_contract", "FREEZE required");
    }
    let paths = match validate_request(&request) {
        Ok(paths) => paths,
        Err((rule, reason)) => return deny(Some(&request), rule, reason),
    };
    let target = match resolve_freeze_target(&paths, &request.stage_id) {
        Ok(target) => target,
        Err((rule, reason)) => return deny(Some(&request), rule, reason),
    };
    if payload.is_empty() || payload.len() > 4 * 1024 * 1024 {
        return deny(
            Some(&request),
            "freeze_payload",
            "freeze payload size invalid",
        );
    }
    if sha256_bytes(payload.as_bytes()) != request.manifest_hash {
        return deny(
            Some(&request),
            "freeze_manifest",
            "freeze payload does not match manifest hash",
        );
    }
    let payload_value = match serde_json::from_str::<Value>(payload) {
        Ok(value) => value,
        Err(_) => {
            return deny(
                Some(&request),
                "freeze_payload",
                "freeze payload is not valid JSON",
            )
        }
    };
    if payload_value.get("stage_id").and_then(Value::as_str) != Some(target.stage_id) {
        return deny(
            Some(&request),
            "freeze_stage",
            "freeze payload stage_id does not match the allowlisted registry",
        );
    }
    let corpus = Path::new(target.corpus_path);
    let corpus_bytes = match fs::read(corpus) {
        Ok(bytes) => bytes,
        Err(error) => {
            return deny(
                Some(&request),
                "freeze_corpus",
                format!("allowlisted judged corpus is unavailable: {error}"),
            )
        }
    };
    let corpus_sha256 = sha256_bytes(&corpus_bytes);
    if payload_value.get("corpus_sha256").and_then(Value::as_str) != Some(corpus_sha256.as_str()) {
        return deny(
            Some(&request),
            "freeze_corpus",
            "freeze payload corpus_sha256 does not match the exact allowlisted judged corpus",
        );
    }
    let path = Path::new(target.registry_path);
    if let Some(parent) = path.parent() {
        if let Err(error) = fs::create_dir_all(parent) {
            return deny(Some(&request), "freeze_parent", error.to_string());
        }
        if let Err(error) = require_plain_root(parent) {
            return deny(Some(&request), "trusted_root", error);
        }
    }
    let mut file = match OpenOptions::new().create_new(true).write(true).open(path) {
        Ok(file) => file,
        Err(error) => return deny(Some(&request), "freeze_collision", error.to_string()),
    };
    if let Err(error) = file
        .write_all(payload.as_bytes())
        .and_then(|_| file.sync_all())
    {
        return deny(Some(&request), "freeze_write", error.to_string());
    }
    let verdict = allow(&request, "training_registry_freeze", paths);
    append_ledger(
        "registry_freeze",
        &verdict,
        json!({
            "path": target.registry_path,
            "corpus_path": target.corpus_path,
            "corpus_sha256": corpus_sha256,
            "stage_id": target.stage_id,
            "bytes": payload.len()
        }),
    );
    verdict
}

pub fn begin_lease(raw: &str) -> TrainingSecurityVerdict {
    let request = match parse_request(raw) {
        Ok(request) => request,
        Err(error) => return deny(None, "request_schema", error),
    };
    if request.action != TrainingAction::BeginRun {
        return deny(Some(&request), "action_contract", "BEGIN_RUN required");
    }
    let paths = match validate_request(&request) {
        Ok(paths) => paths,
        Err((rule, reason)) => return deny(Some(&request), rule, reason),
    };
    let staging = PathBuf::from(STAGING_ROOT).join(&request.run_id);
    let final_root = PathBuf::from(RUNS_ROOT).join(&request.run_id);
    let expected_paths = vec![
        normalize_path(&staging.to_string_lossy()),
        normalize_path(&final_root.to_string_lossy()),
    ];
    if paths != expected_paths {
        return deny(
            Some(&request),
            "lease_path_binding",
            "BEGIN_RUN paths must be the exact staging and final roots",
        );
    }
    if staging.exists() || final_root.exists() {
        return deny(
            Some(&request),
            "run_collision",
            "staging or final run already exists",
        );
    }
    if let Err(error) = fs::create_dir_all(Path::new(STAGING_ROOT)) {
        return deny(Some(&request), "staging_create", error.to_string());
    }
    if let Err(error) = require_plain_root(Path::new(STAGING_ROOT)) {
        return deny(Some(&request), "trusted_root", error);
    }
    if let Err(error) = fs::create_dir(&staging) {
        return deny(Some(&request), "staging_create", error.to_string());
    }
    let token = match random_hex(32) {
        Ok(token) => token,
        Err(error) => {
            let _ = fs::remove_dir(&staging);
            return deny(Some(&request), "rng", error);
        }
    };
    let token_hash = sha256_bytes(token.as_bytes());
    let lease = Lease {
        token_hash: token_hash.clone(),
        binding_hash: lease_binding_hash(&request),
        run_id: request.run_id.clone(),
        stage_id: request.stage_id.clone(),
        manifest_hash: request.manifest_hash.clone(),
        process_id: request.process_id,
        staging_root: staging.clone(),
        final_root: final_root.clone(),
        expires_at: now_epoch() + request.max_duration_s,
        max_disk_bytes: request.max_disk_mib * 1024 * 1024,
        lora_rank: request.lora_rank,
        consumed: false,
    };
    state()
        .lock()
        .expect("security state poisoned")
        .leases
        .insert(token_hash.clone(), lease);
    let mut verdict = allow(&request, "training_lease_begin", paths);
    verdict.lease_token = Some(token);
    verdict.staging_root = Some(staging.to_string_lossy().replace('\\', "/"));
    verdict.final_root = Some(final_root.to_string_lossy().replace('\\', "/"));
    append_ledger(
        "lease_begin",
        &verdict,
        json!({"token_hash": token_hash, "expires_at": now_epoch() + request.max_duration_s}),
    );
    verdict
}

pub fn commit_lease(token: &str, raw: &str) -> TrainingSecurityVerdict {
    let request = match parse_request(raw) {
        Ok(request) => request,
        Err(error) => return deny(None, "request_schema", error),
    };
    if request.action != TrainingAction::CommitRun {
        return deny(Some(&request), "action_contract", "COMMIT_RUN required");
    }
    if let Err((rule, reason)) = validate_request(&request) {
        return deny(Some(&request), rule, reason);
    }
    let token_hash = sha256_bytes(token.as_bytes());
    let presented_binding_hash = lease_binding_hash(&request);
    let lease = {
        let mut guard = state().lock().expect("security state poisoned");
        match guard.leases.get_mut(&token_hash) {
            None => Err("unknown or replayed lease"),
            Some(lease)
                if lease.consumed
                    || lease.expires_at < now_epoch()
                    || lease.process_id != std::process::id()
                    || lease.run_id != request.run_id
                    || lease.stage_id != request.stage_id
                    || lease.manifest_hash != request.manifest_hash
                    || lease.token_hash != token_hash =>
            {
                lease.consumed = true;
                Err("expired, consumed, or mismatched lease")
            }
            Some(lease) if lease.binding_hash != presented_binding_hash => {
                lease.consumed = true;
                Err("lease policy binding mismatch")
            }
            Some(lease) => {
                lease.consumed = true;
                Ok(lease.clone())
            }
        }
    };
    let lease = match lease {
        Ok(lease) => lease,
        Err(error) => return deny(Some(&request), "lease", error),
    };
    let inventory =
        match inspect_staging(&lease.staging_root, lease.max_disk_bytes, lease.lora_rank) {
            Ok(inventory) => inventory,
            Err(error) => return deny(Some(&request), "staging_inspection", error),
        };
    let has_adapter = inventory.iter().any(|entry| {
        entry
            .get("path")
            .and_then(Value::as_str)
            .is_some_and(|path| path.ends_with(".safetensors"))
    });
    if request.artifact_class == "lora_adapter" && !has_adapter {
        return deny(
            Some(&request),
            "adapter_required",
            "LoRA adapter lease contains no safetensors",
        );
    }
    if request.artifact_class != "lora_adapter" && has_adapter {
        return deny(
            Some(&request),
            "artifact_confusion",
            "non-adapter lease may not commit safetensors",
        );
    }
    if lease.final_root.exists() {
        return deny(
            Some(&request),
            "run_collision",
            "final run appeared before commit",
        );
    }
    if let Some(parent) = lease.final_root.parent() {
        if let Err(error) = fs::create_dir_all(parent) {
            return deny(Some(&request), "commit_parent", error.to_string());
        }
        if let Err(error) = require_plain_root(parent) {
            return deny(Some(&request), "trusted_root", error);
        }
    }
    let pending = lease
        .final_root
        .parent()
        .unwrap_or(Path::new(RUNS_ROOT))
        .join(format!(
            ".security_pending_{}_{}",
            lease.run_id,
            &token_hash[..12]
        ));
    if pending.exists() {
        return deny(
            Some(&request),
            "pending_collision",
            "pending commit path already exists",
        );
    }
    if let Err(error) = fs::rename(&lease.staging_root, &pending) {
        return deny(Some(&request), "atomic_stage", error.to_string());
    }
    let post_inventory = match inspect_staging(&pending, lease.max_disk_bytes, lease.lora_rank) {
        Ok(inventory) => inventory,
        Err(error) => return deny(Some(&request), "post_move_inspection", error),
    };
    if inventory != post_inventory {
        return deny(Some(&request), "toctou", "inventory changed during commit");
    }
    if let Err(error) = fs::rename(&pending, &lease.final_root) {
        return deny(Some(&request), "atomic_commit", error.to_string());
    }
    let mut verdict = allow(
        &request,
        "training_lease_commit",
        vec![lease.final_root.to_string_lossy().replace('\\', "/")],
    );
    verdict.final_root = Some(lease.final_root.to_string_lossy().replace('\\', "/"));
    append_ledger("lease_commit", &verdict, json!({"inventory": inventory}));
    verdict
}

pub fn quarantine(token: &str, record_id: &str, plaintext: &str) -> TrainingSecurityVerdict {
    if !safe_id(record_id) || plaintext.is_empty() || plaintext.len() > MAX_QUARANTINE_BYTES {
        return deny(None, "quarantine_contract", "record id or payload invalid");
    }
    let lease = match active_lease(token) {
        Ok(lease) => lease,
        Err(error) => return deny(None, "lease", error),
    };
    let ciphertext = match dpapi_protect(plaintext.as_bytes(), lease.manifest_hash.as_bytes()) {
        Ok(data) => data,
        Err(error) => return deny(None, "dpapi", error),
    };
    let directory = PathBuf::from(QUARANTINE_ROOT).join(&lease.run_id);
    if let Err(error) = fs::create_dir_all(Path::new(QUARANTINE_ROOT)) {
        return deny(None, "quarantine_write", error.to_string());
    }
    if let Err(error) = require_plain_root(Path::new(QUARANTINE_ROOT)) {
        return deny(None, "trusted_root", error);
    }
    if let Err(error) = fs::create_dir(&directory) {
        if error.kind() != std::io::ErrorKind::AlreadyExists {
            return deny(None, "quarantine_write", error.to_string());
        }
    }
    if let Err(error) = require_plain_root(&directory) {
        return deny(None, "quarantine_write", error.to_string());
    }
    let path = directory.join(format!("{record_id}.dpapi"));
    let mut file = match OpenOptions::new().create_new(true).write(true).open(&path) {
        Ok(file) => file,
        Err(error) => return deny(None, "quarantine_write", error.to_string()),
    };
    if let Err(error) = file.write_all(&ciphertext).and_then(|_| file.sync_all()) {
        return deny(None, "quarantine_write", error.to_string());
    }
    let verdict = TrainingSecurityVerdict {
        allowed: true,
        disposition: "QUARANTINE".to_string(),
        reason: "encrypted_training_only".to_string(),
        rule: "dpapi_current_user".to_string(),
        decision_id: random_hex(16).unwrap_or_default(),
        policy_version: env!("CARGO_PKG_VERSION").to_string(),
        manifest_hash: lease.manifest_hash,
        normalized_paths: vec![path.to_string_lossy().replace('\\', "/")],
        lease_token: None,
        staging_root: None,
        final_root: None,
        quarantine_id: Some(record_id.to_string()),
        payload: None,
        training_soft_band: false,
        master_s_n: None,
        training_soft_floor: None,
        hard_threshold: None,
    };
    append_ledger(
        "quarantine",
        &verdict,
        json!({"run_id": lease.run_id, "cipher_sha256": sha256_bytes(&ciphertext), "plaintext_sha256": sha256_bytes(plaintext.as_bytes()), "bytes": plaintext.len()}),
    );
    verdict
}

pub fn read_quarantine(token: &str, record_id: &str) -> TrainingSecurityVerdict {
    if !safe_id(record_id) {
        return deny(None, "quarantine_contract", "record id invalid");
    }
    let lease = match active_lease(token) {
        Ok(lease) => lease,
        Err(error) => return deny(None, "lease", error),
    };
    let path = PathBuf::from(QUARANTINE_ROOT)
        .join(&lease.run_id)
        .join(format!("{record_id}.dpapi"));
    let ciphertext = match fs::read(&path) {
        Ok(data) => data,
        Err(error) => return deny(None, "quarantine_read", error.to_string()),
    };
    let plaintext = match dpapi_unprotect(&ciphertext, lease.manifest_hash.as_bytes()) {
        Ok(data) => data,
        Err(error) => return deny(None, "dpapi", error),
    };
    let payload = match String::from_utf8(plaintext) {
        Ok(text) => text,
        Err(_) => return deny(None, "quarantine_read", "decrypted payload is not UTF-8"),
    };
    let verdict = TrainingSecurityVerdict {
        allowed: true,
        disposition: "ALLOW".to_string(),
        reason: "memory_only_training_read".to_string(),
        rule: "dpapi_current_user".to_string(),
        decision_id: random_hex(16).unwrap_or_default(),
        policy_version: env!("CARGO_PKG_VERSION").to_string(),
        manifest_hash: lease.manifest_hash,
        normalized_paths: vec![],
        lease_token: None,
        staging_root: None,
        final_root: None,
        quarantine_id: Some(record_id.to_string()),
        payload: Some(payload),
        training_soft_band: false,
        master_s_n: None,
        training_soft_floor: None,
        hard_threshold: None,
    };
    append_ledger(
        "quarantine_read",
        &verdict,
        json!({"run_id": lease.run_id, "record_id": record_id}),
    );
    verdict
}

fn active_lease(token: &str) -> Result<Lease, String> {
    let token_hash = sha256_bytes(token.as_bytes());
    let guard = state()
        .lock()
        .map_err(|_| "security state poisoned".to_string())?;
    let lease = guard
        .leases
        .get(&token_hash)
        .ok_or_else(|| "unknown lease".to_string())?;
    if lease.consumed || lease.expires_at < now_epoch() || lease.process_id != std::process::id() {
        return Err("expired, consumed, or process-mismatched lease".to_string());
    }
    Ok(lease.clone())
}

fn random_hex(bytes: usize) -> Result<String, String> {
    let mut output = vec![0u8; bytes];
    let status = unsafe {
        BCryptGenRandom(
            std::ptr::null_mut(),
            output.as_mut_ptr(),
            output.len() as u32,
            BCRYPT_USE_SYSTEM_PREFERRED_RNG,
        )
    };
    if status < 0 {
        return Err(format!("BCryptGenRandom failed: {status}"));
    }
    Ok(hex_encode(output))
}

fn append_ledger(kind: &str, verdict: &TrainingSecurityVerdict, detail: Value) {
    let path = Path::new(LEDGER_PATH);
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _file_lock = match acquire_training_ledger_lock() {
        Ok(lock) => lock,
        Err(_) => return,
    };
    let mut guard = match state().lock() {
        Ok(guard) => guard,
        Err(_) => return,
    };
    // Always refresh the head while holding the cross-process lock. A cached
    // per-process head is stale as soon as another Python/Rust process appends.
    match verify_ledger_file(path) {
        Ok((_, head)) => guard.previous_event_hash = head,
        Err(_) => return,
    }
    let base = json!({
        "at_epoch": now_epoch(),
        "kind": kind,
        "decision_id": verdict.decision_id,
        "allowed": verdict.allowed,
        "disposition": verdict.disposition,
        "rule": verdict.rule,
        "reason": verdict.reason,
        "manifest_hash": verdict.manifest_hash,
        "policy_version": verdict.policy_version,
        "previous_event_hash": guard.previous_event_hash,
        "detail": detail,
    });
    let encoded = serde_json::to_vec(&base).unwrap_or_default();
    let event_hash = sha256_bytes(&encoded);
    let mut event = base;
    event["event_hash"] = Value::String(event_hash.clone());
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        if writeln!(file, "{}", event).is_ok() {
            let _ = file.sync_data();
            guard.previous_event_hash = event_hash;
        }
    }
}

struct TrainingLedgerLock {
    path: PathBuf,
}

impl Drop for TrainingLedgerLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn acquire_training_ledger_lock() -> Result<TrainingLedgerLock, String> {
    let path = PathBuf::from(LEDGER_LOCK_PATH);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    for attempt in 0..500 {
        match OpenOptions::new().create_new(true).write(true).open(&path) {
            Ok(mut handle) => {
                writeln!(handle, "pid={} at={}", std::process::id(), now_epoch())
                    .map_err(|error| error.to_string())?;
                handle.sync_all().map_err(|error| error.to_string())?;
                return Ok(TrainingLedgerLock { path });
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                if attempt > 0 && attempt % 100 == 0 {
                    let stale = fs::metadata(&path)
                        .and_then(|metadata| metadata.modified())
                        .ok()
                        .and_then(|modified| modified.elapsed().ok())
                        .is_some_and(|age| age > Duration::from_secs(60));
                    if stale {
                        let _ = fs::remove_file(&path);
                    }
                }
                thread::sleep(Duration::from_millis(10));
            }
            Err(error) => return Err(error.to_string()),
        }
    }
    Err("training ledger lock busy".to_string())
}

fn verify_ledger_file(path: &Path) -> Result<(usize, String), String> {
    if !path.is_file() {
        return Ok((0, String::new()));
    }
    let raw = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let mut expected_previous = String::new();
    let mut count = 0usize;
    for (index, line) in raw.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let mut value: Value = serde_json::from_str(line)
            .map_err(|error| format!("ledger line {} invalid JSON: {error}", index + 1))?;
        let event_hash = value
            .get("event_hash")
            .and_then(Value::as_str)
            .ok_or_else(|| format!("ledger line {} missing event_hash", index + 1))?
            .to_string();
        let previous = value
            .get("previous_event_hash")
            .and_then(Value::as_str)
            .ok_or_else(|| format!("ledger line {} missing previous_event_hash", index + 1))?;
        if previous != expected_previous {
            return Err(format!("ledger chain break at line {}", index + 1));
        }
        value
            .as_object_mut()
            .ok_or_else(|| format!("ledger line {} is not object", index + 1))?
            .remove("event_hash");
        let computed = sha256_bytes(
            &serde_json::to_vec(&value)
                .map_err(|error| format!("ledger line {} encode: {error}", index + 1))?,
        );
        if computed != event_hash {
            return Err(format!("ledger hash mismatch at line {}", index + 1));
        }
        expected_previous = event_hash;
        count += 1;
    }
    Ok((count, expected_previous))
}

pub fn verify_ledger() -> LedgerStatus {
    match verify_ledger_file(Path::new(LEDGER_PATH)) {
        Ok((events, head)) => LedgerStatus {
            ok: true,
            events,
            head,
            error: None,
            policy_version: env!("CARGO_PKG_VERSION").to_string(),
        },
        Err(error) => LedgerStatus {
            ok: false,
            events: 0,
            head: String::new(),
            error: Some(error),
            policy_version: env!("CARGO_PKG_VERSION").to_string(),
        },
    }
}

fn is_reparse(path: &Path) -> Result<bool, String> {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
        let metadata = fs::symlink_metadata(path).map_err(|error| error.to_string())?;
        Ok(metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0)
    }
    #[cfg(not(windows))]
    {
        Ok(fs::symlink_metadata(path)
            .map_err(|error| error.to_string())?
            .file_type()
            .is_symlink())
    }
}

fn inspect_staging(root: &Path, max_bytes: u64, lora_rank: u64) -> Result<Vec<Value>, String> {
    if !root.is_dir() || is_reparse(root)? {
        return Err("staging root missing or reparse point".to_string());
    }
    let canonical_root = root.canonicalize().map_err(|error| error.to_string())?;
    let mut stack = vec![root.to_path_buf()];
    let mut total = 0u64;
    let mut inventory = Vec::new();
    while let Some(directory) = stack.pop() {
        for entry in fs::read_dir(&directory).map_err(|error| error.to_string())? {
            let entry = entry.map_err(|error| error.to_string())?;
            let path = entry.path();
            if is_reparse(&path)? {
                return Err(format!("reparse point denied: {}", path.display()));
            }
            let canonical = path.canonicalize().map_err(|error| error.to_string())?;
            if !canonical.starts_with(&canonical_root) {
                return Err(format!("path escaped staging root: {}", path.display()));
            }
            let metadata = entry.metadata().map_err(|error| error.to_string())?;
            if metadata.is_dir() {
                stack.push(path);
                continue;
            }
            if !metadata.is_file() {
                return Err(format!("non-regular file denied: {}", path.display()));
            }
            if hard_link_count(&path)? != 1 {
                return Err(format!("hard-linked file denied: {}", path.display()));
            }
            let extension = path
                .extension()
                .and_then(|value| value.to_str())
                .unwrap_or("")
                .to_ascii_lowercase();
            if !matches!(
                extension.as_str(),
                "json" | "jsonl" | "md" | "log" | "safetensors"
            ) {
                return Err(format!("extension denied at commit: {}", path.display()));
            }
            total = total.saturating_add(metadata.len());
            if total > max_bytes {
                return Err("staging size exceeds lease".to_string());
            }
            let sha = hash_file(&path)?;
            if extension == "json" {
                let raw = fs::read_to_string(&path).map_err(|error| error.to_string())?;
                serde_json::from_str::<Value>(&raw)
                    .map_err(|error| format!("invalid JSON {}: {error}", path.display()))?;
            } else if extension == "jsonl" {
                let raw = fs::read_to_string(&path).map_err(|error| error.to_string())?;
                for (index, line) in raw.lines().enumerate() {
                    if !line.trim().is_empty() {
                        serde_json::from_str::<Value>(line).map_err(|error| {
                            format!(
                                "invalid JSONL {} line {}: {error}",
                                path.display(),
                                index + 1
                            )
                        })?;
                    }
                }
            } else if extension == "safetensors" {
                inspect_safetensors(&path, lora_rank)?;
            }
            inventory.push(json!({
                "path": canonical.strip_prefix(&canonical_root).unwrap_or(&canonical).to_string_lossy().replace('\\', "/"),
                "bytes": metadata.len(),
                "sha256": sha,
            }));
        }
    }
    if inventory.is_empty() {
        return Err("empty staging run".to_string());
    }
    inventory.sort_by(|left, right| {
        left.get("path")
            .and_then(Value::as_str)
            .cmp(&right.get("path").and_then(Value::as_str))
    });
    Ok(inventory)
}

#[cfg(windows)]
fn hard_link_count(path: &Path) -> Result<u32, String> {
    use std::os::windows::ffi::OsStrExt;
    let wide: Vec<u16> = path
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();
    let handle = unsafe {
        CreateFileW(
            wide.as_ptr(),
            FILE_READ_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            std::ptr::null(),
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
            0,
        )
    };
    if handle == INVALID_HANDLE_VALUE {
        return Err(format!("failed to open file identity: {}", path.display()));
    }
    let mut information: BY_HANDLE_FILE_INFORMATION = unsafe { std::mem::zeroed() };
    let ok = unsafe { GetFileInformationByHandle(handle, &mut information) };
    unsafe { CloseHandle(handle) };
    if ok == 0 {
        return Err(format!("failed to read file identity: {}", path.display()));
    }
    Ok(information.nNumberOfLinks)
}

#[cfg(not(windows))]
fn hard_link_count(_path: &Path) -> Result<u32, String> {
    Ok(1)
}

fn hash_file(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|error| error.to_string())?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    Ok(hex_encode(hasher.finalize()))
}

fn inspect_safetensors(path: &Path, lora_rank: u64) -> Result<(), String> {
    let mut file = File::open(path).map_err(|error| error.to_string())?;
    let length = file.metadata().map_err(|error| error.to_string())?.len();
    if length < 10 {
        return Err("safetensors file too small".to_string());
    }
    let mut header_len_bytes = [0u8; 8];
    file.read_exact(&mut header_len_bytes)
        .map_err(|error| error.to_string())?;
    let header_len = u64::from_le_bytes(header_len_bytes);
    if header_len == 0 || header_len > 16 * 1024 * 1024 || header_len + 8 > length {
        return Err("safetensors header length invalid".to_string());
    }
    let mut header = vec![0u8; header_len as usize];
    file.read_exact(&mut header)
        .map_err(|error| error.to_string())?;
    let value: Value = serde_json::from_slice(&header)
        .map_err(|error| format!("safetensors header JSON invalid: {error}"))?;
    let object = value
        .as_object()
        .ok_or("safetensors header is not an object")?;
    let data_len = length - header_len - 8;
    let mut tensor_count = 0usize;
    for (name, descriptor) in object {
        if name == "__metadata__" {
            continue;
        }
        tensor_count += 1;
        if tensor_count > 4096 || !name.contains("lora_") {
            return Err(format!("unexpected adapter tensor: {name}"));
        }
        let dtype = descriptor
            .get("dtype")
            .and_then(Value::as_str)
            .ok_or("tensor dtype missing")?;
        let width = match dtype {
            "F32" => 4u64,
            "F16" | "BF16" => 2u64,
            _ => return Err(format!("adapter dtype denied: {dtype}")),
        };
        let shape = descriptor
            .get("shape")
            .and_then(Value::as_array)
            .ok_or("tensor shape missing")?;
        if shape.len() != 2 {
            return Err(format!("adapter tensor rank is not 2D: {name}"));
        }
        if lora_rank == 0
            || !shape
                .iter()
                .filter_map(Value::as_u64)
                .any(|dimension| dimension == lora_rank)
        {
            return Err(format!("LoRA rank mismatch for {name}"));
        }
        let elements = shape.iter().try_fold(1u64, |total, dim| {
            dim.as_u64()
                .and_then(|value| total.checked_mul(value))
                .ok_or_else(|| "tensor shape overflow".to_string())
        })?;
        let offsets = descriptor
            .get("data_offsets")
            .and_then(Value::as_array)
            .ok_or("tensor offsets missing")?;
        if offsets.len() != 2 {
            return Err("tensor offsets malformed".to_string());
        }
        let start = offsets[0].as_u64().ok_or("tensor start missing")?;
        let end = offsets[1].as_u64().ok_or("tensor end missing")?;
        if start > end || end > data_len || end - start != elements.saturating_mul(width) {
            return Err(format!("tensor bounds invalid: {name}"));
        }
        inspect_tensor_finite(&mut file, header_len + 8 + start, end - start, dtype, name)?;
    }
    if tensor_count == 0 {
        return Err("adapter contains no tensors".to_string());
    }
    Ok(())
}

fn inspect_tensor_finite(
    file: &mut File,
    absolute_offset: u64,
    length: u64,
    dtype: &str,
    name: &str,
) -> Result<(), String> {
    file.seek(SeekFrom::Start(absolute_offset))
        .map_err(|error| error.to_string())?;
    let width = if dtype == "F32" { 4usize } else { 2usize };
    let mut remaining = length;
    let mut buffer = vec![0u8; 1024 * 1024];
    while remaining > 0 {
        let count = (remaining as usize).min(buffer.len());
        file.read_exact(&mut buffer[..count])
            .map_err(|error| error.to_string())?;
        if count % width != 0 {
            return Err(format!("unaligned tensor data: {name}"));
        }
        for chunk in buffer[..count].chunks_exact(width) {
            let nonfinite = if dtype == "F32" {
                let bits = u32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
                bits & 0x7f80_0000 == 0x7f80_0000
            } else if dtype == "F16" {
                let bits = u16::from_le_bytes([chunk[0], chunk[1]]);
                bits & 0x7c00 == 0x7c00
            } else {
                let bits = u16::from_le_bytes([chunk[0], chunk[1]]);
                bits & 0x7f80 == 0x7f80
            };
            if nonfinite {
                return Err(format!("non-finite tensor value denied: {name}"));
            }
        }
        remaining -= count as u64;
    }
    Ok(())
}

fn dpapi_protect(plaintext: &[u8], entropy: &[u8]) -> Result<Vec<u8>, String> {
    let input = CRYPT_INTEGER_BLOB {
        cbData: plaintext.len() as u32,
        pbData: plaintext.as_ptr() as *mut u8,
    };
    let entropy_blob = CRYPT_INTEGER_BLOB {
        cbData: entropy.len() as u32,
        pbData: entropy.as_ptr() as *mut u8,
    };
    let mut output = CRYPT_INTEGER_BLOB {
        cbData: 0,
        pbData: std::ptr::null_mut(),
    };
    let ok = unsafe {
        CryptProtectData(
            &input,
            std::ptr::null(),
            &entropy_blob,
            std::ptr::null(),
            std::ptr::null(),
            CRYPTPROTECT_UI_FORBIDDEN,
            &mut output,
        )
    };
    if ok == 0 || output.pbData.is_null() {
        return Err("CryptProtectData failed".to_string());
    }
    let data =
        unsafe { std::slice::from_raw_parts(output.pbData, output.cbData as usize).to_vec() };
    unsafe { LocalFree(output.pbData as *mut core::ffi::c_void) };
    Ok(data)
}

fn dpapi_unprotect(ciphertext: &[u8], entropy: &[u8]) -> Result<Vec<u8>, String> {
    let input = CRYPT_INTEGER_BLOB {
        cbData: ciphertext.len() as u32,
        pbData: ciphertext.as_ptr() as *mut u8,
    };
    let entropy_blob = CRYPT_INTEGER_BLOB {
        cbData: entropy.len() as u32,
        pbData: entropy.as_ptr() as *mut u8,
    };
    let mut output = CRYPT_INTEGER_BLOB {
        cbData: 0,
        pbData: std::ptr::null_mut(),
    };
    let ok = unsafe {
        CryptUnprotectData(
            &input,
            std::ptr::null_mut(),
            &entropy_blob,
            std::ptr::null(),
            std::ptr::null(),
            CRYPTPROTECT_UI_FORBIDDEN,
            &mut output,
        )
    };
    if ok == 0 || output.pbData.is_null() {
        return Err("CryptUnprotectData failed".to_string());
    }
    let data =
        unsafe { std::slice::from_raw_parts(output.pbData, output.cbData as usize).to_vec() };
    unsafe { LocalFree(output.pbData as *mut core::ffi::c_void) };
    Ok(data)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_directory(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "viv-training-security-{}-{}",
            label,
            std::process::id()
        ))
    }

    fn write_test_adapter(path: &Path, nonfinite: bool) {
        let header = json!({
            "base_model.model.layers.0.self_attn.q_proj.lora_A.weight": {
                "dtype": "F32",
                "shape": [16, 1],
                "data_offsets": [0, 64]
            }
        })
        .to_string();
        let mut file = File::create(path).expect("create adapter");
        file.write_all(&(header.len() as u64).to_le_bytes())
            .expect("write header length");
        file.write_all(header.as_bytes()).expect("write header");
        let mut data = vec![0u8; 64];
        if nonfinite {
            data[..4].copy_from_slice(&f32::NAN.to_bits().to_le_bytes());
        }
        file.write_all(&data).expect("write tensor");
        file.sync_all().expect("sync adapter");
    }

    fn request(action: TrainingAction) -> TrainingSecurityRequest {
        TrainingSecurityRequest {
            action,
            stage_id: "evidence_truth".to_string(),
            run_id: "security-test-run".to_string(),
            model_role: "openaster_target".to_string(),
            manifest_hash: "a".repeat(64),
            source_hashes: vec!["b".repeat(64)],
            paths: vec![
                "L:/Continue/Viv/sandbox/training_staging/security-test-run".to_string(),
                "L:/Continue/Viv/foundation/models/Training/runs/security-test-run".to_string(),
            ],
            artifact_class: "lora_adapter".to_string(),
            master_s_n: 0.55,
            process_id: std::process::id(),
            max_duration_s: 60,
            max_vram_mib: 8192,
            max_ram_mib: 28672,
            max_disk_mib: 512,
            sequence_cap: 384,
            lora_rank: 16,
        }
    }

    #[test]
    fn valid_begin_request_passes_pure_contract() {
        let result = validate_request(&request(TrainingAction::BeginRun));
        assert!(result.is_ok(), "{result:?}");
    }

    #[test]
    fn training_soft_band_allows_bounded_begin_and_commit() {
        for action in [TrainingAction::BeginRun, TrainingAction::CommitRun] {
            let mut value = request(action);
            value.master_s_n = 0.3229;
            assert!(validate_request(&value).is_ok(), "{value:?}");
        }
    }

    #[test]
    fn non_training_actions_keep_hard_law5_gate() {
        let mut value = request(TrainingAction::Evaluate);
        value.artifact_class = "training_evidence".to_string();
        value.model_role = "deterministic_authority".to_string();
        value.master_s_n = 0.3229;
        assert!(matches!(
            validate_request(&value),
            Err(("law5_stability", _))
        ));
    }

    #[test]
    fn training_soft_floor_still_fails_closed() {
        let mut value = request(TrainingAction::BeginRun);
        value.master_s_n = TRAINING_SOFT_FLOOR - 0.0001;
        assert!(matches!(
            validate_request(&value),
            Err(("law5_stability", _))
        ));
    }

    #[test]
    fn deployment_is_compiled_closed() {
        let result = validate_request(&request(TrainingAction::Deploy));
        assert!(matches!(result, Err(("training_deploy_disabled", _))));
    }

    #[test]
    fn low_stability_fails_closed() {
        let mut value = request(TrainingAction::BeginRun);
        value.master_s_n = 0.1;
        let result = validate_request(&value);
        assert!(matches!(result, Err(("law5_stability", _))));
    }

    #[test]
    fn path_escape_and_rank_widen_are_denied() {
        let mut escaped = request(TrainingAction::BeginRun);
        escaped.paths = vec!["L:/Continue/Viv/sandbox/../security_core/Cargo.toml".to_string()];
        assert!(matches!(
            validate_request(&escaped),
            Err(("path_contract", _))
        ));
        let mut widened = request(TrainingAction::BeginRun);
        widened.lora_rank = 32;
        assert!(matches!(
            validate_request(&widened),
            Err(("resource_ceiling", _))
        ));
    }

    #[test]
    fn typed_capabilities_protect_ledger_extensions_and_freeze_path() {
        let mut evidence = request(TrainingAction::Evaluate);
        evidence.model_role = "artifact_controller".to_string();
        evidence.artifact_class = "training_evidence".to_string();
        evidence.paths = vec![LEDGER_PATH.to_string()];
        assert!(matches!(
            validate_request(&evidence),
            Err(("ledger_protected", _))
        ));
        evidence.paths =
            vec!["L:/Continue/Viv/foundation/artifacts/auto/training_payload.py".to_string()];
        assert!(matches!(
            validate_request(&evidence),
            Err(("artifact_extension", _))
        ));

        let mut freeze = request(TrainingAction::Freeze);
        freeze.model_role = "deterministic_authority".to_string();
        freeze.artifact_class = "training_evidence".to_string();
        freeze.paths = vec![STAGE1_REGISTRY_PATH.to_string()];
        assert!(validate_request(&freeze).is_ok());
        freeze.model_role = "openaster_target".to_string();
        assert!(matches!(
            validate_request(&freeze),
            Err(("capability_matrix", _))
        ));
    }

    #[test]
    fn registry_freeze_targets_are_exact_and_stage_bound() {
        let old = resolve_freeze_target(&[normalize_path(STAGE1_REGISTRY_PATH)], "evidence_truth")
            .expect("legacy stage1 registry remains allowlisted");
        assert_eq!(old.corpus_path, STAGE1_CORPUS_PATH);

        let mouth = resolve_freeze_target(
            &[normalize_path(MOUTH_IDENTITY_REGISTRY_PATH)],
            "mouth_identity",
        )
        .expect("mouth identity registry is allowlisted");
        assert_eq!(mouth.corpus_path, MOUTH_IDENTITY_CORPUS_PATH);
        assert_eq!(
            registry_for_frozen_corpus(&normalize_path(MOUTH_IDENTITY_CORPUS_PATH)),
            Some(MOUTH_IDENTITY_REGISTRY_PATH)
        );

        let mouth_v2 = resolve_freeze_target(
            &[normalize_path(MOUTH_IDENTITY_V2_REGISTRY_PATH)],
            "mouth_identity",
        )
        .expect("mouth identity v2 registry is allowlisted");
        assert_eq!(mouth_v2.corpus_path, MOUTH_IDENTITY_V2_CORPUS_PATH);

        let mouth_v2_1 = resolve_freeze_target(
            &[normalize_path(MOUTH_IDENTITY_V2_1_REGISTRY_PATH)],
            "mouth_identity",
        )
        .expect("mouth identity v2.1 registry is allowlisted");
        assert_eq!(mouth_v2_1.corpus_path, MOUTH_IDENTITY_V2_1_CORPUS_PATH);

        assert!(matches!(
            resolve_freeze_target(
                &[normalize_path(MOUTH_IDENTITY_REGISTRY_PATH)],
                "evidence_truth"
            ),
            Err(("freeze_stage", _))
        ));
        assert!(matches!(
            resolve_freeze_target(
                &["l:/continue/viv/foundation/artifacts/auto/arbitrary.json".to_string()],
                "mouth_identity"
            ),
            Err(("freeze_target", _))
        ));
        assert!(matches!(
            resolve_freeze_target(
                &[
                    normalize_path(MOUTH_IDENTITY_REGISTRY_PATH),
                    normalize_path(STAGE1_REGISTRY_PATH)
                ],
                "mouth_identity"
            ),
            Err(("freeze_target", _))
        ));
    }

    #[test]
    fn parity_mouth_role_is_evaluate_only() {
        let mut evaluate = request(TrainingAction::Evaluate);
        evaluate.model_role = "parity_mouth_eval".to_string();
        evaluate.artifact_class = "evaluation_report".to_string();
        evaluate.paths = vec![
            "L:/Continue/Viv/foundation/artifacts/auto/openaster_parity/reports/probe.json"
                .to_string(),
        ];
        assert!(validate_request(&evaluate).is_ok());

        let mut begin = request(TrainingAction::BeginRun);
        begin.model_role = "parity_mouth_eval".to_string();
        assert!(matches!(
            validate_request(&begin),
            Err(("capability_matrix", _))
        ));

        let mut promote = request(TrainingAction::Promote);
        promote.model_role = "parity_mouth_eval".to_string();
        promote.artifact_class = "candidate_pointer".to_string();
        assert!(matches!(
            validate_request(&promote),
            Err(("capability_matrix", _))
        ));
    }

    #[test]
    fn request_schema_rejects_unknown_fields() {
        let raw = format!(
            "{{\"action\":\"BEGIN_RUN\",\"stage_id\":\"evidence_truth\",\"run_id\":\"x\",\
             \"model_role\":\"openaster_target\",\"manifest_hash\":\"{}\",\"source_hashes\":[],\
             \"paths\":[],\"artifact_class\":\"lora_adapter\",\"master_s_n\":0.5,\
             \"process_id\":{},\"max_duration_s\":60,\"max_vram_mib\":1,\"max_ram_mib\":1,\
             \"max_disk_mib\":1,\"sequence_cap\":1,\"lora_rank\":1,\"bypass\":true}}",
            "a".repeat(64),
            std::process::id()
        );
        assert!(parse_request(&raw).is_err());
    }

    #[test]
    fn dpapi_round_trip_is_current_user_bound() {
        let plaintext = b"Viv training quarantine test";
        let entropy = b"manifest";
        let ciphertext = dpapi_protect(plaintext, entropy).expect("protect");
        assert_ne!(ciphertext, plaintext);
        let restored = dpapi_unprotect(&ciphertext, entropy).expect("unprotect");
        assert_eq!(restored, plaintext);
        assert!(dpapi_unprotect(&ciphertext, b"wrong-manifest").is_err());
    }

    #[test]
    fn safetensors_parser_accepts_finite_rank_and_rejects_nonfinite_or_malformed() {
        let root = test_directory("safetensors");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).expect("create test root");
        let good = root.join("good.safetensors");
        write_test_adapter(&good, false);
        assert!(inspect_safetensors(&good, 16).is_ok());

        let nonfinite = root.join("nonfinite.safetensors");
        write_test_adapter(&nonfinite, true);
        let error = inspect_safetensors(&nonfinite, 16).expect_err("nonfinite denied");
        assert!(error.contains("non-finite"), "{error}");

        let malformed = root.join("malformed.safetensors");
        fs::write(&malformed, b"not-safe").expect("write malformed");
        assert!(inspect_safetensors(&malformed, 16).is_err());
        fs::remove_dir_all(&root).expect("cleanup test root");
    }

    #[test]
    fn staging_inspection_rejects_hardlinks_and_reparse_points() {
        let root = test_directory("links");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).expect("create test root");
        let original = root.join("record.json");
        fs::write(&original, b"{}").expect("write record");
        let linked = root.join("record-linked.json");
        fs::hard_link(&original, &linked).expect("create hardlink");
        let error = inspect_staging(&root, 1024, 16).expect_err("hardlink denied");
        assert!(error.contains("hard-linked"), "{error}");
        fs::remove_file(&linked).expect("remove hardlink");

        #[cfg(windows)]
        {
            use std::os::windows::fs::symlink_file;
            let outside = test_directory("outside").with_extension("json");
            fs::write(&outside, b"{}").expect("write outside target");
            let link = root.join("reparse.json");
            if symlink_file(&outside, &link).is_ok() {
                let error = inspect_staging(&root, 1024, 16).expect_err("reparse denied");
                assert!(error.contains("reparse"), "{error}");
            }
            let _ = fs::remove_file(&link);
            fs::remove_file(&outside).expect("remove outside target");
        }
        fs::remove_dir_all(&root).expect("cleanup test root");
    }

    #[test]
    fn consumed_lease_token_cannot_be_replayed() {
        let token = "replay-test-token";
        let token_hash = sha256_bytes(token.as_bytes());
        let lease = Lease {
            token_hash: token_hash.clone(),
            binding_hash: "binding".to_string(),
            run_id: "replay-test".to_string(),
            stage_id: "tree_control".to_string(),
            manifest_hash: "a".repeat(64),
            process_id: std::process::id(),
            staging_root: PathBuf::from(STAGING_ROOT).join("replay-test"),
            final_root: PathBuf::from(RUNS_ROOT).join("replay-test"),
            expires_at: now_epoch() + 60,
            max_disk_bytes: 1024,
            lora_rank: 16,
            consumed: true,
        };
        state()
            .lock()
            .expect("state")
            .leases
            .insert(token_hash.clone(), lease);
        let error = active_lease(token).expect_err("consumed lease denied");
        assert!(error.contains("expired, consumed"));
        state().lock().expect("state").leases.remove(&token_hash);
    }
}
