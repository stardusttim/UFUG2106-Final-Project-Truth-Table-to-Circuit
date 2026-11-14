#include <algorithm>
#include <chrono>
#include <memory>
#include <limits>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using namespace std;

enum class GateType { And, Or, Not };

struct GateKey {
    GateType type;
    int a, b;
    bool operator==(const GateKey& other) const {
        return type == other.type && a == other.a && b == other.b;
    }
};

struct GateHash {
    size_t operator()(const GateKey& key) const {
        size_t hash = static_cast<size_t>(key.type);
        hash = hash * 1000003u + key.a;
        return hash * 1000003u + key.b;
    }
};

struct Gate { GateType type; int a, b; };
struct SignalPair { int positive, negative; };

class CircuitBuilder {
public:
    CircuitBuilder(int inputs, long long and_delay, long long or_delay, long long not_delay,
                   long long and_area, long long or_area, long long not_area, int slack)
        : input_count_(inputs), and_delay_(and_delay), or_delay_(or_delay),
          not_delay_(not_delay), and_area_(and_area), or_area_(or_area), not_area_(not_area),
          slack_(slack), arrival_(inputs + 1, 0), estimated_area_(inputs + 1, 0),
          input_negations_(inputs + 1, -1) {
        one_ = make_gate(GateType::Not, 0, 0);
    }

    int build_output(const vector<unsigned char>& truth_values) {
        vector<SignalPair> current(truth_values.size());
        for (size_t i = 0; i < truth_values.size(); ++i) {
            current[i] = truth_values[i] ? SignalPair{one_, 0} : SignalPair{0, one_};
        }

        // Adjacent rows differ in the least significant remaining variable.
        int variable = input_count_;
        while (variable >= 1) {
            const int x = variable;
            const int not_x = input_negation(x);
            if (variable == 1) {
                const size_t count = current.size() / 2;
                for (size_t i = 0; i < count; ++i)
                    current[i] = combine(x, not_x, current[2 * i], current[2 * i + 1]);
                current.resize(count);
                --variable;
                continue;
            }

            const int y = variable - 1;
            const int not_y = input_negation(y);
            // Decode the two variables once; structural hashing shares these signals.
            const int select[4] = {and_gate(not_y, not_x), and_gate(not_y, x),
                                   and_gate(y, not_x), and_gate(y, x)};
            const size_t count = current.size() / 4;
            for (size_t i = 0; i < count; ++i) {
                const SignalPair values[4] = {current[4 * i], current[4 * i + 1],
                                               current[4 * i + 2], current[4 * i + 3]};
                SignalPair sequential = combine(y, not_y,
                    combine(x, not_x, values[0], values[1]),
                    combine(x, not_x, values[2], values[3]));
                // Compare two levels of multiplexers with a parallel four-way expansion.
                int positive = or_tree(and_gate(select[0], values[0].positive),
                                       and_gate(select[1], values[1].positive),
                                       and_gate(select[2], values[2].positive),
                                       and_gate(select[3], values[3].positive));
                int negative = or_tree(and_gate(select[0], values[0].negative),
                                       and_gate(select[1], values[1].negative),
                                       and_gate(select[2], values[2].negative),
                                       and_gate(select[3], values[3].negative));
                positive = faster(sequential.positive, positive);
                negative = faster(sequential.negative, negative);
                current[i] = {faster(positive, invert(negative)),
                              faster(negative, invert(positive))};
            }
            current.resize(count);
            variable -= 2;
        }
        return current[0].positive;
    }

    pair<long long, long long> measure(const vector<int>& outputs) const {
        vector<char> used(gates_.size(), false);
        vector<int> pending(outputs.begin(), outputs.end());
        long long area = 0, delay = 0;
        for (int signal : outputs) delay = max(delay, arrival_[signal]);
        while (!pending.empty()) {
            int signal = pending.back(); pending.pop_back();
            if (signal <= input_count_) continue;
            size_t index = signal - input_count_ - 1;
            if (used[index]) continue;
            used[index] = true;
            const Gate& g = gates_[index];
            area += g.type == GateType::And ? and_area_ : g.type == GateType::Or ? or_area_ : not_area_;
            pending.push_back(g.a);
            if (g.type != GateType::Not) pending.push_back(g.b);
        }
        return {area, delay};
    }

