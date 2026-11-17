# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Tests for the helper code defined inside the notebooks.

Stdlib only, no AWS, no network:
    python3 -m unittest discover -s notebooks/tests -p 'test_notebook_helpers.py'

The functions under test (`normalise`, `load_corpus`, `pick_acts`, `find_section`,
`search_text`, `read_around`) are defined in `Module-6-Agentic-Search.ipynb` so
readers see them, so this file extracts and executes those cells. They must stay
free of AWS dependencies.

TestLiveCorpus runs against the committed legislation and checks the provisions
Module 6 relies on (s180(1) and the s1043A penalty row) are still reachable.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from notebook_source import NOTEBOOKS, REPO, read_source

NOTEBOOK = NOTEBOOKS / "Module-6-Agentic-Search.ipynb"
# Every notebook that scores against the sovereign rubric. All three must agree.
RUBRIC_NOTEBOOKS = ("Module-2-Evaluation.ipynb", "Module-5-RAG.ipynb", "Module-6-Agentic-Search.ipynb")
CORPUS_DIR = REPO / "datasets" / "legal" / "corpus" / "text"

NBSP = "\u00a0"
NNBSP = "\u202f"


def _stub_inspect_ai():
    """Register inert inspect_ai modules so the Step 2b cell can be exec'd.

    That cell imports inspect_ai and calls get_model() at the bottom. We only want
    the pure helpers it defines (the rubric, the prompt builder, the paired test),
    so the heavy dependency is stubbed rather than installed — which also keeps
    this suite runnable with nothing but the standard library.
    """
    import sys
    import types as _t

    made = []
    specs = {
        "inspect_ai": ("Task", "task", "eval"),
        "inspect_ai.dataset": ("FieldSpec", "json_dataset"),
        "inspect_ai.model": ("get_model", "GenerateConfig"),
        "inspect_ai.solver": ("generate", "solver", "Generate", "TaskState"),
        "inspect_ai.scorer": ("model_graded_qa",),
    }
    for name, attrs in specs.items():
        if name in sys.modules:
            continue
        mod = _t.ModuleType(name)
        for a in attrs:
            setattr(mod, a, lambda *args, **kwargs: None)
        sys.modules[name] = mod
        made.append(name)
    return made


class _NoS3:
    """Enough of an S3 client for the cell's trailing load_cell_results() call."""

    def list_objects_v2(self, **kw):
        return {"Contents": [], "IsTruncated": False}


def _load_notebook_functions():
    """Exec the Module 6 cells that define the rubric, helpers and retrieval tools."""
    src = read_source(NOTEBOOK)
    cells, current = [], []
    for line in src.split("\n"):
        if line.startswith("# %%"):
            cells.append("\n".join(current))
            current = [] if line.startswith("# %% [markdown]") else ["#__code__"]
        elif current:
            current.append(line)
    cells.append("\n".join(current))
    code_cells = [c for c in cells if c.startswith("#__code__")]

    # Stub inspect_ai and AWS so the harness cell defines its pure helpers.
    ns = {
        "Path": Path, "CORPUS_DIR": None, "__name__": "module5_cells",
        "EVAL_KEY": "legal/eval-legal-au.jsonl", "DATASET_BUCKET": "ds",
        "RESULTS_BUCKET": "rs", "CELL_RESULTS_PREFIX": "results/cells/",
        "NUM_EVAL_RECORDS": 50, "MAX_CONNECTIONS": 8,
        # Defined in the config cell, which is not exec'd here.
        # test_notebook_lint.py checks the notebook really defines it.
        "CORPUS_PREFIX": "legal/corpus/",
        "MODEL_UNDER_TEST": "bedrock/x", "MODEL_LABEL": "base",
        "s3": _NoS3(), "datetime": __import__("datetime").datetime,
        "timezone": __import__("datetime").timezone, "json": __import__("json"),
    }
    # Cells are found by the functions they define, not by index, so cells can be
    # reordered. Every function listed must be found.
    wanted = (
        "def normalise(",
        "def build_index(",
        "def fetch_corpus_from_s3(",
        "def pick_acts(",
        "def find_section(",
        "def search_text(",
        "def read_around(",
        "def build_grounded_prompt(",
        "def as_span(",
        "def mcnemar_exact(",
        "def paired_compare(",
    )
    stubbed = _stub_inspect_ai()
    seen = set()
    try:
        for cell in code_cells:
            hits = [w for w in wanted if w in cell]
            if hits:
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(cell, str(NOTEBOOK), "exec"), ns)
                seen.update(hits)
    finally:
        import sys
        for name in stubbed:
            sys.modules.pop(name, None)
    absent = [w for w in wanted if w not in seen]
    if absent:
        raise RuntimeError(
            f"These definitions were not found in any code cell of "
            f"{NOTEBOOK.name}: {absent}. Either the function was renamed or "
            "removed, or a cell split left it somewhere this extractor does "
            "not reach."
        )
    return ns


