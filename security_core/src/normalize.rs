//! Text and path normalization — defeat homoglyph, ZWSP, traversal, and smuggling.

use serde_json::Value;

fn is_invisible(c: char) -> bool {
    let u = c as u32;
    if (0x200b..=0x200f).contains(&u) {
        return true;
    }
    if (0x202a..=0x202e).contains(&u) {
        return true;
    }
    if (0x2060..=0x2064).contains(&u) || (0x2066..=0x206f).contains(&u) {
        return true;
    }
    if (0xfff9..=0xfffb).contains(&u) {
        return true;
    }
    matches!(u, 0x00ad | 0x034f | 0x061c | 0x180e | 0xfeff)
}

/// Cyrillic / lookalike → ASCII for Prime-2 needle matching.
fn map_homoglyph(c: char) -> char {
    match c {
        'а' | 'А' => 'a',
        'е' | 'Е' => 'e',
        'о' | 'О' => 'o',
        'р' | 'Р' => 'p',
        'с' | 'С' => 'c',
        'у' | 'У' => 'y',
        'х' | 'Х' => 'x',
        'і' | 'І' => 'i',
        'ї' | 'Ї' => 'i',
        'ј' | 'Ј' => 'j',
        'ѕ' | 'Ѕ' => 's',
        'ԁ' => 'd',
        'ɡ' => 'g',
        'һ' => 'h',
        'ḳ' => 'k',
        'ṃ' => 'm',
        'ṇ' => 'n',
        'ο' | 'Ο' => 'o',
        'ρ' => 'p',
        'ς' | 'σ' => 's',
        'τ' => 't',
        'υ' => 'y',
        'χ' => 'x',
        _ => c,
    }
}

/// Fold text for jailbreak / law-needle detection.
pub fn normalize_probe_text(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        if is_invisible(c) {
            continue;
        }
        let m = map_homoglyph(c);
        out.push(m.to_ascii_lowercase());
    }
    let mut collapsed = String::with_capacity(out.len());
    let mut prev_space = false;
    for c in out.chars() {
        if c.is_whitespace() {
            if !prev_space {
                collapsed.push(' ');
                prev_space = true;
            }
        } else {
            collapsed.push(c);
            prev_space = false;
        }
    }
    collapsed.trim().to_string()
}

/// Normalize a filesystem path for containment checks.
pub fn normalize_path(raw: &str) -> String {
    let mut s = raw.trim().to_lowercase().replace('\\', "/");
    // strip file:// and long-path / UNC prefixes
    for prefix in ["file:///", "file://", "//?/", "//./", "//"] {
        if s.starts_with(prefix) {
            s = s[prefix.len()..].to_string();
        }
    }
    // collapse duplicate slashes
    while s.contains("//") {
        s = s.replace("//", "/");
    }
    s
}

/// True if path uses traversal or unc/smb escape patterns.
pub fn path_has_traversal(raw: &str) -> bool {
    let n = normalize_path(raw);
    let upper = raw.to_uppercase();
    n.contains("/../")
        || n.contains("/..")
        || n.starts_with("../")
        || n.ends_with("/..")
        || n.contains("/./")
        || upper.contains("%2E%2E")
        || upper.contains("..%2F")
        || upper.contains("%2E%2E%2F")
        || n.contains("\\\\")
        || n.starts_with("//")
        || n.contains("/$") // ADS / stream oddities on some APIs
}

/// True for `X:/` / `X:\` style Windows drive roots (not ISO-8601 timestamps).
pub fn looks_like_windows_drive_path(raw: &str) -> bool {
    let low = normalize_path(raw);
    let b = low.as_bytes();
    if b.len() >= 2 && b[1] == b':' && b[0].is_ascii_alphabetic() {
        // Drive letter must be followed by slash or end (X: alone / X:/...)
        return b.len() == 2 || b[2] == b'/' || b[2] == b'\\';
    }
    false
}

/// True for strings that look like filesystem paths (not prose/JSON bodies).
pub fn looks_like_path_string(raw: &str) -> bool {
    let low = normalize_path(raw.trim());
    if low.is_empty() {
        return false;
    }
    // JSON / multi-line bodies are not paths; nested extract handles smuggled JSON.
    if low.starts_with('{') || low.starts_with('[') || low.contains('\n') {
        return false;
    }
    if looks_like_windows_drive_path(&low) {
        return true;
    }
    if low.starts_with('/') || low.starts_with('\\') {
        return true;
    }
    if low.contains("..") && (low.contains('/') || low.contains('\\')) {
        return true;
    }
    // Compact relative or absolute path with separator, not a long paragraph.
    if (low.contains('/') || low.contains('\\')) && low.len() <= 320 {
        return true;
    }
    low.ends_with(".py")
        || low.ends_with(".json")
        || low.ends_with(".pyd")
        || low.ends_with(".dll")
        || low.ends_with(".rs")
        || low.ends_with(".exe")
}

/// Recursively collect string values that look like paths from nested JSON.
pub fn extract_pathlike_strings(value: &Value, out: &mut Vec<String>) {
    match value {
        Value::String(s) => {
            if looks_like_path_string(s) {
                out.push(s.clone());
            }
            // Nested JSON string payloads (path smuggling)
            if (s.starts_with('{') && s.ends_with('}')) || (s.starts_with('[') && s.ends_with(']')) {
                if let Ok(inner) = serde_json::from_str::<Value>(s) {
                    extract_pathlike_strings(&inner, out);
                }
            }
        }
        Value::Array(arr) => {
            for v in arr {
                extract_pathlike_strings(v, out);
            }
        }
        Value::Object(map) => {
            for (k, v) in map {
                let kl = k.to_lowercase();
                if kl.contains("path")
                    || kl == "file"
                    || kl == "file_path"
                    || kl == "target"
                    || kl == "dest"
                    || kl == "destination"
                    || kl == "cwd"
                    || kl == "dir"
                {
                    if let Some(s) = v.as_str() {
                        out.push(s.to_string());
                    }
                }
                extract_pathlike_strings(v, out);
            }
        }
        _ => {}
    }
}

/// Dangerous code constructs (Law 4 IntentScanner — keyword depth).
pub fn dangerous_code_hits(code: &str) -> Vec<&'static str> {
    let n = normalize_probe_text(code);
    let needles = [
        "os.system",
        "subprocess",
        "eval(",
        "exec(",
        "__import__",
        "importlib",
        "ctypes",
        "winreg",
        "socket.",
        "urllib",
        "requests.",
        "shutil.rmtree",
        "pathlib.path",
        "open(",
        "getattr(",
        "setattr(",
        "globals(",
        "locals(",
        "compile(",
        "breakpoint(",
        "pty.",
        "multiprocessing",
        "base64.b64decode",
        "c:/",
        "d:/windows",
        "powershell",
        "cmd.exe",
        "rm -rf",
        "format c:",
    ];
    needles.into_iter().filter(|d| n.contains(d)).collect()
}
