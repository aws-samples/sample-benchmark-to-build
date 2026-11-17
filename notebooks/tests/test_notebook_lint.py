# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Static health checks for the notebooks: no kernel, no AWS, stdlib only.

    python3 -m unittest discover -s notebooks/tests -p 'test_notebook_lint.py'

1. Undefined names: any name read at module level but bound nowhere in the
   notebook, which would only fail as a NameError partway through a paid run.
2. Cell compilation: every code cell compiles as stored, which catches literal
   line-separator characters (e.g. U+2028) that nbformat splits on.
3. Cell order: a name must be bound in an earlier cell than its first
   module-level use. Names used inside function bodies are exempt.
"""

import ast
import builtins
import unittest
from pathlib import Path

from notebook_source import NOTEBOOKS, read_source

# Every notebook in the module flow. Add new modules here.
NOTEBOOK_FILES = (
    "Module-1-Build-Dataset.ipynb",
    "Module-2-Evaluation.ipynb",
    "Module-4-Fine-Tune-Results.ipynb",
    "Module-5-RAG.ipynb",
    "Module-6-Agentic-Search.ipynb",
)

# Names the Jupyter/IPython runtime provides that a static read cannot see.
RUNTIME_PROVIDED = {"get_ipython", "__file__", "__name__", "display", "In", "Out"}

# Line breaks to `str.splitlines()` (which nbformat uses) but not to split("\n").
# Write them as escape sequences in notebook source.
LINE_SPLITTERS = {
    "\x0b": "VERTICAL TAB", "\x0c": "FORM FEED", "\x1c": "FILE SEPARATOR",
    "\x1d": "GROUP SEPARATOR", "\x1e": "RECORD SEPARATOR", "\x85": "NEXT LINE",
    "\u2028": "LINE SEPARATOR", "\u2029": "PARAGRAPH SEPARATOR",
}


def _bound_names(tree):
    """Every name bound anywhere in the module: assignment, def, import, loop, etc."""
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.For, ast.AsyncFor)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                bound |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if isinstance(node.target, ast.Name):
                bound.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.add(node.name)
            a = node.args
            bound |= {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
            if a.vararg:
                bound.add(a.vararg.arg)
            if a.kwarg:
                bound.add(a.kwarg.arg)
        elif isinstance(node, ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            bound |= {(al.asname or al.name).split(".")[0] for al in node.names}
        elif isinstance(node, ast.ImportFrom):
            bound |= {al.asname or al.name for al in node.names}
        elif isinstance(node, ast.Lambda):
            a = node.args
            bound |= {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
        elif isinstance(node, ast.comprehension):
            bound |= {x.id for x in ast.walk(node.target) if isinstance(x, ast.Name)}
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.With) or isinstance(node, ast.AsyncWith):
            for item in node.items:
                if item.optional_vars:
                    bound |= {x.id for x in ast.walk(item.optional_vars)
                              if isinstance(x, ast.Name)}
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            bound |= set(node.names)
    return bound


def undefined_names(path):
    """{name: first line it is read on} for names read but never bound."""
    tree = ast.parse(read_source(path), filename=str(path))
    bound = _bound_names(tree)
    safe = set(dir(builtins)) | RUNTIME_PROVIDED | bound
    missing = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in safe:
                missing.setdefault(node.id, node.lineno)
    return missing


class TestNotebookNames(unittest.TestCase):
    def test_every_notebook_defines_every_name_it_uses(self):
        problems = {}
        for name in NOTEBOOK_FILES:
            path = NOTEBOOKS / name
            if not path.is_file():
                continue
            missing = undefined_names(path)
            if missing:
                problems[name] = missing
        self.assertEqual(
            problems, {},
            "Names read but never defined — these are NameErrors waiting for a "
            "user:\n" + "\n".join(
                f"  {nb}: " + ", ".join(f"{k} (line {v})" for k, v in sorted(m.items()))
                for nb, m in problems.items()
            ),
        )

    def test_all_expected_notebooks_were_checked(self):
        # A typo'd filename would make the test above vacuously pass.
        found = [n for n in NOTEBOOK_FILES if (NOTEBOOKS / n).is_file()]
        self.assertEqual(sorted(found), sorted(NOTEBOOK_FILES),
                         f"missing: {set(NOTEBOOK_FILES) - set(found)}")

    def test_the_checker_actually_detects_a_missing_name(self):
        # Guard the guard: a broken detector would silently pass everything.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "broken.py"
            p.write_text("x = 1\nprint(x + MISSING_CONSTANT)\n", encoding="utf-8")
            self.assertIn("MISSING_CONSTANT", undefined_names(p))

    def test_the_checker_does_not_flag_legitimate_bindings(self):
        import tempfile
        src = (
            "import json\n"
            "from pathlib import Path as P\n"
            "A = 1\n"
            "def f(b, *args, c=2, **kw):\n"
            "    with open('x') as fh:\n"
            "        for i in range(b):\n"
            "            try:\n"
            "                d = [y for y in args if y]\n"
            "            except ValueError as e:\n"
            "                print(e, d, i, fh, c, kw, json, P, A)\n"
            "    return (z := b + 1) and z\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ok.py"
            p.write_text(src, encoding="utf-8")
            self.assertEqual(undefined_names(p), {})


class TestNotebookSourceIsConversionSafe(unittest.TestCase):
    """No literal character that `splitlines()` would break a string literal on."""

    def test_no_notebook_contains_a_literal_line_splitter(self):
        problems = {}
        for name in NOTEBOOK_FILES:
            path = NOTEBOOKS / name
            if not path.is_file():
                continue
            text = read_source(path)
            for i, line in enumerate(text.split("\n"), 1):
                for ch, label in LINE_SPLITTERS.items():
                    if ch in line:
                        problems.setdefault(name, []).append(
                            f"line {i}: literal {label} (U+{ord(ch):04X})")
        self.assertEqual(
            problems, {},
            "Literal line-splitting characters in notebook source. nbformat writes "
            "cell source with splitlines(), so these break the cell during .ipynb "
            "conversion. Write them as escapes instead:\n" + "\n".join(
                f"  {k}: {'; '.join(v)}" for k, v in problems.items()),
        )

    def test_splitlines_agrees_with_newline_splitting(self):
        for name in NOTEBOOK_FILES:
            path = NOTEBOOKS / name
            if not path.is_file():
                continue
            text = read_source(path)
            expected = len(text.split("\n")) - (1 if text.endswith("\n") else 0)
            self.assertEqual(
                len(text.splitlines()), expected,
                f"{name}: splitlines() and split('\\n') disagree — a hidden line "
                f"separator is present",
            )


class TestGeneratedNotebooksCompile(unittest.TestCase):
    """Every code cell of every .ipynb must be valid Python.

    This is the check that catches breakage introduced by jupytext/nbformat rather
    than present in the source.
    """

    @staticmethod
    def _strip_magics(source):
        """Drop IPython magics and shell escapes, which are not valid Python."""
        out = []
        for line in source.split("\n"):
            stripped = line.lstrip()
            if stripped.startswith(("%", "!", "?")):
                out.append("pass  # magic")
            else:
                out.append(line)
        return "\n".join(out)

    def test_every_code_cell_compiles(self):
        import json

        problems = []
        checked = 0
        for name in NOTEBOOK_FILES:
            ipynb = NOTEBOOKS / name
            if not ipynb.is_file():
                continue
            nb = json.loads(ipynb.read_text(encoding="utf-8"))
            for idx, cell in enumerate(nb.get("cells", [])):
                if cell.get("cell_type") != "code":
                    continue
                src = "".join(cell.get("source", []))
                checked += 1
                try:
                    compile(self._strip_magics(src), f"{ipynb.name}:cell{idx}", "exec")
                except SyntaxError as e:
                    problems.append(f"{ipynb.name} cell {idx}: {e.msg} (line {e.lineno})")
        self.assertEqual(problems, [], "Code cells that do not compile:\n" +
                         "\n".join(f"  {p}" for p in problems))
        self.assertGreater(checked, 0, "no code cells were checked")

    def test_the_compile_check_detects_a_broken_cell(self):
        # Guard the guard with a literal U+2028 inside a string.
        with self.assertRaises(SyntaxError):
            # A literal U+2028 inside a string literal, as nbformat would emit it
            # after splitting: the quote never closes on the first line.
            compile('x = "[ \u2028', "<test>", "exec")


class TestCellOrder(unittest.TestCase):
    """Module-level names must be bound in an earlier or the same code cell."""

    @staticmethod
    def _code_cells(path):
        cells, current, kind = [], [], None
        for line in read_source(path).split("\n"):
            if line.startswith("# %%"):
                if kind is not None:
                    cells.append((kind, "\n".join(current)))
                kind = "md" if line.startswith("# %% [markdown]") else "code"
                current = []
            else:
                current.append(line)
        if kind is not None:
            cells.append((kind, "\n".join(current)))
        return [src for k, src in cells if k == "code"]

    @staticmethod
    def _module_level_loads(tree):
        """Name loads NOT inside a function/class/lambda — i.e. run immediately."""
        deferred = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Lambda)):
                for inner in ast.walk(node):
                    deferred.add(id(inner))
        loads = {}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                    and id(node) not in deferred):
                loads.setdefault(node.id, node.lineno)
        return loads

    def test_no_module_level_use_before_definition(self):
        problems = {}
        for name in NOTEBOOK_FILES:
            path = NOTEBOOKS / name
            if not path.is_file():
                continue
            bound = set(dir(builtins)) | RUNTIME_PROVIDED
            for idx, src in enumerate(self._code_cells(path)):
                try:
                    tree = ast.parse(src)
                except SyntaxError:
                    continue
                # Everything this cell binds counts as available within the cell.
                cell_bound = _bound_names(tree)
                for used, line in self._module_level_loads(tree).items():
                    if used not in bound and used not in cell_bound:
                        problems.setdefault(name, []).append(
                            f"code cell {idx}: {used} used before any cell defines it")
                bound |= cell_bound
        self.assertEqual(
            problems, {},
            "Module-level names used before a cell defines them — NameErrors for "
            "anyone running top to bottom:\n" + "\n".join(
                f"  {k}: " + "; ".join(v) for k, v in problems.items()),
        )

    def test_the_order_check_detects_a_reversed_notebook(self):
        # Guard the guard: a definition AFTER its module-level use must be caught.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "reversed.py"
            p.write_text("# %%\nresult = helper()\n\n# %%\ndef helper():\n"
                         "    return 1\n", encoding="utf-8")
            cells = self._code_cells(p)
            self.assertEqual(len(cells), 2)
            tree = ast.parse(cells[0])
            self.assertIn("helper", self._module_level_loads(tree))
            self.assertNotIn("helper", _bound_names(tree))

    def test_a_function_body_may_reference_a_later_cell(self):
        # Legal and common: the body resolves at call time, not definition time.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "deferred.py"
            p.write_text("# %%\ndef f():\n    return LATER\n\n# %%\nLATER = 1\n",
                         encoding="utf-8")
            tree = ast.parse(self._code_cells(p)[0])
            self.assertNotIn("LATER", self._module_level_loads(tree))


if __name__ == "__main__":
    unittest.main(verbosity=2)