M5 = _load_notebook_functions()
build_index = M5["build_index"]
fetch_corpus_from_s3 = M5["fetch_corpus_from_s3"]
mcnemar_exact = M5["mcnemar_exact"]
paired_compare = M5["paired_compare"]
build_grounded_prompt = M5["build_grounded_prompt"]
as_span = M5["as_span"]
normalise = M5["normalise"]
pick_acts = M5["pick_acts"]
find_section = M5["find_section"]
search_text = M5["search_text"]
read_around = M5["read_around"]


class TestExtraction(unittest.TestCase):
    """Guard the extraction itself, so a silent no-op cannot look like a pass."""

    def test_all_six_functions_were_found(self):
        for name in ("normalise", "build_index", "fetch_corpus_from_s3", "pick_acts",
                     "find_section", "search_text", "read_around", "mcnemar_exact",
                     "paired_compare", "build_grounded_prompt", "as_span"):
            self.assertTrue(callable(M5[name]), f"{name} not defined in the notebook")

    def test_every_tool_the_system_prompt_names_actually_exists(self):
        """The prompt tells the agent which tools to call. They must be real.

        Strands names a tool after its Python identifier unless `name=` is set. The
        wrappers are called `find_section_tool` etc., so without `name=` every call
        to "find_section" would fail as an unknown tool.
        """
        import re

        src = read_source(NOTEBOOK)
        exposed = set(re.findall(r'@tool\(name="(\w+)"\)', src))
        # A tool whose Python name already matches needs no name= override.
        exposed |= {m for m in re.findall(r"@tool\n    def (\w+)\(", src)}
        prompt = re.search(r'AGENT_SYSTEM_PROMPT = """(.*?)"""', src, re.S).group(1)
        promised = set(re.findall(r"^- (\w+)\(", prompt, re.M))
        self.assertEqual(
            promised, exposed,
            f"prompt names tools that do not exist: {promised - exposed}; "
            f"tools not mentioned in the prompt: {exposed - promised}",
        )

    def test_the_notebook_defines_them_not_a_library(self):
        self.assertNotIn("corpus_tools", read_source(NOTEBOOK))


