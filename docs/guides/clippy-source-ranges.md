# Bounded source-range verification

`ops/scripts/clippy_source_ranges.py` is the shared scanner imported by the
producer and offline planner; it is not a Rust compiler or standalone CLI.
`verify_function_range` correlates explicit ranges and source/Serena witnesses
and returns verified/ambiguous/unsupported status with reasons and predicates.

Supported lexical cases include comments, ordinary/raw/byte literals, balanced
token trees and ordinary functions/methods with verified ancestors. Macro
contents remain opaque. Diagnostic units are explicit; Windows/Unicode/CRLF
cases cannot be silently rebased or normalized.

Regression boundaries retained in extraction:

- Bodyless foreign declarations and extern blocks exclude inner spans from an
  outer function, but do not invalidate an ordinary outer-header diagnostic.
- Inner attributes attach to nearest lexical scope. Selected functions and
  relevant ancestors are checked; unrelated nested scopes do not poison them.
- Parent identity is ordered and role-sensitive through the full chain.
  Reversed trait/self impls, wrong module names and invented root parents fail.
- Only the fully parsed non-rewriting lint-attribute subset in the
  [IO contract](../contracts/io.md#physical-localization-and-scanner-limits)
  is accepted. This never approves suppression or corrective edits.

Nested items, required closure/async identity, cfg/generated contexts and
unsupported syntax remain unresolved rather than guessed. Physical verification
does not prove references, dispatch safety or complete feature/macro coverage.
The public mixed-source fixture is invented; it contains no application body.

```powershell
python -B -m unittest discover -s ops/tests -p test_clippy_source_ranges.py
```
