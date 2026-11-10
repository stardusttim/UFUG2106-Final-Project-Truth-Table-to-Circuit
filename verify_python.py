"""Run the Stage 1 program and independently verify its generated circuits."""

import csv
from pathlib import Path
import subprocess
import sys
import time


CASE_DIRECTORY = Path('stage1')
PROGRAM = Path('stage1.py')
OUTPUT = Path('python_output.txt')
RESULTS = Path('python_results.csv')
BLOCK_SIZE = 1024
GATE_TYPES = {'AND2': 0, 'OR2': 1, 'NOT': 2}
RESULT_COLUMNS = [
    'case', 'local_status', 'area', 'delay', 'runtime_ms',
    'target_delay', 'runtime_limit_ms',
]


def read_case(path):
    lines = path.read_text().splitlines()
    input_count = int(lines[0])
    output_count = int(lines[1])
    rows = lines[2].split()
    costs = [tuple(map(int, line.split())) for line in lines[3:6]]
    target = int(lines[6])
    runtime_limit = int(lines[7]) if len(lines) > 7 else 0
    return input_count, output_count, rows, costs, target, runtime_limit


def run_program(case_path):
    start = time.perf_counter()
    process = subprocess.run(
        [sys.executable, str(PROGRAM), str(case_path), str(OUTPUT)],
        capture_output=True,
        timeout=30,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    if process.returncode:
        raise ValueError(process.stderr.decode(errors='replace'))
    return elapsed_ms


def read_circuit(input_count, output_count, costs):
    lines = OUTPUT.read_text().splitlines()
    gates = [line.split() for line in lines[:-1]]
    outputs = list(map(int, lines[-1].split()))
    area = 0
    delays = [0] * (input_count + 1)

    for tokens in gates:
        assert int(tokens[0]) == len(delays)
        operation = tokens[1]
        cost_index = GATE_TYPES[operation]
        inputs = list(map(int, tokens[2:]))
        assert len(inputs) == (1 if operation == 'NOT' else 2)
        assert all(signal < len(delays) for signal in inputs)
        area += costs[cost_index][0]
        delays.append(max(delays[signal] for signal in inputs) + costs[cost_index][1])

    assert len(outputs) == output_count
    assert all(signal < len(delays) for signal in outputs)
    delay = max(delays[signal] for signal in outputs)
    return gates, outputs, area, delay


def verify_truth_table(input_count, rows, gates, outputs):
    """Simulate every assignment in blocks using integers as bit vectors."""
    for start_row in range(0, len(rows), BLOCK_SIZE):
        block = rows[start_row:start_row + BLOCK_SIZE]
        mask = (1 << len(block)) - 1
        values = [0] + [
            sum(((start_row + offset) >> (input_count - 1 - i) & 1) << offset
                for offset in range(len(block)))
            for i in range(input_count)
        ]

        for tokens in gates:
            operation = tokens[1]
            left = values[int(tokens[2])]
            if operation == 'NOT':
                value = left ^ mask
            elif operation == 'AND2':
                value = left & values[int(tokens[3])]
            else:
                value = left | values[int(tokens[3])]
            values.append(value)

        for column, signal in enumerate(outputs):
            expected = sum((row[column] == '1') << offset
                           for offset, row in enumerate(block))
            assert values[signal] == expected


def write_results(results):
    with RESULTS.open('w', newline='') as result_file:
        writer = csv.writer(result_file)
        writer.writerow(RESULT_COLUMNS)
        writer.writerows(results)


def main():
    results = []
    for case_path in sorted(CASE_DIRECTORY.glob('case_*.txt')):
        input_count, output_count, rows, costs, target, runtime_limit = read_case(case_path)
        try:
            elapsed_ms = run_program(case_path)
            gates, outputs, area, delay = read_circuit(input_count, output_count, costs)
            verify_truth_table(input_count, rows, gates, outputs)
            status = 'correct' if not runtime_limit or elapsed_ms <= runtime_limit else 'time limit exceeded'
            results.append([case_path.name, status, area, delay, round(elapsed_ms), target, runtime_limit])
            print(case_path.name, status, flush=True)
        except Exception as error:
            message = str(error)[:100]
            results.append([case_path.name, message, '', '', '', target, runtime_limit])
            print(case_path.name, 'error', message, flush=True)
        write_results(results)


if __name__ == '__main__':
    main()
