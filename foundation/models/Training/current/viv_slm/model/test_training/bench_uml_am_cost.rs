//! Bounded U_AM cost benchmark.
//!
//! All three paths compute the same variable-input function:
//!     (x + y) * z
//!
//! - persistent: native compiled composite
//! - dynamic: generic opcode dispatch over A then M
//! - mono/LIT: dense pre-materialized output table
//!
//! The LIT baseline is deliberately strong: unchecked dense lookup, not a
//! hash map. Requests visit a large table in deterministic pseudo-random order
//! so the result measures the scaling cost of materializing destinations.

use std::env;
use std::hint::black_box;
use std::time::Instant;

const OP_X: u8 = 1;
const OP_Y: u8 = 2;
const OP_Z: u8 = 3;
const OP_ADD: u8 = 4;
const OP_MUL: u8 = 5;

#[derive(Clone, Copy)]
struct Request {
    index: usize,
    x: i64,
    y: i64,
    z: i64,
}

#[derive(Clone, Copy)]
struct Config {
    x_size: usize,
    y_size: usize,
    z_size: usize,
    requests: usize,
    rounds: usize,
    warmup: usize,
}

fn parse_usize(name: &str, default: usize) -> usize {
    let args: Vec<String> = env::args().collect();
    args.windows(2)
        .find(|pair| pair[0] == name)
        .and_then(|pair| pair[1].parse::<usize>().ok())
        .unwrap_or(default)
}

#[inline(always)]
fn persistent_am(req: &Request) -> i64 {
    black_box((black_box(req.x) + black_box(req.y)) * black_box(req.z))
}

#[inline(never)]
fn dynamic_am(req: &Request, program: &[u8]) -> i64 {
    let mut stack = [0_i64; 4];
    let mut sp = 0_usize;
    for op in black_box(program) {
        match *op {
            OP_X => {
                stack[sp] = black_box(req.x);
                sp += 1;
            }
            OP_Y => {
                stack[sp] = black_box(req.y);
                sp += 1;
            }
            OP_Z => {
                stack[sp] = black_box(req.z);
                sp += 1;
            }
            OP_ADD => {
                let rhs = stack[sp - 1];
                let lhs = stack[sp - 2];
                sp -= 1;
                stack[sp - 1] = lhs + rhs;
            }
            OP_MUL => {
                let rhs = stack[sp - 1];
                let lhs = stack[sp - 2];
                sp -= 1;
                stack[sp - 1] = lhs * rhs;
            }
            _ => panic!("invalid opcode"),
        }
    }
    assert_eq!(sp, 1);
    black_box(stack[0])
}

fn validate_program(program: &[u8]) {
    let mut depth: isize = 0;
    let mut seen_a = false;
    let mut seen_m = false;
    for op in program {
        match *op {
            OP_X | OP_Y | OP_Z => depth += 1,
            OP_ADD => {
                assert!(depth >= 2, "malformed ADD");
                depth -= 1;
                seen_a = true;
            }
            OP_MUL => {
                assert!(depth >= 2, "malformed MUL");
                depth -= 1;
                seen_m = true;
            }
            _ => panic!("unknown opcode"),
        }
    }
    assert_eq!(depth, 1, "program must seal one destination");
    assert!(seen_a && seen_m, "program must be U_AM");
}

#[inline(always)]
fn decode(index: usize, cfg: Config) -> Request {
    let x = index % cfg.x_size;
    let rem = index / cfg.x_size;
    let y = rem % cfg.y_size;
    let z = rem / cfg.y_size;
    Request {
        index,
        x: x as i64,
        y: y as i64,
        z: (z + 1) as i64,
    }
}

fn build_requests(cfg: Config) -> Vec<Request> {
    let domain = cfg.x_size * cfg.y_size * cfg.z_size;
    assert!(domain.is_power_of_two(), "domain must be power of two");
    let mask = domain - 1;
    let mut state: usize = 0x9e37_79b9;
    let mut requests = Vec::with_capacity(cfg.requests);
    for _ in 0..cfg.requests {
        // Full-period LCG modulo 2^k: multiplier = 1 mod 4, increment odd.
        state = state
            .wrapping_mul(6_364_136_223_846_793_005_usize)
            .wrapping_add(1_442_695_040_888_963_407_usize);
        requests.push(decode(state & mask, cfg));
    }
    requests
}

fn build_literal_table(cfg: Config, program: &[u8]) -> (Vec<i64>, u128) {
    let domain = cfg.x_size * cfg.y_size * cfg.z_size;
    let started = Instant::now();
    let mut table = Vec::with_capacity(domain);
    for index in 0..domain {
        let req = decode(index, cfg);
        table.push(dynamic_am(&req, program));
    }
    (table, started.elapsed().as_nanos())
}

fn run_persistent(requests: &[Request]) -> i64 {
    let mut checksum = 0_i64;
    for req in black_box(requests) {
        checksum = checksum.wrapping_add(persistent_am(req));
    }
    black_box(checksum)
}

