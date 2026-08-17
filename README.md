# Quantum Circuit Obfuscator

> **Correctness-repair fork.** This fork fixes several source-level defects in
> the upstream research prototype and adds structural regression checks.  The
> historical QASM files in `Obfuscator/results/` predate those repairs and are
> known to contain invalid same-wire CNOT instructions.  See
> [REPAIRS.md](REPAIRS.md) for the exact fixes, validation status, remaining
> work, and security limitations.  This software is not an implementation of
> indistinguishability obfuscation or virtual-black-box obfuscation.

This repository contains an implementation of an obfuscator for quantum circuits. It is the accompanying software artifact for the paper **Scalable Verification of Quantum Supremacy based on Circuit Obfuscation** *Shouvanik Chakrabarti, Chi-Ning Chou, Kai-Min Chung, and Xiaodi Wu*.

## Overview

The intended behavior is to take a quantum circuit, add 100 wires and more
gates, and produce a rewritten circuit with the same logical behavior.  In
this repair fork, that equivalence remains a property to be established by a
whole-circuit proof or independent equivalence tests.  The repaired source has
been compiled and re-extracted, and both outputs from a small smoke test pass
the strict structural audit, but those checks do not by themselves prove
equivalence.

The obfuscator is based on primitives from **SQIR**, a Small Quantum Intermediate Representation for quantum programs, and the Verified Optimizer for Quantum Circuits **(VOQC)**. The repository is built upon a clone of the [SQIR repository](https://github.com/inQWIRE/SQIR). The implementation of the obfuscator is found under the Obfuscator subdirectory.

## Compilation

To compile the obfuscator follow these instructions:

**Dependencies**
We recommend using the Ocaml Package Manager `opam` to install these dependencies.
Install opam using the appropriate instructions for your system found [here](https://opam.ocaml.org/doc/Install.html).

  * OCaml version 4.08.1 (`opam switch create 4.08.1`)
  * Coq version 8.10.1 (`opam pin add coq 8.10.1`)
  * dune (`opam install dune`)
  * menhir (`opam install menhir`)
  * OCaml OpenQASM parser (`opam install openQASM`)

Once the dependencies are installed, run `make obfuscator` in the repository
root.  This produces
`Obfuscator/extraction/_build/default/obfuscator.exe`.

This repair branch has also been built successfully with OCaml 4.12.0, Coq
8.13.2, and dune 3.24.2.  See [REPAIRS.md](REPAIRS.md) for the compatibility
changes and exact validation performed.

## Execution

All commands for running the obfuscator and the benchmarks are to be run in the Obfuscator subdirectory.

# Running the obfuscator

In order to use the obfuscator executable run the command

`dune exec ./obfuscator.exe <input_file> <output_file> <output_optimized_with_voqc> --root extraction`

This returns an obfuscated version of `<input_file>` in `<output_file>`, and a version of `<output_file>` that has been further optimized by VOQC in `<output_optimized_with_voqc>`. For instance, to run the obfuscator on the benchmark `tof_5` and obtain the obfuscated output `out.qasm` and subsequently optimized circuit `optimized_voqc.qasm` run the command

`dune exec ./obfuscator.exe benchmarks/Arithmetic_and_Toffoli/tof_5.qasm out.qasm optimized_voqc.qasm --root extraction`

By default each run receives fresh pseudo-random initialization.  Append
`-- --seed 123` to make a run reproducible.  The generated QASM contains
comments giving the final physical location of every original logical wire.
Downstream tools must preserve or consume this original logical-wire placement
map.

# Running the benchmarks

The benchmark script has the following dependencies.
* **Python**: The benchmarking script requires a working Python 3 distribution that can be obtained [here](https://www.python.org/downloads/). 
* **Python packages**: Install NumPy, Qiskit, and PyZX with a compatible Python
  package manager.  For example: `pip install numpy qiskit pyzx`.
* **staq** : A clone of the staq repository is included under Obfuscator/benchmarks/staq. To build the executable for a UNIX based system with `cmake` and a C++ distribution , run the following commands in this directory

``` sh
cd build
cmake ..
make staq
```
For other systems follow the [installation instructions](https://github.com/softwareQinc/staq) for staq in the directory Obfuscator/benchmarks/staq.

Given all the dependencies, `Obfuscator/run_benchmarks.py` executes the
benchmarks and writes CSV-formatted results to the file supplied on the command
line.  Running

``` sh
python run_benchmarks.py results.csv
```
in the Obfuscator directory will return the results in results.csv.

## Main components
The main source components of the obfuscator can be found in

* `Obfuscator/src/obfuscator/ReverseOptimizations.v` : contains the main primitives that are combined to form the obfuscator.
* `Obfuscator/extraction/obfuscator.ml` : contains the implementation of the obfuscator executable.
* `Obfuscator/run_benchmarks.py` : contains the code that reproduces the numerical benchmarks found in the paper.