class TestRubricIdentity(unittest.TestCase):
    """The rubric must be the same text in every notebook, or no score is comparable.

    Each notebook inlines its own copy so it stands alone; this catches drift
    between the copies.
    """

    @staticmethod
    def _rubric(filename):
        import re
        src = read_source(NOTEBOOKS / filename)
        m = re.search(r'LEGAL_INSTRUCTIONS = """(.*?)"""', src, re.S)
        return m.group(1) if m else None

    def test_all_scoring_notebooks_use_the_same_rubric(self):
        found = {nb: self._rubric(nb) for nb in RUBRIC_NOTEBOOKS}
        missing = [nb for nb, r in found.items() if r is None]
        self.assertEqual(missing, [], f"LEGAL_INSTRUCTIONS not found in {missing}")
        reference = found[RUBRIC_NOTEBOOKS[0]]
        for nb, rubric in found.items():
            self.assertEqual(
                rubric, reference,
                f"{nb}'s rubric differs from {RUBRIC_NOTEBOOKS[0]}'s. Every "
                f"cross-module comparison is invalid until they match again.",
            )

    def test_rubric_still_demands_all_three_criteria(self):
        # These three conditions make it a sovereign benchmark, not a generic one.
        r = self._rubric("Module-6-Agentic-Search.ipynb")
        self.assertIn("correct legal conclusion", r)
        self.assertIn("cites the correct legislation or section", r)
        self.assertIn("specific to Australian law", r)
        self.assertIn('"GRADE: C"', r)

    def test_every_notebook_pins_the_same_judge(self):
        for nb in RUBRIC_NOTEBOOKS:
            src = read_source(NOTEBOOKS / nb)
            self.assertIn("us.anthropic.claude-sonnet-4-6", src, nb)

    def test_every_notebook_pins_the_judge_temperature(self):
        """Same judge *id* is not the same judge. Config counts too.

        An unpinned judge re-decides borderline answers on every run, adding
        run-to-run variance larger than the effects being compared.
        """
        import re
        for nb in RUBRIC_NOTEBOOKS:
            src = read_source(NOTEBOOKS / nb)
            m = re.search(r"grader\s*=\s*get_model\((.*?)\)\n", src, re.S)
            self.assertIsNotNone(m, f"{nb}: no `grader = get_model(...)` found")
            call = m.group(1)
            self.assertIn(
                "GenerateConfig(temperature=0.0)",
                call.replace(" ", "").replace("\n", ""),
                f"{nb}: the judge is not pinned to temperature 0. If this is "
                f"deliberate (e.g. a judge model that rejects the parameter), "
                f"document why and update this test — do not just "
                f"delete the pin, because every score then carries judge noise.",
            )

    def test_every_notebook_pins_the_answerer_temperature(self):
        """The model under test must be pinned too, not just the judge."""
        import re
        for nb in RUBRIC_NOTEBOOKS:
            src = read_source(NOTEBOOKS / nb)
            for call in re.findall(r"inspect_eval\((.*?)\n\s*\)|inspect_eval\((.*?)\)\n",
                                   src, re.S):
                body = (call[0] or call[1])
                self.assertIn(
                    "temperature=0.0", body.replace(" ", ""),
                    f"{nb}: an inspect_eval() call does not pin temperature. "
                    f"Run-to-run answerer drift then sits on top of judge drift.",
                )


class TestGroundedPrompt(unittest.TestCase):
    def test_matches_module_4s_template_byte_for_byte(self):
        # Module 5 builds this prompt inline; the templates must match for agentic
        # and RAG rows to be comparable.
        chunks = [as_span("SEC A text", "a.txt"), as_span("SEC B text", "b.txt")]
        ctx = "\n\n---\n\n".join(c["content"]["text"] for c in chunks)
        expected = ("Use the following Australian legislation extracts to answer the "
                    "question. If they are relevant, cite the specific section.\n\n"
                    f"<legislation>\n{ctx}\n</legislation>\n\n"
                    "Question: Q?")
        self.assertEqual(build_grounded_prompt(chunks, "Q?"), expected)

    def test_as_span_shape_matches_the_knowledge_base(self):
        s = as_span("text", "s3://b/legal/corpus/x.txt")
        self.assertEqual(s["content"]["text"], "text")
        self.assertEqual(s["location"]["s3Location"]["uri"], "s3://b/legal/corpus/x.txt")


