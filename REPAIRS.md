# Correctness repairs and security scope

This branch repairs several concrete implementation defects found during a
source audit.  The repairs make the prototype a better basis for experiments;
they do **not** turn it into a cryptographic obfuscator.  In particular, the
old bundled QASM files have not been regenerated and should not be treated as
correctness evidence.

The upstream repository has no top-level software license.  This GitHub fork
preserves its history and attribution and does not attempt to relicense the
inherited source.  Anyone planning to redistribute or use the code outside
GitHub should obtain appropriate permission from the upstream authors.

## What was repaired

### Circuit-rewrite core

- **Wire exchanges are now simultaneous.**  The old `swap_qubits` routine
  changed only the first matching operand of a multi-qubit gate.  A CNOT on
  the two exchanged wires could therefore become a CNOT whose control and
  target were the same qubit.  The new helper maps every operand from the
  original gate, including all three operands of a three-qubit gate.  Two
  small Coq examples cover the direct CNOT failure mode.
- **Inserted rotations now cancel exactly.**  Rotation indices have period
  `2 * Rzk_k`.  The old inverse used only half of that period and could differ
  from the intended inverse by a Pauli-Z operation.  The inserted inverse is
  now `2 * Rzk_k - i`.
- **Inserted CNOT structure is no longer discarded.**  The top-level Coq
  pipeline computed `cnotsadd` and then accidentally ran its second local
  rewrite pass on the earlier `composite` circuit.  The second pass now
  receives `cnotsadd`.

These repairs have been compiled and re-extracted into the OCaml executable,
as described under **Build and smoke-test status** below.  The two examples
check the index mapping, not the semantics of the whole obfuscation pass.

### OCaml driver and wire bookkeeping

- **Teleportation pools are kept separate.**  Constant-size moves now take
  origins from the live-wire pool and both helper and destination wires from
  the clean-wire pool.  Old origins and temporary answer wires are returned
  to the clean pool after the move.  The old code accidentally derived part
  of the clean pool from the shuffled live-wire list, consumed only one clean
  wire per move although two are required, and could mark untouched
  destinations as live when its argument lists had different lengths.
- **The destination of a growing move is now identified correctly.**  The
  extracted teleportation routine allocates helper wires first and destination
  wires second.  The old driver marked the helper range as live.  It now uses
  the actual destination range.
- **Moves are limited by the wires actually available.**  A move uses no more
  live origins or clean wire pairs than exist, and random insertion uses a
  nonzero bound even for an empty circuit.
- **Wire bookkeeping now fails closed.**  At epoch boundaries and after decoy
  promotion, the driver checks that live and clean pools contain unique,
  in-range wires, remain disjoint, and cover the declared circuit width.  It
  also checks that every original logical wire has one distinct placement in
  the live pool.
- **Original logical-wire placement is tracked explicitly.**  Teleportation
  moves a logical state to a different physical wire.  The driver now carries
  an ordered map from every original logical wire to its current physical
  location.  This is a placement map for all original data wires, not a list
  of designated output wires.  The map is printed and included as comments in
  generated QASM.  A consumer must honor it; the circuit does not automatically
  swap those states back to their original indices.  Applying a later routing
  pass can make the comments stale unless that pass also updates the map.
- **Runs are no longer identical by default.**  The driver initializes its
  pseudo-random generator from the system by default and accepts `--seed N`
  for a reproducible run.  OCaml's standard `Random` module is not a
  cryptographically secure generator, so this is reproducibility hygiene,
  not a security guarantee.
- **The repaired rotation rewrite is now reachable.**  The local-operation
  selector has four cases numbered 0 through 3, but the old exclusive random
  bound produced only 0, 1, or 2.  The bound is now 4, allowing case 3 to use
  the corrected rotation pair.

### OpenQASM boundary

- **Unsupported state-changing constructs now fail closed.**  Measurement,
  reset, and classical conditionals previously printed a warning and then
  disappeared from the translated circuit.  They now stop translation with a
  clear error.  Barriers are still removed intentionally because they do not
  change the circuit's unitary action; this also means their scheduling intent
  is not preserved.
- **The original logical-wire placement map is recorded in generated output.**
  Generated QASM includes comments recording where every original logical
  wire ends up.

### Benchmark harness

- **A failed obfuscator run no longer looks like benchmark data.**  The runner
  now checks the executable's exit status and parses its labeled count records
  instead of relying on fixed output-line positions.
- **A failed staq run no longer becomes a fabricated gate count.**  The runner
  invokes staq directly, checks its exit status, validates the OpenQASM header,
  and counts executable statements instead of piping unchecked output to
  `wc -l`.
- **Invalid CNOTs are rejected rather than hidden.**  The old Qiskit adapter
  silently omitted a CNOT when its two operands matched.  It now stops and
  reports the invalid file and wire.
- **Benchmark runs are reproducible without restoring the fixed-seed default.**
  The harness passes an explicit benchmark seed, while ordinary executable
  runs still use fresh pseudo-random initialization.  Rotation conversion now
  uses the library value of pi rather than the decimal approximation `3.14`.

## Structural regression check

`tests/audit_obfuscated_qasm.py` is a dependency-free scanner for generated
OpenQASM.  It checks the OpenQASM 2.0 header, parses every CNOT line, and
rejects a CNOT whose control and target refer to the same qubit.  It accepts
files or directories:

```sh
python3 tests/audit_obfuscated_qasm.py path/to/new-output.qasm
```

The default is strict and returns a failure status for any finding.  The
regression suite demonstrates both acceptance of a clean fixture and rejection
of a deliberately invalid fixture:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The GitHub Actions workflow runs those tests.  It also inventories the
historical results in report-only mode, so their known defects remain visible
without presenting them as newly generated output.

