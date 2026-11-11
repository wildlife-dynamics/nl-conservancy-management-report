"""Make `python -m ruff` work when only the ruff BINARY is installed.

wt-compiler 0.8.3 formats every generated file with

    subprocess.check_output([sys.executable, "-m", "ruff", "format", "-s", "-"],
                            input=..., encoding="utf-8")

(see wt_compiler/formatting.py), but its conda recipe depends on
`ruff >=0.1.0`, which resolves to conda-forge's ruff -- a binary-only package
whose entire file manifest is bin/ruff plus three shell completions. There is
no python module, so the call the compiler makes cannot be satisfied by the
dependency the compiler declares, and compilation fails with

    .../bin/python3.15: No module named ruff

This package is put on PYTHONPATH by `[activation.env]` in pixi.toml and does
the one thing the real module would: hand argv and stdin to the binary.

`os.execvp` replaces this process, so stdin, stdout, stderr and the exit code
pass straight through -- which matters, because the compiler pipes the
unformatted source in on stdin and reads the formatted source back out.

DELETE THIS SHIM when wt-compiler either ships the PyPI ruff or calls the
binary directly. It is a workaround, not a design.
"""

import os
import shutil
import sys

exe = shutil.which("ruff")
if exe is None:
    sys.exit(
        "ruff shim: no `ruff` executable on PATH.\n"
        "This shim exists because wt-compiler calls `python -m ruff` while "
        "conda-forge's ruff package ships only a binary. If the binary is "
        "gone too, the environment is incomplete -- run `pixi install`."
    )

os.execvp(exe, ["ruff", *sys.argv[1:]])