class TestMcNemar(unittest.TestCase):
    """Known McNemar exact p-values (n=50)."""

    def test_reranking_step_alone(self):
        self.assertAlmostEqual(mcnemar_exact(12, 4), 0.0768, places=4)

    def test_baseline_to_rag_plus_reranking(self):
        self.assertAlmostEqual(mcnemar_exact(30, 2), 2.46e-07, places=9)

    def test_baseline_to_rag(self):
        self.assertAlmostEqual(mcnemar_exact(22, 2), 3.588e-05, places=7)

    def test_corpus_refresh_regression(self):
        self.assertAlmostEqual(mcnemar_exact(1, 7), 0.0703, places=4)

    def test_no_discordant_items_is_p_one(self):
        self.assertEqual(mcnemar_exact(0, 0), 1.0)

    def test_symmetric_counts_give_p_one(self):
        self.assertEqual(mcnemar_exact(5, 5), 1.0)

    def test_is_symmetric_in_its_arguments(self):
        self.assertEqual(mcnemar_exact(9, 2), mcnemar_exact(2, 9))

    def test_never_exceeds_one(self):
        for f in range(6):
            for b in range(6):
                self.assertLessEqual(mcnemar_exact(f, b), 1.0)


class TestPairedCompare(unittest.TestCase):
    @staticmethod
    def _items(scores):
        return [{"id": i, "category": "x", "score": s} for i, s in enumerate(scores, 1)]

    def test_classifies_every_cell_of_the_table(self):
        r = paired_compare(self._items([0, 1, 1, 0]), self._items([1, 0, 1, 0]))
        self.assertEqual(r["fixed"], ["1"])
        self.assertEqual(r["broken"], ["2"])
        self.assertEqual(r["both_right"], ["3"])
        self.assertEqual(r["both_wrong"], ["4"])
        self.assertEqual(r["n_compared"], 4)
        self.assertEqual(r["delta"], 0.0)

    def test_delta_matches_the_score_difference(self):
        r = paired_compare(self._items([0, 0, 0, 0]), self._items([1, 1, 0, 0]))
        self.assertAlmostEqual(r["delta"], 0.5)

    def test_joins_on_id_not_on_order(self):
        base = [{"id": "a", "score": 0.0}, {"id": "b", "score": 1.0}]
        var = [{"id": "b", "score": 1.0}, {"id": "a", "score": 1.0}]
        r = paired_compare(base, var)
        self.assertEqual(r["fixed"], ["a"])
        self.assertEqual(r["both_right"], ["b"])

    def test_reports_unmatched_ids_rather_than_hiding_them(self):
        # Comparing across different datasets must look like a mistake, not a result.
        r = paired_compare([{"id": "a", "score": 0.0}, {"id": "zz", "score": 0.0}],
                           [{"id": "a", "score": 1.0}, {"id": "yy", "score": 1.0}])
        self.assertEqual(r["n_compared"], 1)
        self.assertEqual(r["n_baseline_only"], 1)
        self.assertEqual(r["n_variant_only"], 1)

    def test_empty_overlap_does_not_divide_by_zero(self):
        r = paired_compare([{"id": "a", "score": 1.0}], [{"id": "b", "score": 1.0}])
        self.assertEqual(r["n_compared"], 0)
        self.assertEqual(r["delta"], 0.0)
        self.assertEqual(r["p_value"], 1.0)

    def test_p_value_is_wired_to_the_counts(self):
        r = paired_compare(self._items([0] * 12 + [1] * 4 + [1] * 34),
                           self._items([1] * 12 + [0] * 4 + [1] * 34))
        self.assertEqual((len(r["fixed"]), len(r["broken"])), (12, 4))
        self.assertAlmostEqual(r["p_value"], 0.0768, places=4)