fn run_dynamic(requests: &[Request], program: &[u8]) -> i64 {
    let mut checksum = 0_i64;
    for req in black_box(requests) {
        checksum = checksum.wrapping_add(dynamic_am(req, program));
    }
    black_box(checksum)
}

fn run_literal(requests: &[Request], table: &[i64]) -> i64 {
    let mut checksum = 0_i64;
    for req in black_box(requests) {
        // Dense unchecked lookup is the strongest finite LIT implementation.
        let value = unsafe { *table.get_unchecked(black_box(req.index)) };
        checksum = checksum.wrapping_add(black_box(value));
    }
    black_box(checksum)
}

fn measure<F: FnOnce() -> i64>(run: F) -> (u128, i64) {
    let started = Instant::now();
    let checksum = run();
    (started.elapsed().as_nanos(), checksum)
}

fn json_u128_array(values: &[u128]) -> String {
    values
        .iter()
        .map(|value| value.to_string())
        .collect::<Vec<_>>()
        .join(",")
}

fn main() {
    let cfg = Config {
        x_size: parse_usize("--x-size", 256),
        y_size: parse_usize("--y-size", 256),
        z_size: parse_usize("--z-size", 64),
        requests: parse_usize("--requests", 1_048_576),
        rounds: parse_usize("--rounds", 31),
        warmup: parse_usize("--warmup", 5),
    };
    assert!(cfg.requests > 0);
    assert!(cfg.rounds >= 21, "need >=21 valid samples");

    let program = vec![OP_X, OP_Y, OP_ADD, OP_Z, OP_MUL];
    validate_program(&program);
    let requests = build_requests(cfg);
    let (literal_table, literal_build_ns) = build_literal_table(cfg, &program);

    let expected_p = run_persistent(&requests);
    let expected_d = run_dynamic(&requests, &program);
    let expected_l = run_literal(&requests, &literal_table);
    assert_eq!(expected_p, expected_d, "persistent/dynamic mismatch");
    assert_eq!(expected_p, expected_l, "persistent/LIT mismatch");

    for _ in 0..cfg.warmup {
        black_box(run_persistent(&requests));
        black_box(run_dynamic(&requests, &program));
        black_box(run_literal(&requests, &literal_table));
    }

    let mut persistent_ns = Vec::with_capacity(cfg.rounds);
    let mut dynamic_ns = Vec::with_capacity(cfg.rounds);
    let mut literal_ns = Vec::with_capacity(cfg.rounds);
    let mut health_ok = true;

    // Rotate order to reduce systematic thermal/order bias.
    for round in 0..cfg.rounds {
        let mut p = (0_u128, 0_i64);
        let mut d = (0_u128, 0_i64);
        let mut l = (0_u128, 0_i64);
        match round % 3 {
            0 => {
                p = measure(|| run_persistent(&requests));
                d = measure(|| run_dynamic(&requests, &program));
                l = measure(|| run_literal(&requests, &literal_table));
            }
            1 => {
                d = measure(|| run_dynamic(&requests, &program));
                l = measure(|| run_literal(&requests, &literal_table));
                p = measure(|| run_persistent(&requests));
            }
            _ => {
                l = measure(|| run_literal(&requests, &literal_table));
                p = measure(|| run_persistent(&requests));
                d = measure(|| run_dynamic(&requests, &program));
            }
        }
        health_ok &= p.1 == expected_p && d.1 == expected_p && l.1 == expected_p;
        persistent_ns.push(p.0);
        dynamic_ns.push(d.0);
        literal_ns.push(l.0);
    }

    let domain = cfg.x_size * cfg.y_size * cfg.z_size;
    let literal_bytes = literal_table.capacity() * std::mem::size_of::<i64>();
    let request_bytes = requests.capacity() * std::mem::size_of::<Request>();

    println!(
        concat!(
            "{{",
            "\"schema_version\":\"uml_am_cost_bench_v1\",",
            "\"federation\":\"U_AM\",",
            "\"formula\":\"(x+y)*z\",",
            "\"x_size\":{},\"y_size\":{},\"z_size\":{},",
            "\"domain_entries\":{},\"requests\":{},\"rounds\":{},\"warmup\":{},",
            "\"literal_build_ns\":{},\"literal_table_bytes\":{},",
            "\"request_stream_bytes\":{},\"program_bytes\":{},",
            "\"checksum\":{},\"health_ok\":{},",
            "\"persistent_elapsed_ns\":[{}],",
            "\"dynamic_elapsed_ns\":[{}],",
            "\"literal_elapsed_ns\":[{}]",
            "}}"
        ),
        cfg.x_size,
        cfg.y_size,
        cfg.z_size,
        domain,
        cfg.requests,
        cfg.rounds,
        cfg.warmup,
        literal_build_ns,
        literal_bytes,
        request_bytes,
        program.capacity() * std::mem::size_of::<u8>(),
        expected_p,
        if health_ok { "true" } else { "false" },
        json_u128_array(&persistent_ns),
        json_u128_array(&dynamic_ns),
        json_u128_array(&literal_ns),
    );
}
