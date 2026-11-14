// Synthetic lexical fixture; not application code.
struct Unrelated;
fn unrelated() {}
// A physical header is distinguishable from opaque/body expressions.
pub fn synthetic_header() -> usize {
    let text = r###"} fn imaginary() {"###;
    /* Nested /* comment */ with { braces } */
    opaque!({ fn not_a_source_item() {} });
    let transform = |value| value + 1;
    let byte = b'}';
    let _ = (text, byte);
    transform(1)
}
