

## Requirements

- Python 3, available as `python3` on Ubuntu.
- No third-party packages are required.
- The Python source does not need to be compiled.

## Run on Ubuntu

From the directory containing `stage1.py`, first make the script executable:

```bash
chmod +x stage1.py
```

Run the script with an input file path and an output file path:

```bash
./stage1.py <input_path> <output_path>
```

For example:

```bash
./stage1.py stage1/case_001.txt output.txt
```

Alternatively, run it directly with Python:

```bash
python3 stage1.py stage1/case_001.txt output.txt
```

Each invocation reads one input file and writes one output file to the specified
path. Run the program separately for each input file. Preserve the script's
Unix-style line endings when transferring it to Ubuntu.
