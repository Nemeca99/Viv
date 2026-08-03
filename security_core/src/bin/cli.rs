//! Native CLI for security_core (no Python required).

use security_core::gate::{check_gate, GateDirection};
use std::env;

fn print_usage() {
    eprintln!("usage: security_core_cli check-in <text> [--s-n 0.5]");
    eprintln!("       security_core_cli check-out <text> [--s-n 0.5]");
}

fn main() {
    let mut args = env::args().skip(1);
    let Some(cmd) = args.next() else {
        print_usage();
        std::process::exit(2);
    };
    if matches!(cmd.as_str(), "-h" | "--help" | "help") {
        print_usage();
        std::process::exit(0);
    }
    let text = args.next().unwrap_or_default();
    let mut s_n = 1.0_f64;
    let parts: Vec<String> = args.collect();
    let mut i = 0;
    while i < parts.len() {
        if parts[i] == "--s-n" {
            if let Some(v) = parts.get(i + 1) {
                s_n = v.parse().unwrap_or(1.0);
            }
            i += 2;
        } else {
            i += 1;
        }
    }

    let direction = match cmd.as_str() {
        "check-in" | "in" => GateDirection::Ingress,
        "check-out" | "out" => GateDirection::Egress,
        _ => {
            eprintln!("unknown command: {cmd}");
            print_usage();
            std::process::exit(2);
        }
    };

    let verdict = check_gate(direction, &text, s_n);
    println!("{}", serde_json::to_string_pretty(&verdict).unwrap_or_default());
    std::process::exit(if verdict.allowed { 0 } else { 1 });
}
