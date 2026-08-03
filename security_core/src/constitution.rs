//! Constitution surface — primes + laws as machine-readable doctrine.

use crate::laws::{effective_dormancy_threshold, ARCHITECT, CRITICAL_S_N, LAWS, PRIMES};
use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct ConstitutionSummary {
    pub architect: String,
    pub version: String,
    pub dormancy_threshold: f64,
    pub critical_s_n: f64,
    pub primes: Vec<String>,
    pub laws: Vec<String>,
}

pub fn summary(version: &str) -> ConstitutionSummary {
    ConstitutionSummary {
        architect: ARCHITECT.to_string(),
        version: version.to_string(),
        dormancy_threshold: effective_dormancy_threshold(),
        critical_s_n: CRITICAL_S_N,
        primes: PRIMES.iter().map(|s| (*s).to_string()).collect(),
        laws: LAWS.iter().map(|s| (*s).to_string()).collect(),
    }
}
