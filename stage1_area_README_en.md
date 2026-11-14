# Build and run

Compile on Ubuntu using a C++17 compiler:

```sh
g++ -std=c++17 -O2 -DNDEBUG stage1_area_new.cpp -o stage1_area
```

Run with an input file path and an output file path:

```sh
./stage1_area stage1/case_001.txt circuit.txt
```

The program writes the circuit to the output path and exits. To run the provided evaluator:

```sh
./evaluator ./stage1_area stage1
# Or evaluate one case:
./evaluator ./stage1_area stage1/case_001.txt
```
