"""Regression tests for the dependency-free QASM structural audit."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import unittest

from tests.audit_obfuscated_qasm import audit_paths, discover_qasm_files, main


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
HISTORICAL_RESULTS = REPOSITORY_ROOT / "Obfuscator" / "results"


class StructuralAuditTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> int:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            return main(arguments)

    def test_clean_fixture_passes(self) -> None:
        result = audit_paths([FIXTURES / "clean.qasm"])
        self.assertEqual(2, result.cnot_count)
        self.assertEqual((), result.violations)
        self.assertEqual(0, self.run_cli([str(FIXTURES / "clean.qasm")]))

    def test_self_cnot_is_rejected(self) -> None:
        result = audit_paths([FIXTURES / "self_cnot.qasm"])
        self.assertEqual(1, result.cnot_count)
        self.assertEqual(1, len(result.violations))
        self.assertEqual("self-cnot", result.violations[0].code)
        self.assertEqual(
            1,
            self.run_cli([str(FIXTURES / "self_cnot.qasm")]),
        )

    def test_report_only_does_not_hide_findings(self) -> None:
        result = audit_paths([FIXTURES / "self_cnot.qasm"])
        self.assertTrue(result.violations)
        self.assertEqual(
            0,
            self.run_cli(
                ["--report-only", str(FIXTURES / "self_cnot.qasm")]
            ),
        )

    def test_every_bundled_qasm_output_is_inventoried(self) -> None:
        expected = {
            path.resolve()
            for path in HISTORICAL_RESULTS.glob("*-obfuscated.qasm")
        }
        discovered = set(discover_qasm_files(expected))
        self.assertTrue(expected, "no bundled obfuscated QASM outputs found")
        self.assertEqual(expected, discovered)

        # These files predate the generator repairs, so this test deliberately
        # inventories rather than requiring them to pass.  Newly generated
        # artifacts must be checked with the strict default mode.
        result = audit_paths(expected)
        self.assertEqual(expected, set(result.files))


if __name__ == "__main__":
    unittest.main()