class TestNormalise(unittest.TestCase):
    def test_collapses_non_breaking_spaces(self):
        # The exact shape the Schedule 3 penalty table uses.
        self.assertEqual(normalise(f"Subsection{NBSP}1043A(1)"), "Subsection 1043A(1)")
        self.assertEqual(normalise(f"Section{NNBSP}1041G"), "Section 1041G")

    def test_collapses_runs_and_strips_per_line(self):
        self.assertEqual(normalise("180  Care   and\tdiligence"), "180 Care and diligence")
        self.assertEqual(normalise("  padded  "), "padded")

    def test_preserves_newlines(self):
        # Line structure is load-bearing: a penalty row is a section on one line and
        # its penalty on the next, and that adjacency is the only link between them.
        self.assertEqual(
            normalise(f"Subsection{NBSP}1043A(1)\n15 years imprisonment"),
            "Subsection 1043A(1)\n15 years imprisonment",
        )

    def test_ungluess_subsection_markers_from_the_following_word(self):
        """The corpus writes "(1)If" 820 times against 101 for "(1) If".

        An agent searching the natural phrasing finds nothing otherwise — which
        reads as missing corpus coverage but is a text-extraction artefact. APP 11
        is the worst case: the Act renders it "11.1If an APP entity holds...".
        """
        self.assertEqual(normalise("(1)If a person"), "(1) If a person")
        self.assertEqual(normalise("11.1If an APP entity"), "11.1 If an APP entity")
        self.assertEqual(normalise("(a)from misuse"), "(a) from misuse")

    def test_leaves_already_spaced_text_alone(self):
        self.assertEqual(normalise("(1) If a person"), "(1) If a person")

    def test_does_not_split_a_bare_cross_reference(self):
        # "subsection (1)" and "section 1043A(1)" must not gain a trailing space
        # that changes how a citation reads.
        self.assertEqual(normalise("subsection (1) does not apply"),
                         "subsection (1) does not apply")
        self.assertEqual(normalise("Subsection 1043A(1)"), "Subsection 1043A(1)")

    def test_blank_lines_survive(self):
        self.assertEqual(normalise("a\n\nb"), "a\n\nb")


class _TmpCorpus(unittest.TestCase):
    """Base class giving each test a small in-memory corpus.

    No filesystem: the retrieval path takes {name: text}, so the tests feed it
    documents directly, as the S3 fetch would.
    """

    FILES = {}

    def setUp(self):
        self.c = build_index(dict(self.FILES))


class TestBuildIndex(_TmpCorpus):
    FILES = {
        "fake-act-2001.txt": "SOURCE: Fake Act 2001 (Cth) | Register ID X | compilation 1\n"
                             "==========\n1 Short title\nThis is the Fake Act.\n",
        "no-header-act.txt": "1 Short title\nBody.\n",
    }

    def test_title_comes_from_source_header(self):
        self.assertEqual(self.c["fake-act-2001"]["title"], "Fake Act 2001 (Cth)")

    def test_title_falls_back_to_slug_without_header(self):
        self.assertEqual(self.c["no-header-act"]["title"], "No Header Act")

    def test_records_character_counts(self):
        self.assertTrue(all(d["chars"] > 0 for d in self.c.values()))


