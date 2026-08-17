#!/usr/bin/env python3
"""Perform small, dependency-free structural checks on OpenQASM output.

The default mode is strict: any malformed CNOT or CNOT whose control and
target name the same qubit makes the command fail.  ``--report-only`` is
provided for inventorying historical artifacts that are known to predate a
generator fix; it never changes what is reported, only the process exit code.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


CX_RE = re.compile(r"^\s*cx\b(?P<operands>.*?)\s*;?\s*$", re.IGNORECASE)
QUBIT_RE = re.compile(
    r"^(?P<register>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\[\s*(?P<index>[0-9]+)\s*\])?$"
)
HEADER_RE = re.compile(r"^\s*OPENQASM\s+2\.0\s*;?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Violation:
    """One structural problem, with a source location suitable for CI logs."""

    path: Path
    line: int
    code: str
    message: str


@dataclass(frozen=True)
class AuditResult:
    """Aggregate result for one or more QASM files."""

    files: tuple[Path, ...]
    cnot_count: int
    violations: tuple[Violation, ...]


def discover_qasm_files(paths: Iterable[Path]) -> tuple[Path, ...]:
    """Expand files and directories into a sorted, duplicate-free QASM list."""

    discovered: set[Path] = set()
    missing: list[Path] = []
    for supplied_path in paths:
        path = supplied_path.resolve()
        if path.is_file():
            if path.suffix.lower() == ".qasm":
                discovered.add(path)
            else:
                missing.append(path)
        elif path.is_dir():
            discovered.update(
                candidate.resolve()
                for candidate in path.rglob("*.qasm")
                if candidate.is_file()
            )
        else:
            missing.append(path)

    if missing:
        rendered = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"not a QASM file or directory: {rendered}")
    if not discovered:
        raise FileNotFoundError("no .qasm files were found")
    return tuple(sorted(discovered))


def _operand_identity(text: str) -> tuple[str, int | None] | None:
    """Return a normalized register/index pair for one CNOT operand."""

    match = QUBIT_RE.fullmatch(text.strip())
    if match is None:
        return None
    index = match.group("index")
    return match.group("register"), None if index is None else int(index)


def _same_qubit(
    control: tuple[str, int | None], target: tuple[str, int | None]
) -> bool:
    """Detect equal operands, including overlapping whole-register operands."""

    control_register, control_index = control
    target_register, target_index = target
    if control_register != target_register:
        return False
    return (
        control_index is None
        or target_index is None
        or control_index == target_index
    )


def audit_file(path: Path) -> tuple[int, list[Violation]]:
    """Audit one OpenQASM file and return its CNOT count and violations."""

    violations: list[Violation] = []
    cnot_count = 0
    saw_content = False
    saw_header = False

    with path.open("r", encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, start=1):
            line = raw_line.split("//", 1)[0].strip()
            if not line:
                continue
            if not saw_content:
                saw_content = True
                saw_header = HEADER_RE.fullmatch(line) is not None

            match = CX_RE.fullmatch(line)
            if match is None:
                continue

            cnot_count += 1
            operands = match.group("operands").split(",")
            if len(operands) != 2:
                violations.append(
                    Violation(
                        path,
                        line_number,
                        "malformed-cnot",
                        "CNOT must have exactly two qubit operands",
                    )
                )
                continue

            control = _operand_identity(operands[0])
            target = _operand_identity(operands[1])
            if control is None or target is None:
                violations.append(
                    Violation(
                        path,
                        line_number,
                        "malformed-cnot",
                        "CNOT operands must be register names or indexed qubits",
                    )
                )
                continue
            if _same_qubit(control, target):
                violations.append(
                    Violation(
                        path,
                        line_number,
                        "self-cnot",
                        "CNOT control and target refer to the same qubit",
                    )
                )

    if not saw_header:
        violations.append(
            Violation(
                path,
                1,
                "missing-header",
                "first non-comment line must be 'OPENQASM 2.0;'",
            )
        )
    return cnot_count, violations


def audit_paths(paths: Iterable[Path]) -> AuditResult:
    """Audit every QASM file reached from ``paths``."""

    files = discover_qasm_files(paths)
    cnot_count = 0
    violations: list[Violation] = []
    for path in files:
        file_cnot_count, file_violations = audit_file(path)
        cnot_count += file_cnot_count
        violations.extend(file_violations)
    return AuditResult(files, cnot_count, tuple(violations))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="QASM files or directories to scan recursively",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="report violations but return success (for historical inventories)",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=20,
        help="maximum violation details to print (default: 20; 0 prints all)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_errors < 0:
        raise SystemExit("--max-errors must be non-negative")

    try:
        result = audit_paths(args.paths)
    except (FileNotFoundError, OSError) as error:
        print(f"audit error: {error}", file=sys.stderr)
        return 2

    limit = None if args.max_errors == 0 else args.max_errors
    shown = result.violations[:limit]
    for violation in shown:
        print(
            f"{violation.path}:{violation.line}: "
            f"{violation.code}: {violation.message}",
            file=sys.stderr,
        )
    hidden = len(result.violations) - len(shown)
    if hidden:
        print(f"... {hidden} additional violation(s) omitted", file=sys.stderr)

    print(
        f"Audited {len(result.files)} QASM file(s), "
        f"{result.cnot_count} CNOT statement(s), "
        f"{len(result.violations)} violation(s)."
    )
    if result.violations and not args.report_only:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
