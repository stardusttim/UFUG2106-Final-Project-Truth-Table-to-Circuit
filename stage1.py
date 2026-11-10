#!/usr/bin/env python3
"""Synthesize a combinational circuit from a truth table."""

import sys
import time


def optimization_rank(area, delay, target_delay):
    """Feasible circuits beat infeasible ones, regardless of area."""
    if delay <= target_delay:
        return (0, area, delay)
    return (1, delay, area)


class Circuit:
    """Build topologically ordered gates and share identical expressions."""

    def __init__(self, input_count, gate_costs, target_delay):
        self.input_count = input_count
        self.costs = dict(zip(('AND2', 'OR2', 'NOT'), gate_costs))
        self.target_delay = target_delay
        self.arrival = [0] * (input_count + 1)
        self.gates = [None] * (input_count + 1)
        self.unique = {}
        self.one = self.gate('NOT', 0)
        self.negated_inputs = [0] + [
            self.gate('NOT', i) for i in range(1, input_count + 1)
        ]

    def gate(self, operation, left, right=-1):
        if operation == 'NOT':
            if left > self.input_count and self.gates[left][0] == 'NOT':
                return self.gates[left][1]
        else:
            # AND and OR are commutative; canonical ordering enables sharing.
            if left > right:
                left, right = right, left
            if left == right:
                return left
            if left == 0:
                return 0 if operation == 'AND2' else right

        key = (operation, left, right)
        result = self.unique.get(key)
        if result is None:
            result = len(self.gates)
            self.gates.append(key)
            inputs = (left,) if operation == 'NOT' else (left, right)
            self.arrival.append(max(self.arrival[i] for i in inputs) + self.costs[operation][1])
            self.unique[key] = result
        return result

    def select(self, variable, low, high):
        """Implement (not variable and low) or (variable and high)."""
        if low == high:
            return low
        if low == 0 and high == self.one:
            return variable
        if low == self.one and high == 0:
            return self.negated_inputs[variable]
        if low == 0:
            return self.gate('AND2', variable, high)
        if high == 0:
            return self.gate('AND2', self.negated_inputs[variable], low)
        if low == self.one:
            return self.gate('OR2', self.negated_inputs[variable], high)
        if high == self.one:
            return self.gate('OR2', variable, low)
        low_term = self.gate('AND2', self.negated_inputs[variable], low)
        high_term = self.gate('AND2', variable, high)
        return self.gate('OR2', low_term, high_term)

    def reachable(self, outputs):
        used = set(outputs)
        pending = list(outputs)
        while pending:
            node = pending.pop()
            if node <= self.input_count:
                continue
            operation, left, right = self.gates[node]
            for signal in (left,) if operation == 'NOT' else (left, right):
                if signal not in used:
                    used.add(signal)
                    pending.append(signal)
        return used

    def metrics(self, outputs):
        used = self.reachable(outputs)
        area = sum(self.costs[self.gates[i][0]][0]
                   for i in used if i > self.input_count)
        return area, max(self.arrival[i] for i in outputs)

    def rewritten(self, outputs, replace_operation):
        """Rebuild reachable gates with one De Morgan transformation."""
        result = Circuit(self.input_count, list(self.costs.values()), self.target_delay)
        mapping = list(range(self.input_count + 1)) + [0] * (len(self.gates) - self.input_count - 1)
        used = self.reachable(outputs)
        for node in range(self.input_count + 1, len(self.gates)):
            if node not in used:
                continue
            operation, left, right = self.gates[node]
            a = mapping[left]
            if operation == replace_operation:
                b = mapping[right]
                opposite = 'OR2' if operation == 'AND2' else 'AND2'
                inner = result.gate(opposite, result.gate('NOT', a), result.gate('NOT', b))
                mapping[node] = result.gate('NOT', inner)
            elif operation == 'NOT':
                mapping[node] = result.gate('NOT', a)
            else:
                mapping[node] = result.gate(operation, a, mapping[right])
        return result, [mapping[node] for node in outputs]

    def delay_optimized(self, outputs, deadline=None):
        """Map both polarities of each signal, choosing fastest implementations.

        Keeping the inverted form avoids forcing a NOT after every positive
        form. Different gates can use different De Morgan implementations.
        This minimizes arrival times within this mapping search, not over all
        equivalent circuits. Final selection measures actual shared-gate area.
        """
        result = Circuit(self.input_count, list(self.costs.values()), self.target_delay)
        positive = [0] * len(self.gates)
        negative = [0] * len(self.gates)
        negative[0] = result.one
        for node in range(1, self.input_count + 1):
            positive[node] = node
            negative[node] = result.negated_inputs[node]

        def fastest(*signals):
            # Root-gate area only breaks arrival-time ties. Actual total area
            # is evaluated after the whole candidate has been constructed.
            return min(signals, key=lambda signal: (
                result.arrival[signal],
                result.costs[result.gates[signal][0]][0]
                if signal > self.input_count else 0,
                signal,
            ))

        used = self.reachable(outputs)
        for node in range(self.input_count + 1, len(self.gates)):
            if node % 256 == 0 and deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError('post-synthesis optimization budget exhausted')
            if node not in used:
                continue
            operation, left, right = self.gates[node]
            if operation == 'NOT':
                positive[node], negative[node] = negative[left], positive[left]
                continue

            opposite = 'OR2' if operation == 'AND2' else 'AND2'
            direct = result.gate(operation, positive[left], positive[right])
            inverted = result.gate(opposite, negative[left], negative[right])
            positive[node] = fastest(direct, result.gate('NOT', inverted))
            negative[node] = fastest(inverted, result.gate('NOT', direct))

        return result, [positive[node] for node in outputs]

    def write(self, path, outputs):
        used = self.reachable(outputs)

        ids = list(range(self.input_count + 1))
        ids.extend([0] * (len(self.gates) - len(ids)))
        next_id = self.input_count + 1
        with open(path, 'w', encoding='ascii', newline='\n') as output_file:
            for node in range(self.input_count + 1, len(self.gates)):
                if node not in used:
                    continue
                ids[node] = next_id
                next_id += 1
                operation, left, right = self.gates[node]
                line = f'{ids[node]} {operation} {ids[left]}'
                if operation != 'NOT':
                    line += f' {ids[right]}'
                output_file.write(line + '\n')
            output_file.write(' '.join(str(ids[node]) for node in outputs) + '\n')