class TestFetchCorpusFromS3(unittest.TestCase):
    """The only I/O in the retrieval path, against a fake S3 client.

    The agent reads the same prefix the knowledge base ingests, so both see
    identical text. These tests pin the paging and the filtering.
    """

    class FakeS3:
        def __init__(self, objects, page_size=None):
            self.objects = objects          # {key: bytes}
            self.page_size = page_size
            self.list_calls = 0

        def list_objects_v2(self, **kw):
            self.list_calls += 1
            keys = sorted(k for k in self.objects if k.startswith(kw["Prefix"]))
            if self.page_size:
                start = int(kw.get("ContinuationToken", 0))
                page = keys[start:start + self.page_size]
                nxt = start + self.page_size
                return {"Contents": [{"Key": k} for k in page],
                        "IsTruncated": nxt < len(keys),
                        "NextContinuationToken": str(nxt)}
            return {"Contents": [{"Key": k} for k in keys], "IsTruncated": False}

        def get_object(self, Bucket, Key):
            return {"Body": io.BytesIO(self.objects[Key])}

    def test_fetches_text_objects_under_the_prefix(self):
        cli = self.FakeS3({"legal/corpus/a.txt": b"SOURCE: A Act | x\n1 Short title",
                           "legal/corpus/b.txt": b"SOURCE: B Act | x\n1 Short title"})
        docs = fetch_corpus_from_s3("bk", "legal/corpus/", client=cli)
        self.assertEqual(sorted(docs), ["legal/corpus/a.txt", "legal/corpus/b.txt"])

    def test_ignores_objects_outside_the_prefix(self):
        cli = self.FakeS3({"legal/corpus/a.txt": b"x", "legal/other/b.txt": b"y"})
        docs = fetch_corpus_from_s3("bk", "legal/corpus/", client=cli)
        self.assertEqual(list(docs), ["legal/corpus/a.txt"])

    def test_ignores_non_txt_objects(self):
        # The KB prefix can also hold manifests or metadata sidecars.
        cli = self.FakeS3({"legal/corpus/a.txt": b"x",
                           "legal/corpus/manifest.json": b"{}"})
        self.assertEqual(list(fetch_corpus_from_s3("bk", "legal/corpus/", client=cli)),
                         ["legal/corpus/a.txt"])

    def test_follows_pagination(self):
        # 12 Acts is under the 1000-key page limit today, but a silent truncation
        # would drop Acts from the agent's reach without any error.
        cli = self.FakeS3({f"legal/corpus/act-{i:02d}.txt": b"x" for i in range(12)},
                          page_size=5)
        docs = fetch_corpus_from_s3("bk", "legal/corpus/", client=cli)
        self.assertEqual(len(docs), 12)
        self.assertGreater(cli.list_calls, 1)

    def test_empty_prefix_returns_empty_not_an_error(self):
        self.assertEqual(fetch_corpus_from_s3("bk", "legal/corpus/",
                                              client=self.FakeS3({})), {})

    def test_decodes_utf8_and_survives_bad_bytes(self):
        cli = self.FakeS3({"legal/corpus/a.txt": "sect\u00a0180".encode("utf-8"),
                           "legal/corpus/b.txt": b"\xff\xfe bad"})
        docs = fetch_corpus_from_s3("bk", "legal/corpus/", client=cli)
        self.assertIn("\u00a0", docs["legal/corpus/a.txt"])
        self.assertIsInstance(docs["legal/corpus/b.txt"], str)

    def test_index_built_from_s3_keys_is_slugged_like_the_filename(self):
        cli = self.FakeS3({
            "legal/corpus/corporations-act-2001.txt":
                b"SOURCE: Corporations Act 2001 (Cth) | id\n180  Care and diligence\n(1)x"})
        corpus = build_index(fetch_corpus_from_s3("bk", "legal/corpus/", client=cli))
        self.assertEqual(list(corpus), ["corporations-act-2001"])
        self.assertEqual(corpus["corporations-act-2001"]["title"],
                         "Corporations Act 2001 (Cth)")
        self.assertTrue(find_section(corpus, "180"))


class TestFindSection(_TmpCorpus):
    FILES = {
        "demo-act.txt": (
            "SOURCE: Demo Act 2001 (Cth) | x\n"
            "180  Care and diligence\n"
            "(1)A director must exercise care.\n"
            "(2)More detail here.\n"
            "181  Good faith\n"
            "(1)A director must act in good faith.\n"
            "1043A  Prohibited conduct\n"
            "(1)An insider must not trade.\n"
        ),
    }

    def test_finds_section_and_its_subsections(self):
        hits = find_section(self.c, "180")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["heading"], "Care and diligence")
        self.assertIn("(1) A director must exercise care.", hits[0]["text"])
        self.assertIn("(2) More detail here.", hits[0]["text"])

    def test_stops_at_the_next_section(self):
        # The whole point: subsections stay attached, the NEXT section does not leak.
        self.assertNotIn("Good faith", find_section(self.c, "180")[0]["text"])

    def test_does_not_prefix_match_a_longer_section_number(self):
        # "18" must not match "180"; a prefix match would return the wrong
        # provision with full confidence, which is worse than returning nothing.
        self.assertEqual(find_section(self.c, "18"), [])

    def test_alphanumeric_sections_work_case_insensitively(self):
        hits = find_section(self.c, "1043a")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["heading"], "Prohibited conduct")

    def test_missing_section_returns_empty_not_an_error(self):
        self.assertEqual(find_section(self.c, "999ZZ"), [])

    def test_reports_start_line_for_navigation(self):
        self.assertEqual(find_section(self.c, "180")[0]["start_line"], 2)


