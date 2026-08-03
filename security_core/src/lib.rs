//! Viv Canonical Alpha — `security_core` Rust layer.
//!
//! Bidirectional IN/OUT gate wrapping the three Python foundation mains.
//! Python (`foundation/`) orchestrates; Rust enforces 3 Primes + 8 Laws.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde_json::Value;

pub mod constitution;
pub mod backup_security;
pub mod gate;
pub mod governor;
pub mod laws;
pub mod normalize;
pub mod training_security;

#[cfg(test)]
mod normalize_tests {
    use super::normalize::normalize_probe_text;

    #[test]
    fn strips_zwsp_jailbreak() {
        let t = "jail\u{200b}break the system";
        let n = normalize_probe_text(t);
        assert!(
            n.contains("jailbreak"),
            "normalized={n:?} raw_codes={:?}",
            t.chars().map(|c| format!("{:x}", c as u32)).collect::<Vec<_>>()
        );
    }
}

use gate::{check_gate, GateDirection, GateVerdict};
use governor::{enforce_laws_with_raw, LawEnforcementResult};

const VERSION: &str = env!("CARGO_PKG_VERSION");

fn verdict_to_py(py: Python<'_>, verdict: &GateVerdict) -> PyResult<PyObject> {
    let dict = PyDict::new_bound(py);
    dict.set_item("allowed", verdict.allowed)?;
    dict.set_item("direction", &verdict.direction)?;
    dict.set_item("stage", &verdict.stage)?;
    dict.set_item("reason", &verdict.reason)?;
    dict.set_item("s_n", verdict.s_n)?;
    dict.set_item("version", VERSION)?;
    Ok(dict.into())
}

fn law_result_to_py(py: Python<'_>, result: &LawEnforcementResult) -> PyResult<PyObject> {
    let dict = PyDict::new_bound(py);
    dict.set_item("allowed", result.allowed)?;
    dict.set_item("reason", &result.reason)?;
    dict.set_item("law", &result.law)?;
    dict.set_item("tariff_demand", result.tariff_demand)?;
    dict.set_item("version", VERSION)?;
    Ok(dict.into())
}

#[pyfunction]
fn check_ingress(text: String, s_n: f64) -> PyResult<PyObject> {
    let verdict = check_gate(GateDirection::Ingress, &text, s_n);
    Python::with_gil(|py| verdict_to_py(py, &verdict))
}

#[pyfunction]
fn check_egress(text: String, s_n: f64) -> PyResult<PyObject> {
    let verdict = check_gate(GateDirection::Egress, &text, s_n);
    Python::with_gil(|py| verdict_to_py(py, &verdict))
}

#[pyfunction]
#[pyo3(signature = (tool_name, params_json, s_n, forensic_buffer, raw_input=None))]
fn enforce_morality(
    tool_name: String,
    params_json: String,
    s_n: f64,
    forensic_buffer: String,
    raw_input: Option<String>,
) -> PyResult<PyObject> {
    let params: Value = serde_json::from_str(&params_json)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    let raw = raw_input.unwrap_or_default();
    let result = enforce_laws_with_raw(&tool_name, params, s_n, &forensic_buffer, &raw);
    Python::with_gil(|py| law_result_to_py(py, &result))
}

#[pyfunction]
fn dormancy_threshold() -> f64 {
    laws::effective_dormancy_threshold()
}

/// Architect-static growth ceiling veto.
/// `proposed_r` / `max_r` are LoRA ranks (or analogous capacity units).
#[pyfunction]
fn check_growth(actuator: String, proposed_r: f64, max_r: f64) -> PyResult<PyObject> {
    let allowed_actuators = ["lora_widen"];
    let mut allowed = true;
    let mut reason = "OK".to_string();

    if !allowed_actuators.iter().any(|a| *a == actuator.as_str()) {
        allowed = false;
        reason = format!("actuator_not_allowlisted:{actuator}");
    } else if proposed_r > max_r {
        allowed = false;
        reason = format!("max_capacity_ceiling:proposed={proposed_r} max={max_r}");
    } else if proposed_r < 1.0 {
        allowed = false;
        reason = "proposed_r_invalid".to_string();
    }

    Python::with_gil(|py| {
        let dict = PyDict::new_bound(py);
        dict.set_item("allowed", allowed)?;
        dict.set_item("reason", reason)?;
        dict.set_item("actuator", actuator)?;
        dict.set_item("proposed_r", proposed_r)?;
        dict.set_item("max_r", max_r)?;
        dict.set_item("version", VERSION)?;
        dict.set_item("gate", "rust")?;
        Ok(dict.into())
    })
}

fn training_verdict_to_py(
    py: Python<'_>,
    verdict: &training_security::TrainingSecurityVerdict,
) -> PyResult<PyObject> {
    let encoded = serde_json::to_string(verdict)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    let json = py.import_bound("json")?;
    Ok(json.call_method1("loads", (encoded,))?.into())
}

