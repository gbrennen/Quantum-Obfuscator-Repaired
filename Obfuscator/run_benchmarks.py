'''
    We use the Qiskit optimizer with the gate set {u1,h,x,cnot}
    References:
    - https://github.com/Qiskit/qiskit-terra/blob/master/qiskit/transpiler/preset_passmanagers/level2.py
'''

import math
import numpy
import os
from qiskit import QuantumCircuit
from qiskit.compiler import transpile
from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import Unroller, Optimize1qGates, CommutationAnalysis, CommutativeCancellation, CXCancellation, Depth, FixedPoint, Collect2qBlocks, ConsolidateBlocks
import sys
import pyzx as zx
import re
import subprocess


OBFUSCATOR_SEED = 42
OBFUSCATOR_COUNT_RE = re.compile(
    r"^(Original|Final after obfuscation|After optimization with VOQC):"
    r"\s*Total\s+(\d+),.*\bCNOT\s+(\d+)\s*$"
)


def parse_obfuscator_counts(output):
    """Extract gate counts from labeled obfuscator status lines."""
    counts = {}
    for line in output.splitlines():
        match = OBFUSCATOR_COUNT_RE.match(line)
        if match is None:
            continue
        label = match.group(1)
        if label in counts:
            raise ValueError("duplicate obfuscator output record: {}".format(label))
        counts[label] = (int(match.group(2)), int(match.group(3)))

    required = (
        "Original",
        "Final after obfuscation",
        "After optimization with VOQC",
    )
    missing = [label for label in required if label not in counts]
    if missing:
        raise ValueError(
            "obfuscator output is missing labeled count record(s): {}\n{}"
            .format(", ".join(missing), output)
        )
    return counts

def count(d):
    sum = 0
    for k in d.keys():
        sum += d[k]
    return sum


def count_qasm_instructions(output):
    """Count executable statements in flattened OpenQASM text."""
    metadata_prefixes = (
        "OPENQASM", "include", "qreg", "creg", "gate", "opaque", "barrier"
    )
    instruction_count = 0
    saw_header = False
    for raw_line in output.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if line.startswith("OPENQASM"):
            saw_header = True
        if not line or line.startswith(metadata_prefixes):
            continue
        if not line.endswith(";"):
            raise ValueError("unexpected staq output line: {}".format(raw_line))
        instruction_count += 1
    if not saw_header:
        raise ValueError("staq output did not contain an OPENQASM header")
    return instruction_count
    
def get_closest_multiple_of_pi(theta):
    l = [x * (math.pi/4) for x in range(-7,8)]
    l1 = [abs(x - theta) for x in l]
    return(range(-7,8)[l1.index(min(l1))])

