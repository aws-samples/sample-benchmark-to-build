#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Tests for the corpus collector's compilation resolution and currency checks.

Standard library only. Run from the repo root:
    python3 -m unittest discover -s datasets/legal/scripts -p 'test_*.py' -v
"""

import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def _load_collector():
    """Import the hyphenated script as a module."""
    path = SCRIPT_DIR / "collect-corpus.py"
    spec = importlib.util.spec_from_file_location("collect_corpus", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cc = _load_collector()


def doc(date, vol=0, comp="1", fmt="Word"):
    """Build a minimal /documents entry as the register returns it."""
    return {"start": f"{date}T00:00:00+00:00", "volumeNumber": vol,
            "compilationNumber": comp, "format": fmt}


class FakeApi:
    """Serves `pages` in order, with @odata.nextLink on all but the last."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, timeout=60):
        self.calls.append(url)
        idx = 0
        if "$skip=" in url:
            idx = int(url.split("$skip=")[1].split("&")[0]) // 510
        elif "%24skip=" in url:
            idx = int(url.split("%24skip=")[1].split("&")[0]) // 510
        body = {"value": self.pages[idx]}
        if idx + 1 < len(self.pages):
            body["@odata.nextLink"] = (
                "https://api.prod.legislation.gov.au/v1/documents"
                f"?$filter=titleId%20eq%20%27X%27&$skip={(idx + 1) * 510}")
        return json.dumps(body).encode()


class PaginationTest(unittest.TestCase):
    """fetch_all_documents must follow @odata.nextLink to the end."""

    def setUp(self):
        self._real_get = cc._get

    def tearDown(self):
        cc._get = self._real_get

    def test_follows_next_link_across_all_pages(self):
        api = FakeApi([[doc("2001-01-01")] * 3, [doc("2011-07-01")] * 3,
                       [doc("2026-08-27")] * 2])
        cc._get = api.get
        docs = cc.fetch_all_documents("C2004A00818")
        self.assertEqual(len(docs), 8, "must return documents from every page")
        self.assertEqual(len(api.calls), 3, "must request each page exactly once")

    def test_single_page_response_needs_no_follow_up(self):
        api = FakeApi([[doc("2026-08-27")]])
        cc._get = api.get
        self.assertEqual(len(cc.fetch_all_documents("C2004A03712")), 1)
        self.assertEqual(len(api.calls), 1)

    def test_page_cap_raises_rather_than_looping_forever(self):
        """A malformed nextLink that never terminates must fail loudly."""
        class Endless:
            def get(self, url, timeout=60):
                return json.dumps({
                    "value": [doc("2001-01-01")],
                    "@odata.nextLink": "https://api.prod.legislation.gov.au/v1/"
                                       "documents?$filter=x&$skip=0",
                }).encode()
        cc._get = Endless().get
        with self.assertRaises(RuntimeError):
            cc.fetch_all_documents("X", max_pages=3)


class LatestCompilationTest(unittest.TestCase):
    """The newest compilation must win, not the newest on page 1."""

    def setUp(self):
        self._real_get = cc._get

    def tearDown(self):
        cc._get = self._real_get

    def test_picks_newest_compilation_from_a_later_page(self):
        page1 = [doc("2011-05-10", vol=v, comp="100") for v in (1, 2, 3, 4, 5)]
        page2 = [doc("2026-08-27", vol=v, comp="180") for v in (1, 2, 3, 4, 5, 6, 7)]
        cc._get = FakeApi([page1, page2]).get
        comp = cc.latest_word_compilation("C2004A00818")
        self.assertEqual(comp.date, "2026-08-27")
        self.assertEqual(comp.volumes, [1, 2, 3, 4, 5, 6, 7])

    def test_ignores_non_word_formats(self):
        cc._get = FakeApi([[doc("2026-08-27", fmt="Pdf"), doc("2020-01-01", fmt="Word")]]).get
        self.assertEqual(cc.latest_word_compilation("X").date, "2020-01-01")

    def test_raises_when_no_word_documents_exist(self):
        cc._get = FakeApi([[doc("2026-08-27", fmt="Pdf")]]).get
        with self.assertRaises(RuntimeError):
            cc.latest_word_compilation("X")

    def test_rectification_suffix_breaks_the_date_tie(self):
        """Same date, compilation 23A supersedes 23."""
        cc._get = FakeApi([[doc("2026-01-01", comp="23"),
                            doc("2026-01-01", comp="23A")]]).get
        self.assertEqual(cc.latest_word_compilation("X").compilation_number, "23A")

    def test_volumes_come_only_from_the_winning_compilation(self):
        """An older compilation's extra volumes must not leak into the volume set."""
        old = [doc("2011-05-10", vol=v, comp="100") for v in (1, 2, 3, 4, 5, 6, 7, 8)]
        new = [doc("2026-08-27", vol=v, comp="180") for v in (1, 2, 3)]
        cc._get = FakeApi([old, new]).get
        self.assertEqual(cc.latest_word_compilation("X").volumes, [1, 2, 3])