Additional fast tests exercise the wire-transposition invariant and check that
the repaired source patterns are present in both the Coq and extracted OCaml
code.  These are regression sentinels, not semantic proofs.

## Build and smoke-test status

The repaired Coq sources compile, extract, and link successfully with Coq
8.13.2, OCaml 4.12.0, dune 3.24.2, and `openQASM` 0.4.0.  Running
`make obfuscator` regenerated `Obfuscator/extraction/ExtractedCode.ml` and
built `obfuscator.exe`.

The upstream versions pinned in the README are not available as a native
Apple-silicon opam switch, so three small compatibility changes were needed:
two old proof scripts were made independent of tactic goal ordering, and
`RotationMerging.v` now imports and names the finite-set property module
explicitly.  These changes affect proof/build syntax, not circuit definitions.
The `Makefile` was also repaired so it creates `CoqMakefile` before invoking
it.

A reproducible smoke test used the nine-wire, 105-gate `tof_5.qasm` input with
seed 42.  The rebuilt program produced a 109-wire, 4,572-gate raw output and
a 2,058-gate VOQC-cleaned output.  Each output contained 1,324 CNOT statements;
the strict audit found zero malformed or same-wire CNOTs in either file.  Both
files carried the same complete nine-entry original logical-wire placement
map, and the new runtime bookkeeping checks completed without error.  This
test confirms that the repaired build and structural checks work end to end;
it is not a proof that the complete rewritten circuit implements the same
unitary.  Separate executable checks also confirmed that a same-wire CNOT and
a circuit containing measurement are rejected rather than translated.

## Status of the bundled QASM

The 40 files named `Obfuscator/results/*-obfuscated.qasm` were produced before
these repairs.  A full structural inventory finds **431 self-CNOTs** among
85,573 CNOT statements.  A CNOT cannot use the same qubit as both control and
target, so these files are invalid artifacts and are not evidence that the
repaired source is correct.

The inventory can be reproduced with:

```sh
python3 tests/audit_obfuscated_qasm.py \
  --report-only Obfuscator/results/*-obfuscated.qasm
```

The modern compatible toolchain now builds and the Coq source has been
re-extracted.  Regenerating the full benchmark set remains a separate follow-up:
record the toolchain and seeds, put an end-to-end equivalence check in place,
and run the structural audit in strict mode, without `--report-only`.

## Security limits

This prototype does not provide either of the standard cryptographic
obfuscation guarantees:

- **Not indistinguishability obfuscation (iO).**  There is no proof that two
  same-size circuits with the same behavior produce computationally
  indistinguishable protected descriptions.
- **Not virtual-black-box (VBB) obfuscation.**  There is no simulator showing
  that everything learned from the published circuit could also be learned
  from input-output access alone.

The implementation is best viewed as a heuristic for making ordinary circuit
optimization and the quantum minimum-equivalent-circuit problem (QMECP) more
difficult.  QMECP asks for a smaller circuit with the same operation.  Even
resistance to that task is an empirical goal here, not a proof.

For an outer protection layer around a fused `KeyGen`, global resistance to
shrinking is not enough.  An attacker may instead look for one useful internal
entry point, such as a continuation that accepts a caller-chosen label.  The
repository contains no proof that such an interface is hidden, no protection
against adaptive quantum access to that interface, and no authentication of
intermediate states.  Any use in that setting therefore needs a separately
stated and tested interface-extraction assumption or a stronger cryptographic
outer obfuscator.

## Verification still needed

Before relying on this branch for new experimental results:

1. **Reproduce the source build in CI and on the historical stack.**  The
   repaired source has been compiled with the modern compatible versions
   listed above, but the lightweight GitHub workflow currently runs only
   dependency-free Python structural and source-invariant checks.  A
   containerized job should compile and extract the source, and should also
   exercise the exact historical versions pinned by upstream when that
   platform is available.
2. **Prove or test whole-pass equivalence.**  Check the input and output
   circuits as unitaries, including the final physical placement of every
   original logical wire and the promised state of every helper wire.  The
   small Coq examples are not a replacement for this check.
3. **Regenerate every bundled result.**  Use recorded seeds, run the strict
   structural audit, and compare the new result with an independent simulator
   or equivalence checker.  Do the same for the VOQC-optimized output.
4. **Exercise parser failure paths.**  Add end-to-end cases for measurement,
   reset, conditionals, barriers, multiple quantum registers, unsupported
   gates, empty circuits, and malformed input.  Confirm that no executable
   operation is silently dropped.
5. **Exercise parameter boundaries.**  Test small circuits, zero or one
   epoch, insufficient helper wires, and parameter combinations that could
   otherwise cause division by zero, negative counts, or invalid random
   bounds.
6. **Validate placement-map handling.**  Either make every downstream consumer
   read the emitted original logical-wire placement map or append a verified
   final permutation that restores the original wire placement.  Confirm the
   current assumption that `E.optimize` preserves wire indices, and ensure any
   later routing or compilation pass updates the placement map.
7. **Choose randomness appropriate to the claim.**  Reproducible seeds are
   useful for benchmarking.  A security experiment that treats random choices
   as secret needs a cryptographically secure source and a clear key/seed
   model.
8. **Red-team the actual security target.**  Flatten and resynthesize the
   generated circuit, try several optimizers, search specifically for useful
   internal interfaces, and publish attack success rates together with circuit
   size, depth, and runtime.  These experiments can measure a heuristic; they
   cannot establish iO or VBB security.
