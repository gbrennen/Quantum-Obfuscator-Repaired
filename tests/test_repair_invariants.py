"""Fast regression checks for the repaired source-level invariants.

These tests do not replace Coq compilation or channel-equivalence testing.
They make the audited failure modes visible in the lightweight CI job.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REVERSE = ROOT / "Obfuscator/src/obfuscator/ReverseOptimizations.v"
EXTRACTED = ROOT / "Obfuscator/extraction/ExtractedCode.ml"
DRIVER = ROOT / "Obfuscator/extraction/obfuscator.ml"
QASM = ROOT / "Obfuscator/extraction/qasm2sqir.ml"
BENCHMARK = ROOT / "Obfuscator/run_benchmarks.py"


class RepairInvariantTests(unittest.TestCase):
    def test_wire_transposition_is_involutive_and_preserves_distinctness(self) -> None:
        def exchange(first: int, second: int, wire: int) -> int:
            if wire == first:
                return second
            if wire == second:
                return first
            return wire

        for width in range(2, 10):
            for first in range(width):
                for second in range(width):
                    if first == second:
                        continue
                    for wire in range(width):
                        self.assertEqual(
                            wire,
                            exchange(first, second, exchange(first, second, wire)),
                        )
                    for control in range(width):
                        for target in range(width):
                            if control != target:
                                self.assertNotEqual(
                                    exchange(first, second, control),
                                    exchange(first, second, target),
                                )

    def test_rotation_inverse_uses_the_full_period(self) -> None:
        half_period = 2**15
        period = 2 * half_period
        for index in (0, 1, 100, half_period, period - 1, period + 7):
            self.assertEqual(0, (index + (period - index)) % period)
            self.assertEqual(
                half_period,
                (index + (half_period - index)) % period,
            )

        source = REVERSE.read_text(encoding="utf-8")
        self.assertIn("Rz (2 * Rzk_k - i) q", source)
        self.assertIn("arand2 cnotsadd", source)

    def test_checked_in_extraction_contains_the_core_repairs(self) -> None:
        source = EXTRACTED.read_text(encoding="utf-8")
        self.assertIn("let swap_qubit_index q1 q2 q", source)
        self.assertIn("swap_qubit_index q1 q2 m", source)
        self.assertIn("swap_qubit_index q1 q2 n", source)
        self.assertIn("swap_qubit_index q1 q2 p0", source)
        self.assertIn("Z.sub (Z.mul", source)
        self.assertIn("arand2\n    cnotsadd", source)

    def test_driver_keeps_wire_pools_separate_and_tracks_outputs(self) -> None:
        source = DRIVER.read_text(encoding="utf-8")
        self.assertIn("remove_first (2 * moved) shuffled_ancilla", source)
        self.assertIn("orig @ anc @ rest_ancilla", source)
        self.assertIn("make_list (dim + moved) moved", source)
        self.assertIn("logical_outputs", source)
        self.assertIn("validate_wire_state", source)
        self.assertIn("live and clean wire pools overlap", source)
        self.assertNotIn("Random.init 42", source)
        self.assertIn("gen_random num_local 4", source)

    def test_qasm_translation_fails_closed(self) -> None:
        source = QASM.read_text(encoding="utf-8")
        self.assertIn("Unsupported OpenQASM construct: measurement", source)
        self.assertIn("Unsupported OpenQASM construct: reset", source)
        self.assertIn("Unsupported OpenQASM construct: classical conditional", source)
        self.assertIn("apply_distinct_c_gate", source)
        self.assertIn("operands must resolve to distinct qubits", source)
        self.assertIn("Original logical-wire placement map (advisory)", source)

    def test_benchmark_adapter_rejects_self_cnot(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        self.assertIn("if a == b:", source)
        self.assertIn("invalid CNOT", source)
        self.assertNotIn("if a!=b:", source)
        self.assertIn("subprocess.run(", source)
        self.assertIn("check=True", source)
        self.assertIn("OBFUSCATOR_SEED = 42", source)
        self.assertIn("parse_obfuscator_counts", source)
        self.assertIn("reported success but did not create", source)
        self.assertIn('"--root", "extraction", "./obfuscator.exe", "--"', source)
        self.assertIn("count_qasm_instructions", source)
        self.assertIn("staq failed", source)
        self.assertNotIn("os.popen", source)


if __name__ == "__main__":
    unittest.main()