class VolumeCompletenessTest(unittest.TestCase):
    def test_single_unsplit_volume_is_complete(self):
        self.assertEqual(cc.volume_gaps([0]), [])

    def test_contiguous_volumes_are_complete(self):
        self.assertEqual(cc.volume_gaps([1, 2, 3, 4, 5, 6, 7]), [])

    def test_gap_is_reported(self):
        self.assertEqual(cc.volume_gaps([1, 2, 4, 5]), [3])

    def test_not_starting_at_one_is_reported(self):
        self.assertEqual(cc.volume_gaps([2, 3]), [1])

    def test_empty_volume_set_is_a_problem(self):
        self.assertNotEqual(cc.volume_gaps([]), [])


class HeaderTest(unittest.TestCase):
    """The provenance header lets --verify check the corpus without re-downloading."""

    def test_header_roundtrips_date_and_volumes(self):
        header = cc.federal_header(
            title="Corporations Act 2001", jurisdiction="Cth", rid="C2004A00818",
            date="2026-08-27", compilation_number="180", volumes=[1, 2, 3, 4, 5, 6, 7])
        parsed = cc.parse_federal_header(header)
        self.assertEqual(parsed["date"], "2026-08-27")
        self.assertEqual(parsed["volumes"], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(parsed["compilation_number"], "180")

    def test_single_volume_roundtrips(self):
        header = cc.federal_header(title="Privacy Act 1988", jurisdiction="Cth",
                                  rid="C2004A03712", date="2026-06-04",
                                  compilation_number="99", volumes=[0])
        self.assertEqual(cc.parse_federal_header(header)["volumes"], [0])

    def test_legacy_header_without_volumes_parses_date_only(self):
        """Files collected before volume recording must still report their date."""
        legacy = ("SOURCE: Corporations Act 2001 (Cth) | Federal Register ID "
                  "C2004A00818 | compilation 2021-08-02 | legislation.gov.au | "
                  "Crown copyright, Copyright Act 1968 (Cth) s 182A")
        parsed = cc.parse_federal_header(legacy)
        self.assertEqual(parsed["date"], "2021-08-02")
        self.assertIsNone(parsed["volumes"])

    def test_unparseable_header_returns_none_date(self):
        self.assertIsNone(cc.parse_federal_header("not a header")["date"])


class TocStripTest(unittest.TestCase):
    """Locks in the TOC-strip behaviour."""

    def test_strips_contents_block_but_keeps_operative_text(self):
        text = "\n".join([
            "SOURCE: x", "Contents", "1Short title1", "2Commencement1",
            "Chapter 1-Introductory1",
            "An Act about corporations", "and related matters", "1  Short title",
            "This Act may be cited as the Corporations Act 2001.",
            "It commences on Royal Assent.", "Nothing further applies here.",
            "The end of the operative text.",
        ])
        out, removed = cc.strip_toc(text)
        self.assertGreater(removed, 0)
        self.assertNotIn("1Short title1", out)
        self.assertIn("This Act may be cited as the Corporations Act 2001.", out)

    def test_is_idempotent(self):
        text = "\n".join(["Contents", "1Short title1", "2Commencement1"]
                         + [f"prose line {i}" for i in range(12)])
        once, _ = cc.strip_toc(text)
        twice, removed = cc.strip_toc(once)
        self.assertEqual(once, twice)
        self.assertEqual(removed, 0)

    def test_text_with_no_contents_block_is_unchanged(self):
        text = "An Act about things\nSection 1 applies.\n"
        out, removed = cc.strip_toc(text)
        self.assertEqual(out, text)
        self.assertEqual(removed, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