fn backup_verdict_to_py(
    py: Python<'_>,
    verdict: &backup_security::BackupSecurityVerdict,
) -> PyResult<PyObject> {
    let encoded = serde_json::to_string(verdict)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    let json = py.import_bound("json")?;
    Ok(json.call_method1("loads", (encoded,))?.into())
}

#[pyfunction]
fn authorize_backup(request_json: String) -> PyResult<PyObject> {
    let verdict = backup_security::authorize(&request_json);
    Python::with_gil(|py| backup_verdict_to_py(py, &verdict))
}

#[pyfunction]
fn verify_backup_ledger() -> PyResult<String> {
    serde_json::to_string(&backup_security::verify_ledger())
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))
}

#[pyfunction]
fn authorize_training(request_json: String) -> PyResult<PyObject> {
    let verdict = training_security::authorize(&request_json);
    Python::with_gil(|py| training_verdict_to_py(py, &verdict))
}

#[pyfunction]
fn begin_training_lease(request_json: String) -> PyResult<PyObject> {
    let verdict = training_security::begin_lease(&request_json);
    Python::with_gil(|py| training_verdict_to_py(py, &verdict))
}

#[pyfunction]
fn commit_training_lease(token: String, request_json: String) -> PyResult<PyObject> {
    let verdict = training_security::commit_lease(&token, &request_json);
    Python::with_gil(|py| training_verdict_to_py(py, &verdict))
}

#[pyfunction]
fn freeze_training_registry(request_json: String, payload: String) -> PyResult<PyObject> {
    let verdict = training_security::freeze_registry(&request_json, &payload);
    Python::with_gil(|py| training_verdict_to_py(py, &verdict))
}

#[pyfunction]
fn quarantine_training_payload(
    token: String,
    record_id: String,
    plaintext: String,
) -> PyResult<PyObject> {
    let verdict = training_security::quarantine(&token, &record_id, &plaintext);
    Python::with_gil(|py| training_verdict_to_py(py, &verdict))
}

#[pyfunction]
fn read_training_quarantine(token: String, record_id: String) -> PyResult<PyObject> {
    let verdict = training_security::read_quarantine(&token, &record_id);
    Python::with_gil(|py| training_verdict_to_py(py, &verdict))
}

#[pyfunction]
fn verify_training_ledger() -> PyResult<String> {
    serde_json::to_string(&training_security::verify_ledger())
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))
}

#[pyfunction]
fn get_constitution() -> PyResult<PyObject> {
    let summary = constitution::summary(VERSION);
    let json = serde_json::to_string(&summary)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    let value: Value = serde_json::from_str(&json)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    Python::with_gil(|py| {
        let dict = PyDict::new_bound(py);
        dict.set_item("architect", value["architect"].as_str().unwrap_or(""))?;
        dict.set_item("version", value["version"].as_str().unwrap_or(VERSION))?;
        dict.set_item("dormancy_threshold", value["dormancy_threshold"].as_f64().unwrap_or(0.45))?;
        dict.set_item("critical_s_n", value["critical_s_n"].as_f64().unwrap_or(0.15))?;
        let primes = pyo3::types::PyList::empty_bound(py);
        if let Some(arr) = value["primes"].as_array() {
            for p in arr {
                primes.append(p.as_str().unwrap_or(""))?;
            }
        }
        dict.set_item("primes", primes)?;
        let law_list = pyo3::types::PyList::empty_bound(py);
        if let Some(arr) = value["laws"].as_array() {
            for p in arr {
                law_list.append(p.as_str().unwrap_or(""))?;
            }
        }
        dict.set_item("laws", law_list)?;
        Ok(dict.into())
    })
}

#[pymodule]
fn security_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(check_ingress, m)?)?;
    m.add_function(wrap_pyfunction!(check_egress, m)?)?;
    m.add_function(wrap_pyfunction!(enforce_morality, m)?)?;
    m.add_function(wrap_pyfunction!(dormancy_threshold, m)?)?;
    m.add_function(wrap_pyfunction!(check_growth, m)?)?;
    m.add_function(wrap_pyfunction!(authorize_backup, m)?)?;
    m.add_function(wrap_pyfunction!(verify_backup_ledger, m)?)?;
    m.add_function(wrap_pyfunction!(authorize_training, m)?)?;
    m.add_function(wrap_pyfunction!(begin_training_lease, m)?)?;
    m.add_function(wrap_pyfunction!(commit_training_lease, m)?)?;
    m.add_function(wrap_pyfunction!(freeze_training_registry, m)?)?;
    m.add_function(wrap_pyfunction!(quarantine_training_payload, m)?)?;
    m.add_function(wrap_pyfunction!(read_training_quarantine, m)?)?;
    m.add_function(wrap_pyfunction!(verify_training_ledger, m)?)?;
    m.add_function(wrap_pyfunction!(get_constitution, m)?)?;
    m.add("__version__", VERSION)?;
    Ok(())
}
