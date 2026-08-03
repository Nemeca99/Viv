fn main() {
  let t = "jai\u{200b}break";
  let mut out = String::new();
  for c in t.chars() {
    let u = c as u32;
    let inv = matches!(u, 0x200b..=0x200f);
    println!("{:?} u={:x} inv={}", c, u, inv);
  }
}