class TestSearchText(_TmpCorpus):
    FILES = {
        "penalty-act.txt": (
            "SOURCE: Penalty Act (Cth) | x\n"
            "Schedule 3 Penalties\n"
            f"Subsection{NBSP}1041F(1)\n"
            "15 years imprisonment\n"
            f"Subsection{NBSP}1043A(1)\n"
            "15 years imprisonment\n"
            f"Subsection{NBSP}1043A(2)\n"
            "10 years imprisonment\n"
        ),
    }

    def test_finds_a_row_written_with_a_non_breaking_space(self):
        # Searching with an ORDINARY space must match text stored with an NBSP.
        hits = search_text(self.c, "Subsection 1043A(1)")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["match"], "Subsection 1043A(1)")

    def test_window_extends_after_the_match_to_reach_the_penalty(self):
        # The penalty is on the FOLLOWING line. A before-only window is useless.
        hits = search_text(self.c, "Subsection 1043A(1)")
        self.assertIn("15 years imprisonment", hits[0]["text"])

    def test_query_written_with_a_non_breaking_space_also_matches(self):
        hits = search_text(self.c, f"Subsection{NBSP}1043A(2)")
        self.assertIn("10 years imprisonment", hits[0]["text"])

    def test_is_case_insensitive(self):
        self.assertEqual(len(search_text(self.c, "subsection 1043a(1)")), 1)

    def test_respects_max_hits(self):
        self.assertEqual(len(search_text(self.c, "imprisonment", max_hits=2)), 2)

    def test_distinct_lines_are_distinct_hits(self):
        # Three penalty rows ~40 chars apart are three results, not one. Suppressing
        # by character distance would merge genuinely different provisions.
        hits = search_text(self.c, "imprisonment", max_hits=5)
        self.assertEqual(len(hits), 3)
        self.assertEqual(len({h["start_line"] for h in hits}), 3)

    def test_reports_total_match_count(self):
        self.assertEqual(search_text(self.c, "imprisonment", max_hits=2)[0]["of"], 3)

    def test_spread_includes_the_last_match_when_truncating(self):
        # The property the s1043A penalty depends on: the final match in the
        # document stays reachable when there are more hits than the budget.
        truncated = search_text(self.c, "imprisonment", max_hits=2)
        everything = search_text(self.c, "imprisonment", max_hits=5)
        self.assertEqual(truncated[-1]["start_line"],
                         max(h["start_line"] for h in everything))

    def test_empty_query_returns_empty(self):
        self.assertEqual(search_text(self.c, "   "), [])

    def test_unknown_act_hint_falls_back_rather_than_returning_nothing(self):
        self.assertEqual(len(search_text(self.c, "imprisonment", act="penalty")), 3)
        self.assertTrue(search_text(self.c, "imprisonment", act="no-such-act"))


class TestReadAround(_TmpCorpus):
    FILES = {
        "demo-act.txt": "SOURCE: Demo Act | x\n" + "\n".join(
            f"line {i}" for i in range(1, 51)),
    }

    def test_returns_a_window_around_a_line(self):
        got = read_around(self.c, "demo-act", line=20, before=2, after=3)
        self.assertIn("line 19", got["text"])
        self.assertIn("line 21", got["text"])

    def test_clamps_at_file_boundaries(self):
        got = read_around(self.c, "demo-act", line=1, before=100, after=2)
        self.assertEqual(got["from_line"], 1)

    def test_unknown_act_does_not_raise(self):
        self.assertIsNotNone(read_around(self.c, "nope", line=1))


