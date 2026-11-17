# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Read a notebook as one Python source, stdlib only.

`read_source()` renders a `.ipynb` in jupytext's percent format: each cell starts
with `# %%` (code) or `# %% [markdown]` (markdown, commented out). IPython magics
and shell escapes are replaced by `pass  # magic` so the result parses as Python.
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NOTEBOOKS = REPO / "notebooks"


def _code(src):
    out = []
    for line in src.split("\n"):
        if line.lstrip().startswith(("%", "!", "?")):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}pass  # magic")
        else:
            out.append(line)
    return "\n".join(out)


def _markdown(src):
    return "\n".join(f"# {line}" if line else "#" for line in src.split("\n"))


def read_source(path):
    """The notebook at `path` as percent-format Python. Non-.ipynb files are read as-is."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".ipynb":
        return text
    parts = []
    for cell in json.loads(text).get("cells", []):
        src = "".join(cell.get("source", []))
        if cell.get("cell_type") == "code":
            parts.append("# %%\n" + _code(src))
        elif cell.get("cell_type") == "markdown":
            parts.append("# %% [markdown]\n" + _markdown(src))
    return "\n\n".join(parts) + "\n"