    void write(ostream& out, const vector<int>& outputs) const {
        // Retain only gates reachable from the outputs, then renumber topologically.
        vector<char> used(gates_.size(), false);
        vector<int> pending;
        for (int signal : outputs)
            if (signal > input_count_) pending.push_back(signal);
        while (!pending.empty()) {
            int signal = pending.back();
            pending.pop_back();
            size_t index = signal - input_count_ - 1;
            if (used[index]) continue;
            used[index] = true;
            const Gate& gate = gates_[index];
            if (gate.a > input_count_) pending.push_back(gate.a);
            if (gate.type != GateType::Not && gate.b > input_count_) pending.push_back(gate.b);
        }

        vector<int> remap(input_count_ + 1 + gates_.size());
        for (int i = 0; i <= input_count_; ++i) remap[i] = i;
        int next = input_count_ + 1;
        for (size_t i = 0; i < gates_.size(); ++i) {
            if (!used[i]) continue;
            const Gate& gate = gates_[i];
            remap[input_count_ + 1 + i] = next;
            const char* name = gate.type == GateType::And ? "AND2" :
                               gate.type == GateType::Or ? "OR2" : "NOT";
            out << next++ << ' ' << name << ' ' << remap[gate.a];
            if (gate.type != GateType::Not) out << ' ' << remap[gate.b];
            out << '\n';
        }
        for (size_t i = 0; i < outputs.size(); ++i) {
            if (i) out << ' ';
            out << remap[outputs[i]];
        }
        out << '\n';
    }

private:
    int input_count_, one_;
    long long and_delay_, or_delay_, not_delay_;
    long long and_area_, or_area_, not_area_;
    int slack_;
    vector<Gate> gates_;
    unordered_map<GateKey, int, GateHash> gate_cache_;
    vector<long long> arrival_;
    vector<double> estimated_area_;
    vector<int> input_negations_;

    int make_gate(GateType type, int a, int b) {
        if (type != GateType::Not && a > b) swap(a, b);
        GateKey key{type, a, b};
        auto found = gate_cache_.find(key);
        if (found != gate_cache_.end()) return found->second;
        int id = input_count_ + 1 + static_cast<int>(gates_.size());
        gates_.push_back({type, a, b});
        long long delay = type == GateType::And ? and_delay_ :
                          type == GateType::Or ? or_delay_ : not_delay_;
        arrival_.push_back(max(arrival_[a], type == GateType::Not ? 0LL : arrival_[b]) + delay);
        double area = type == GateType::And ? and_area_ : type == GateType::Or ? or_area_ : not_area_;
        // This tree cost is only a ranking heuristic; final area counts shared gates once.
        estimated_area_.push_back(area + estimated_area_[a] +
                                  (type == GateType::Not ? 0 : estimated_area_[b]));
        gate_cache_.emplace(key, id);
        return id;
    }

    int invert(int signal) {
        if (signal == 0) return one_;
        if (signal == one_) return 0;
        if (signal > input_count_ && gates_[signal - input_count_ - 1].type == GateType::Not)
            return gates_[signal - input_count_ - 1].a;
        return make_gate(GateType::Not, signal, 0);
    }

    int input_negation(int input) {
        if (input_negations_[input] < 0) input_negations_[input] = invert(input);
        return input_negations_[input];
    }

    int and_gate(int a, int b) {
        if (a == 0 || b == 0) return 0;
        if (a == one_) return b;
        if (b == one_ || a == b) return a;
        return make_gate(GateType::And, a, b);
    }

    int or_gate(int a, int b) {
        if (a == one_ || b == one_) return one_;
        if (a == 0) return b;
        if (b == 0 || a == b) return a;
        int direct = make_gate(GateType::Or, a, b);
        // De Morgan's law may be faster when OR gates have a high delay.
        if (and_delay_ + not_delay_ < or_delay_ ||
            (slack_ >= 0 && and_area_ + 2 * not_area_ < or_area_)) {
            int alternative = invert(and_gate(invert(a), invert(b)));
            if (slack_ < 0) {
                if (arrival_[alternative] < arrival_[direct]) return alternative;
            } else return faster(direct, alternative);
        }
        return direct;
    }

    int faster(int a, int b) const {
        if (slack_ < 0) return arrival_[a] <= arrival_[b] ? a : b;
        if (arrival_[a] + slack_ < arrival_[b]) return a;
        if (arrival_[b] + slack_ < arrival_[a]) return b;
        if (estimated_area_[a] != estimated_area_[b])
            return estimated_area_[a] < estimated_area_[b] ? a : b;
        return arrival_[a] <= arrival_[b] ? a : b;
    }