@unittest.skipUnless(CORPUS_DIR.is_dir(), "committed corpus not present")
class TestLiveCorpus(unittest.TestCase):
    """The provisions Module 6 teaches from, against the committed text."""

    @classmethod
    def setUpClass(cls):
        # The committed copy of what the notebook reads from S3.
        docs = {p.name: p.read_text(encoding="utf-8", errors="replace")
                for p in sorted(CORPUS_DIR.glob("*.txt"))}
        cls.c = build_index(docs)

    def test_corpus_has_the_expected_twelve_acts(self):
        self.assertEqual(len(self.c), 12, sorted(self.c))

    def test_normalise_leaves_no_non_breaking_spaces(self):
        self.assertEqual(sum(d["text"].count(NBSP) for d in self.c.values()), 0)

    def test_s180_is_reachable_structurally(self):
        # Vector search buries s180(1) behind look-alike duties (Module 5);
        # structural lookup must land on it exactly.
        hits = find_section(self.c, "180", act="corporations")
        self.assertTrue(hits)
        best = hits[0]
        self.assertIn("care and diligence", best["heading"].lower())
        self.assertIn("degree of care and diligence", best["text"].lower())
        self.assertIn("director or other officer", best["text"].lower())

    def test_constitution_sections_are_findable(self):
        """The Constitution writes "92.  Heading", with a period.

        find_section must accept the period, or it finds no section of the
        Constitution.
        """
        hits = find_section(self.c, "92", act="constitution")
        self.assertTrue(hits, "s92 of the Constitution not found")
        self.assertIn("absolutely free", hits[0]["text"])
        # And the body must still stop at the next section rather than run on.
        self.assertLess(len(hits[0]["text"]), 2000)

    def test_period_form_does_not_break_the_modern_form(self):
        for section, act, expected in [("180", "corporations", "care and diligence"),
                                       ("131.1", "criminal", "theft")]:
            hits = find_section(self.c, section, act=act)
            self.assertTrue(hits, f"s{section} regressed")
            self.assertIn(expected, hits[0]["heading"].lower())

    def test_s180_body_carries_its_cross_reference(self):
        # "see section 1317E" is what the agent follows with read_around; if the
        # body were cut short, multi-hop navigation would have nothing to chase.
        text = find_section(self.c, "180", act="corporations")[0]["text"]
        self.assertIn("1317E", text)

    def test_s1043A_penalty_row_is_reachable_by_keyword(self):
        # The penalty is a bare Schedule 3 row with no semantic signal, so reranking
        # can't find it; keyword search plus a forward window can.
        hits = search_text(self.c, "Subsection 1043A(1)", act="corporations")
        self.assertTrue(hits, "s1043A row not found - corpus may have been re-pinned")
        self.assertTrue(
            any("15 years imprisonment" in h["text"] for h in hits),
            "found the row but not the penalty on the following line",
        )

    def test_the_penalty_row_is_not_the_first_match(self):
        # Pins why search_text samples a spread. The row is the LAST of 21 matches;
        # a first-N implementation returns only exemption cross-references.
        hits = search_text(self.c, "Subsection 1043A(1)", act="corporations")
        self.assertGreater(hits[0]["of"], 8)
        penalty = next(h for h in hits if "15 years imprisonment" in h["text"])
        self.assertGreater(penalty["hit"], 1)

    def test_the_penalty_row_really_does_use_a_non_breaking_space(self):
        # Pins the reason normalise() exists.
        raw = (CORPUS_DIR / "corporations-act-2001.txt").read_text(encoding="utf-8")
        self.assertIn(f"Subsection{NBSP}1043A(1)", raw)
        self.assertNotIn("Subsection 1043A(1)", raw)

    def test_act_hint_resolves_a_partial_name(self):
        self.assertEqual(pick_acts(self.c, "corporations"), ["corporations-act-2001"])
        self.assertEqual(pick_acts(self.c, "privacy"), ["privacy-act-1988"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
