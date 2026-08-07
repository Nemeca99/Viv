//! Isolated persistent U_AM composite candidate.
//!
//! Contract:
//!   substrate: U (fixed, validated structure)
//!   domains:   A then M
//!   formula:   (x + y) * z
//!
//! This library has no model, table, parser, or dynamic dispatcher. It is the
//! exact compiled macro whose creation cost is measured before promotion.

#[no_mangle]
pub extern "C" fn uml_u_am_v1(x: i64, y: i64, z: i64) -> i64 {
    (x + y) * z
}

#[no_mangle]
pub extern "C" fn uml_u_am_v1_contract() -> u64 {
    // ASCII "U_AM_V1" packed as a stable contract marker.
    0x0055_5f41_4d5f_5631
}