    int mux(int x, int not_x, int low, int high) {
        if (low == high) return low;
        // Equivalent sum-of-products and product-of-sums Shannon expansions.
        int sop = or_gate(and_gate(not_x, low), and_gate(x, high));
        int pos = and_gate(or_gate(x, low), or_gate(not_x, high));
        return faster(sop, pos);
    }

    SignalPair combine(int x, int not_x, SignalPair low, SignalPair high) {
        int positive = mux(x, not_x, low.positive, high.positive);
        int negative = mux(x, not_x, low.negative, high.negative);
        int from_negative = invert(negative);
        int from_positive = invert(positive);
        return {faster(positive, from_negative), faster(negative, from_positive)};
    }

    int or_tree(int a, int b, int c, int d) {
        // Check all three balanced pairings to account for different arrival times.
        int first = or_gate(or_gate(a, b), or_gate(c, d));
        int second = or_gate(or_gate(a, c), or_gate(b, d));
        int third = or_gate(or_gate(a, d), or_gate(b, c));
        return faster(faster(first, second), third);
    }
};

int main(int argc, char** argv) {
    try {
        const auto start = chrono::steady_clock::now();
        if (argc != 3) throw runtime_error("usage: program input output");
        ifstream input(argv[1]);
        if (!input) throw runtime_error("cannot open input");
        int input_count, output_count;
        input >> input_count >> output_count;
        if (!input || input_count < 1 || input_count > 20 || output_count < 1)
            throw runtime_error("invalid dimensions");
        const size_t rows = size_t(1) << input_count;
        vector<vector<unsigned char>> truth(output_count, vector<unsigned char>(rows));
        string bits;
        for (size_t row = 0; row < rows; ++row) {
            if (!(input >> bits) || bits.size() != static_cast<size_t>(output_count))
                throw runtime_error("invalid truth table");
            for (int output = 0; output < output_count; ++output) {
                if (bits[output] != '0' && bits[output] != '1') throw runtime_error("invalid bit");
                truth[output][row] = bits[output] - '0';
            }
        }
        long long and_area, and_delay, or_area, or_delay, not_area, not_delay, target_delay;
        if (!(input >> and_area >> and_delay >> or_area >> or_delay >> not_area >> not_delay >> target_delay))
            throw runtime_error("missing costs");

        long long runtime_limit = 0, ram_limit = 0;
        input >> runtime_limit >> ram_limit;
        // Retain the fast reference as a safe fallback; only accept a smaller
        // circuit when its measured critical path meets the target.
        unique_ptr<CircuitBuilder> best;
        vector<int> best_outputs;
        long long best_area = 0, best_delay = 0;
        double first_duration = 0;
        const int options[] = {-1, 0, 1, 2, 4, 8};
        for (int slack : options) {
            double elapsed = chrono::duration<double, milli>(chrono::steady_clock::now() - start).count();
            // Allow a generous reserve for variations in candidate cost and output I/O.
            if (best && runtime_limit > 0 && elapsed + 2.5 * first_duration + 30 >= runtime_limit) break;
            // The reference is still available when a memory limit is specified.
            if (best && ram_limit > 0) break;
            auto attempt_start = chrono::steady_clock::now();
            auto candidate = make_unique<CircuitBuilder>(input_count, and_delay, or_delay, not_delay,
                                                          and_area, or_area, not_area, slack);
            vector<int> outputs;
            for (const auto& values : truth) outputs.push_back(candidate->build_output(values));
            auto [area, delay] = candidate->measure(outputs);
            if (!best || (delay <= target_delay && (best_delay > target_delay || area < best_area)) ||
                (best_delay > target_delay && delay < best_delay)) {
                best = move(candidate);
                best_outputs = move(outputs);
                best_area = area;
                best_delay = delay;
            }
            if (slack == -1)
                first_duration = chrono::duration<double, milli>(chrono::steady_clock::now() - attempt_start).count();
        }
        ofstream output(argv[2]);
        if (!output) throw runtime_error("cannot open output");
        best->write(output, best_outputs);
        if (!output) throw runtime_error("write failed");
    } catch (const exception& error) {
        cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