def synthesize(input_path, output_path):
    started = time.monotonic()
    with open(input_path, 'rb') as input_file:
        input_count = int(input_file.readline())
        output_count = int(input_file.readline())
        rows = input_file.readline().split()
        # Gate costs and target are used for post-synthesis optimization.
        gate_costs = [tuple(map(int, input_file.readline().split())) for _ in range(3)]
        target_delay = int(input_file.readline())
        limit_line = input_file.readline()
        runtime_limit = int(limit_line) if limit_line.strip() else 0

    if not (1 <= input_count <= 20 and output_count >= 1
            and len(rows) == 1 << input_count):
        raise ValueError('invalid input dimensions or truth table')
    if any(len(row) != output_count or any(bit not in (48, 49) for bit in row)
           for row in rows):
        raise ValueError('invalid truth table bits')

    circuit = Circuit(input_count, gate_costs, target_delay)
    outputs = []
    for column in range(output_count):
        level = [circuit.one if row[column] == 49 else 0 for row in rows]
        # Adjacent entries differ first in the least significant input.
        for variable in range(input_count, 0, -1):
            level = [circuit.select(variable, level[i], level[i + 1])
                     for i in range(0, len(level), 2)]
        outputs.append(level[0])
    # Compare complete circuits so that sharing and dead gates are accounted for.
    # Prefer meeting the target, then area; otherwise minimize excess delay.
    def rank(candidate, candidate_outputs):
        area, delay = candidate.metrics(candidate_outputs)
        return optimization_rank(area, delay, target_delay)

    baseline = circuit
    best, best_outputs = circuit, outputs
    best_rank = rank(best, best_outputs)
    for operation in ('AND2', 'OR2'):
        # Leave time for output when the case has a tight runtime limit.
        if runtime_limit and (time.monotonic() - started) * 1000 > runtime_limit * 0.45:
            break
        candidate, candidate_outputs = baseline.rewritten(outputs, operation)
        candidate_rank = rank(candidate, candidate_outputs)
        if candidate_rank < best_rank:
            best, best_outputs, best_rank = candidate, candidate_outputs, candidate_rank

    # Unlike the uniform rewrites above, this pass makes a delay-first choice
    # at each gate. Keep the original candidates as fallbacks.
    deadline = started + runtime_limit * 0.00075 if runtime_limit else None
    if deadline is None or time.monotonic() < deadline:
        try:
            candidate, candidate_outputs = baseline.delay_optimized(outputs, deadline)
        except TimeoutError:
            pass
        else:
            candidate_rank = rank(candidate, candidate_outputs)
            if candidate_rank < best_rank:
                best, best_outputs = candidate, candidate_outputs
    best.write(output_path, best_outputs)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: stage1.py INPUT OUTPUT')
    try:
        synthesize(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as error:
        sys.exit(str(error))