def run_on_file(fname,file_handler,logfile):

    print("====================================================================")
    print("Running benchmark {}".format(fname))

    # Call the obfuscator; this also runs VOQC
    obfuscated_file = "results/"+file_handler+"-obfuscated.qasm"
    post_voqc_file = "results/"+file_handler+"-aftervoqc.qasm"
    command = [
        "dune", "exec", "--root", "extraction", "./obfuscator.exe", "--",
        fname, obfuscated_file, post_voqc_file,
        "--seed", str(OBFUSCATOR_SEED),
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            "obfuscator failed for {} (exit {}):\nstdout:\n{}\nstderr:\n{}"
            .format(fname, error.returncode, error.stdout, error.stderr)
        ) from error

    counts = parse_obfuscator_counts(completed.stdout)
    gates_orig, cnot_orig = counts["Original"]
    gates_obf, cnot_obf = counts["Final after obfuscation"]
    gates_voqc, _ = counts["After optimization with VOQC"]

    # Run Qiskit

    missing_outputs = [
        path for path in (obfuscated_file, post_voqc_file)
        if not os.path.exists(path)
    ]
    if missing_outputs:
        raise FileNotFoundError(
            "obfuscator reported success but did not create: {}"
            .format(", ".join(missing_outputs))
        )

    inqasm = open(obfuscated_file, "r")
    tmp = open("copy-qiskit.qasm", "w") # hardcoded filename
    p_ccz = re.compile("ccz (.*), (.*), (.*);")
    p_ccx = re.compile("ccx (.*), (.*), (.*);")
    p_cx = re.compile("cx (.*),(.*);")
    p_rz = re.compile("rz15\((.*)\) (.*);")
    
    for line in inqasm:
        m1 = p_ccx.match(line)
        m2 = p_ccz.match(line)
        m3 = p_cx.match(line)
        m4 = p_rz.match(line)
        if m1:
            a = m1.group(1)
            b = m1.group(2)
            c = m1.group(3)
            tmp.write("h %s;\n" % (c))
            tmp.write("cx %s, %s;\n" % (b, c))
            tmp.write("tdg %s;\n" % (c))
            tmp.write("cx %s, %s;\n" % (a, c))
            tmp.write("t %s;\n" % (c))
            tmp.write("cx %s, %s;\n" % (b, c))
            tmp.write("tdg %s;\n" % (c))
            tmp.write("cx %s, %s;\n" % (a, c))
            tmp.write("cx %s, %s;\n" % (a, b))
            tmp.write("tdg %s;\n" % (b))
            tmp.write("cx %s, %s;\n" % (a, b))
            tmp.write("t %s;\n" % (a))
            tmp.write("t %s;\n" % (b))
            tmp.write("t %s;\n" % (c))
            tmp.write("h %s;\n" % (c))
        elif m2:
            a = m2.group(1)
            b = m2.group(2)
            c = m2.group(3)
            tmp.write("cx %s, %s;\n" % (b, c))
            tmp.write("tdg %s;\n" % (c))
            tmp.write("cx %s, %s;\n" % (a, c))
            tmp.write("t %s;\n" % (c))
            tmp.write("cx %s, %s;\n" % (b, c))
            tmp.write("tdg %s;\n" % (c))
            tmp.write("cx %s, %s;\n" % (a, c))
            tmp.write("cx %s, %s;\n" % (a, b))
            tmp.write("tdg %s;\n" % (b))
            tmp.write("cx %s, %s;\n" % (a, b))
            tmp.write("t %s;\n" % (a))
            tmp.write("t %s;\n" % (b))
            tmp.write("t %s;\n" % (c))
        elif m3:
            a = m3.group(1).strip()
            b = m3.group(2).strip()
            if a == b:
                raise ValueError(
                    "invalid CNOT in {}: control and target are both {}"
                    .format(obfuscated_file, a)
                )
            tmp.write("cx %s, %s;\n" % (a, b))
        elif m4:
            a = m4.group(1)
            b = m4.group(2)
            tmp.write("u1(%f) %s;\n" % ((int(a)*math.pi/32768), b))
        else:
            tmp.write(line)
    tmp.close()
    circ = QuantumCircuit.from_qasm_file("copy-qiskit.qasm")

    num_gates_before = count(circ.count_ops())
    # getting a t-count only makes sense for the current benchmarks, which only 
    # contain rotations by PI/4
    t_count_before = 0
    for inst, _, _ in circ.data:
        if (inst.name == "t" or inst.name == "tdg"):
            t_count_before += 1
    # print("\nORIGINAL: %d gates, %d T-gates" % (num_gates_before, t_count_before))

    # A
    basis_gates = ['u1', 'h', 'x', 'cx']
    _unroll = Unroller(basis_gates)
    _depth_check = [Depth(), FixedPoint('depth')]
    def _opt_control(property_set):
        return not property_set['depth_fixed_point']
    _opt = [Optimize1qGates(), CommutativeCancellation()]
    pmA = PassManager()
    pmA.append(_unroll)
    pmA.append([CommutationAnalysis()])
    pmA.append(_depth_check + _opt, do_while=_opt_control)
    circA = pmA.run(circ)
    num_gates_afterA = count(circA.count_ops())
    t_count_afterA = 0
    for inst, _, _ in circA.data:
        if (inst.name == "u1"):
            if (get_closest_multiple_of_pi(inst.params[0]) % 2 == 1):
                t_count_afterA += 1
    with open(logfile,'a+') as f:
        reductionA = num_gates_before - num_gates_afterA
        gates_qiskit = gates_obf - reductionA
        # f.write("After optimization with Qiskit: {} gates, {} T-gates\n".format(num_gates_before - reduction, t_count_afterA))

    # Run staq and check its status directly.  The old shell pipeline reported
    # only wc's status, so a missing or crashed staq process could look like a
    # successful zero-line result.
    staq_command = [
        "./benchmarks/staq/build/staq", "-S", "-O2", "copy-qiskit.qasm"
    ]
    try:
        staq_completed = subprocess.run(
            staq_command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            "staq failed (exit {}):\nstdout:\n{}\nstderr:\n{}"
            .format(error.returncode, error.stdout, error.stderr)
        ) from error
    except OSError as error:
        raise RuntimeError("could not start staq: {}".format(error)) from error

    gates_after = count_qasm_instructions(staq_completed.stdout)
    reductionS = max(num_gates_before - gates_after,0)
    gates_staq = gates_obf - reductionS
    # with open(logfile,'a+') as f:
    #     f.write("After Staq optimization, number of gates is " + str(num_gates_before-reduction))
    #     f.write("\n\n\n=======================================================\n")
    with open(logfile,'a+') as f:
        f.write('{:>25},{:>25},{:>25},{:>25},{:>25},{:>25},{:>25},{:>25}\n'.format(
            file_handler,gates_orig,cnot_orig,gates_obf,cnot_obf,gates_voqc,gates_qiskit,gates_staq))


if __name__ == "__main__":
    logfile=sys.argv[1]

    with open(logfile,'w+') as f:
        f.write('{:>25},{:>25},{:>25},{:>25},{:>25},{:>25},{:>25},{:>25}\n'.format(
            'Benchmarks','Total gates (Original)','CNOT (Original)','Total gates (Obfuscated)',
            'CNOT (Obfuscated)','Total gates(VOQC)','Total gates (Qiskit)','Total gates (STAQ)\n'))

    # Arithmetic Benchmarks
    for fname in os.listdir("benchmarks/Arithmetic_and_Toffoli"):
        run_on_file("benchmarks/Arithmetic_and_Toffoli/%s" % fname,fname.split('.')[0],logfile)
    # Google Benchmarks
    for fname in os.listdir("benchmarks/Google-supremacy-examples"):
        run_on_file("benchmarks/Google-supremacy-examples/%s" % fname,fname.split('.')[0],logfile)
    # IQP Benchmarks
    for fname in os.listdir("benchmarks/IQP-supremacy-examples"):
        run_on_file("benchmarks/IQP-supremacy-examples/%s" % fname,fname.split('.')[0],logfile)
