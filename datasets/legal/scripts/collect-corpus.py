#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Australian Legal Corpus Collector

Builds the legislation corpus the RAG knowledge base (Modules 5 and 6) retrieves
from. Reads datasets/legal/corpus/manifest.json, downloads each Commonwealth Act
from the Federal Register of Legislation and writes one .txt file per Act into
datasets/legal/corpus/text/. Register IDs are resolved and verified against the
register's OData API rather than hardcoded. Standard library only.

Licence and provenance: datasets/legal/corpus/SOURCES.md (CC BY 4.0).

Usage:
    # Verify every federal register_id in the manifest still resolves to the
    # correct in-force principal Act (run this if downloads start 404-ing):
    python3 collect-corpus.py --verify

    # Download + extract the corpus to datasets/legal/corpus/text/:
    python3 collect-corpus.py

    # Both:
    python3 collect-corpus.py --verify --collect

    # Check the manually-collected NSW Acts are present and usable:
    python3 collect-corpus.py --check-nsw

Tables of contents are stripped by default (--keep-toc to retain them): they
embed well against "what does section X say" questions and get retrieved instead
of the operative provisions.

The three NSW Acts are not on the federal register and the NSW site blocks
automated requests, so they are collected by hand (see MANUAL_NSW).
"""

import argparse
import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile
from collections import namedtuple
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPT_DIR = Path(__file__).resolve().parent
CORPUS_DIR = SCRIPT_DIR.parent / "corpus"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
TEXT_DIR = CORPUS_DIR / "text"

REGISTER_API = "https://api.prod.legislation.gov.au/v1/titles"
# The register has no static download links. The OData /documents endpoint lists
# every stored version (date, volume, format); the bytes come from a dated
# content URL. We pick the latest Word compilation and fetch each volume.
DOCUMENTS_API = ("https://api.prod.legislation.gov.au/v1/documents"
                 "?%24filter=titleId%20eq%20%27{rid}%27")
# {rid}=register id, {date}=compilation start date (YYYY-MM-DD), {vol}=volume no.
CONTENT_URL = "https://www.legislation.gov.au/{rid}/{date}/{date}/text/original/word/{vol}"
USER_AGENT = "benchmark-to-build-corpus-collector/1.0 (sovereign-AI evaluation sample)"

DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def verify_ids(manifest: dict) -> int:
    """Re-resolve each federal register_id against the OData API and report drift.

    Returns the number of mismatches. Matches on the principal, in-force title so
    a repealed or renamed instrument is reported rather than silently downloaded.
    """
    mismatches = 0
    for inst in manifest["instruments"]:
        if inst["source"] != "legislation.gov.au":
            continue
        title, rid = inst["title"], inst["register_id"]
        # OData: combining a contains() with a boolean eq in one filter 400s on
        # this endpoint, so filter by title only and inspect the results here.
        flt = f"contains(name,'{title}')"
        url = f"{REGISTER_API}?{urllib.parse.urlencode({'$filter': flt})}"
        try:
            data = json.loads(_get(url))
        except Exception as e:  # network / API blip - report, don't crash
            print(f"  ?? {title}: could not query register API ({e})")
            mismatches += 1
            continue
        exact = [v for v in data.get("value", []) if v.get("name") == title]
        principal = next((v for v in exact if v.get("isPrincipal")), None)
        if not principal:
            print(f"  !! {title}: no principal match found in register")
            mismatches += 1
            continue
        resolved = principal["id"]
        in_force = principal.get("isInForce", False)
        flag = "" if in_force else "  [REPEALED - currency flag]"
        if resolved != rid:
            print(f"  != {title}: manifest={rid} register={resolved}{flag}")
            mismatches += 1
        else:
            print(f"  ok {title}: {rid}{flag}")
    return mismatches


def docx_to_text(blob: bytes) -> str:
    """Extract paragraph text from a .docx (a zip containing word/document.xml)."""
    with zipfile.ZipFile(BytesIO(blob)) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(f"{{{DOCX_NS['w']}}}p"):
        runs = [node.text for node in p.iter(f"{{{DOCX_NS['w']}}}t") if node.text]
        line = "".join(runs).strip()
        if line:
            paras.append(line)
    return "\n".join(paras)


# /documents pages at 510 results, OLDEST FIRST, so reading only page one silently
# resolves an old compilation for large Acts. Follow @odata.nextLink to the end;
# MAX_DOC_PAGES is only a runaway guard.
MAX_DOC_PAGES = 50

# Date, number and volume set are all needed to tell "current and complete" from
# "current but truncated".
Compilation = namedtuple(
    "Compilation", "date compilation_number volumes total_documents pages")


def fetch_all_documents(rid: str, max_pages: int = MAX_DOC_PAGES) -> list:
    """Return every stored document version for a title, across all OData pages.

    Raises if the nextLink chain does not terminate, rather than returning a
    truncated result set.
    """
    url, docs, pages, seen = DOCUMENTS_API.format(rid=rid), [], 0, set()
    while url:
        if pages >= max_pages:
            raise RuntimeError(
                f"/documents did not terminate after {max_pages} pages for {rid} "
                f"- refusing to trust a truncated result set")
        if url in seen:
            raise RuntimeError(f"/documents paging loop detected for {rid}")
        seen.add(url)
        data = json.loads(_get(url))
        docs.extend(data.get("value", []))
        pages += 1
        nxt = data.get("@odata.nextLink")
        # The API returns nextLink with literal '$' and pre-encoded '%27', so quote
        # only what is genuinely unsafe and leave those byte sequences intact.
        url = urllib.parse.quote(nxt, safe=":/?&=%$,'") if nxt else None
    return docs


def _compilation_sort_key(d: dict):
    """Order documents by compilation date, then compilation number.

    Compilation numbers are usually integers but can carry a rectification suffix
    (e.g. "23A" supersedes "23"), so sort on (leading-digits, suffix) not int().
    """
    c = str(d.get("compilationNumber") or "0")
    m = re.match(r"(\d+)(.*)", c)
    num = (int(m.group(1)), m.group(2)) if m else (0, c)
    return (str(d.get("start") or ""), num)


def latest_word_compilation(rid: str) -> Compilation:
    """Resolve the newest complete Word compilation of an Act.

    Returns every volume of the winning date and number, and only those: volumes
    from an older compilation would 404 at this date.
    """
    docs = fetch_all_documents(rid)
    words = [d for d in docs if d.get("format") == "Word"]
    if not words:
        raise RuntimeError(f"no Word-format documents listed for {rid} "
                           f"({len(docs)} documents of other formats)")

    words.sort(key=_compilation_sort_key)
    latest = words[-1]
    vols = sorted({d["volumeNumber"] for d in words
                   if d["start"] == latest["start"]
                   and d.get("compilationNumber") == latest.get("compilationNumber")})
    return Compilation(
        date=latest["start"][:10],  # ISO datetime -> YYYY-MM-DD
        compilation_number=str(latest.get("compilationNumber") or ""),
        volumes=vols,
        total_documents=len(docs),
        pages=-(-len(docs) // 510) or 1,
    )


def volume_gaps(volumes) -> list:
    """Return the volume numbers missing from a compilation's volume set.

    Volume 0 means the Act is not split, so [0] is complete. Otherwise volumes
    must run contiguously from 1, or the Act would be silently truncated.
    """
    vols = sorted(volumes)
    if not vols:
        return [1]  # nothing at all is the worst kind of gap
    if vols == [0]:
        return []
    return [v for v in range(1, max(vols) + 1) if v not in set(vols)]


def _volume_label(volumes) -> str:
    vols = sorted(volumes)
    if vols == [0]:
        return "single"
    if vols == list(range(vols[0], vols[-1] + 1)):
        return f"{vols[0]}-{vols[-1]}" if len(vols) > 1 else str(vols[0])
    return ",".join(str(v) for v in vols)


def federal_header(*, title, jurisdiction, rid, date, compilation_number, volumes) -> str:
    """Build the provenance header prepended to every federal corpus file.

    The compilation date and volume set are recorded here so `--verify` can detect
    a stale or truncated corpus from the files on disk, with no re-download.
    """
    comp = f" (compilation no {compilation_number})" if compilation_number else ""
    return (f"SOURCE: {title} ({jurisdiction}) | "
            f"Federal Register ID {rid} | compilation {date}{comp} | "
            f"volumes {_volume_label(volumes)} | "
            f"legislation.gov.au | CC BY 4.0, (c) Commonwealth of Australia\n"
            f"{'=' * 78}\n\n")


def parse_federal_header(text: str) -> dict:
    """Read date / compilation number / volumes back out of a corpus file header.

    Tolerates headers written before volumes were recorded (volumes -> None) so an
    older corpus is reported as "unknown volumes", not as an error.
    """
    head = text[:1000]
    date = re.search(r"compilation (\d{4}-\d{2}-\d{2})", head)
    comp = re.search(r"compilation no ([\w]+)", head)
    vols_m = re.search(r"volumes ([\w,\-]+)", head)
    volumes = None
    if vols_m:
        raw = vols_m.group(1)
        if raw == "single":
            volumes = [0]
        elif "-" in raw:
            lo, hi = raw.split("-", 1)
            volumes = list(range(int(lo), int(hi) + 1))
        else:
            volumes = [int(v) for v in raw.split(",") if v.strip().isdigit()]
    return {"date": date.group(1) if date else None,
            "compilation_number": comp.group(1) if comp else None,
            "volumes": volumes}


def slug_for(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def collect(manifest: dict) -> int:
    """Download every federal Act at its newest complete compilation.

    Returns the number of failures. A failed download leaves the old file on
    disk, so failures are reported loudly rather than skipped.
    """
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    federal = [i for i in manifest["instruments"] if i["source"] == "legislation.gov.au"]
    nsw = [i for i in manifest["instruments"] if i["source"] == "legislation.nsw.gov.au"]

    failures = 0
    for inst in federal:
        title, rid = inst["title"], inst["register_id"]
        out = TEXT_DIR / f"{slug_for(title)}.txt"
        previous = None
        if out.exists():
            previous = parse_federal_header(out.read_text(errors="replace"))["date"]
        if not inst.get("in_force", True):
            print(f"  ~~ {title}: REPEALED - collecting for the citing eval item, "
                  f"but flag for currency review")
        try:
            comp = latest_word_compilation(rid)
            gaps = volume_gaps(comp.volumes)
            if gaps:
                raise RuntimeError(
                    f"compilation {comp.date} lists volumes {comp.volumes} - "
                    f"missing {gaps}; refusing to write a truncated Act")
            parts = []
            for vol in comp.volumes:
                blob = _get(CONTENT_URL.format(rid=rid, date=comp.date, vol=vol))
                parts.append(docx_to_text(blob))
            text = "\n".join(parts)
        except Exception as e:
            stale = f" - {out.name} still holds compilation {previous}" if previous else ""
            print(f"  FAIL {title}: {e}{stale}")
            failures += 1
            continue
        header = federal_header(title=title, jurisdiction=inst["jurisdiction"], rid=rid,
                                date=comp.date, compilation_number=comp.compilation_number,
                                volumes=comp.volumes)
        # Write via a temp file so an interrupted run cannot leave a half-written
        # Act that would still be ingested.
        tmp = out.with_suffix(".txt.partial")
        tmp.write_text(header + text)
        tmp.replace(out)
        moved = ""
        if previous and previous != comp.date:
            moved = f"  [was {previous}]"
        elif previous == comp.date:
            moved = "  [unchanged]"
        print(f"  OK   {title}: {len(text):,} chars "
              f"(vols {_volume_label(comp.volumes)}, {comp.date}, "
              f"{comp.total_documents} versions/{comp.pages}pp) -> {out.name}{moved}")

    if nsw:
        print("\n  NSW state instruments (manual - not on the federal register):")
        for inst in nsw:
            path = TEXT_DIR / f"{slug_for(inst['title'])}.txt"
            state = f"present, {path.stat().st_size:,} bytes" if path.exists() else "MISSING"
            print(f"    keep {inst['title']} (NSW) -> {path.name} ({state})")
        print("  Not re-fetched: manual step. See MANUAL_NSW / BUILDING_DATASETS.md.")
    return failures


def verify_currency(manifest: dict) -> int:
    """Assert every federal corpus file is the newest COMPLETE compilation.

    Returns the problem count.
    """
    problems = 0
    for inst in manifest["instruments"]:
        if inst["source"] != "legislation.gov.au":
            continue
        title, rid = inst["title"], inst["register_id"]
        path = TEXT_DIR / f"{slug_for(title)}.txt"
        try:
            comp = latest_word_compilation(rid)
        except Exception as e:
            print(f"  ?? {title}: could not resolve latest compilation ({e})")
            problems += 1
            continue

        gaps = volume_gaps(comp.volumes)
        register = (f"register: {comp.date} vols {_volume_label(comp.volumes)}"
                    f" ({comp.total_documents} versions across {comp.pages} page(s))")
        if gaps:
            print(f"  !! {title}: register itself lists a volume gap {gaps} - {register}")
            problems += 1
            continue
        if not path.exists():
            print(f"  -- {title}: NOT COLLECTED ({path.name} missing) | {register}")
            problems += 1
            continue

        have = parse_federal_header(path.read_text(errors="replace"))
        issues = []
        if have["date"] is None:
            issues.append("no compilation date in the header - re-collect")
        elif have["date"] < comp.date:
            issues.append(f"STALE: on disk {have['date']}, register {comp.date}")
        elif have["date"] > comp.date:
            issues.append(f"on disk {have['date']} is NEWER than the register's "
                          f"{comp.date} - manifest/register mismatch, investigate")
        if have["volumes"] is None:
            issues.append(f"volumes not recorded (older header) - expected "
                          f"{_volume_label(comp.volumes)}, cannot confirm completeness")
        elif have["volumes"] != comp.volumes:
            issues.append(f"PARTIAL: on disk vols {_volume_label(have['volumes'])}, "
                          f"register has {_volume_label(comp.volumes)}")
        if issues:
            print(f"  != {title} ({path.name})")
            for i in issues:
                print(f"       - {i}")
            print(f"       {register}")
            problems += 1
        else:
            print(f"  ok {title}: {have['date']} vols "
                  f"{_volume_label(have['volumes'])} - current and complete")
    return problems


# A TOC entry ends in its page number ("1Short title1"). The loose pattern is only
# applied inside a block opened by a "Contents" line, which ends after
# TOC_END_RUN consecutive non-matching lines.
TOC_ENTRY = re.compile(r"\S\d+$")
TOC_MARKER = "Contents"
TOC_END_RUN = 8


def strip_toc(text: str):
    """Remove every table-of-contents block. Returns (new_text, lines_removed).

    Handles one block per volume. Idempotent.
    """
    lines = text.split("\n")
    out, i, removed = [], 0, 0
    while i < len(lines):
        if lines[i].strip() == TOC_MARKER:
            j, run, last = i + 1, 0, i
            while j < len(lines):
                stripped = lines[j].strip()
                if not stripped:
                    j += 1
                    continue
                if TOC_ENTRY.search(stripped):
                    run, last = 0, j
                else:
                    run += 1
                    if run >= TOC_END_RUN:
                        break
                j += 1
            removed += last - i + 1
            i = last + 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), removed


def strip_toc_in_place(text_dir: Path) -> None:
    """Strip TOC blocks from every .txt in the corpus, federal and NSW alike."""
    files = sorted(text_dir.glob("*.txt"))
    if not files:
        print("  (no corpus files to strip)")
        return
    total_before = total_after = 0
    for f in files:
        before = f.read_text()
        after, removed = strip_toc(before)
        total_before, total_after = total_before + len(before), total_after + len(after)
        if removed:
            f.write_text(after)
            print(f"  {f.name}: removed {removed:,} TOC lines "
                  f"({len(before):,} -> {len(after):,} chars)")
        else:
            print(f"  {f.name}: no TOC block found (already stripped, or none)")
    if total_before:
        print(f"  corpus: {total_before:,} -> {total_after:,} chars "
              f"({1 - total_after / total_before:.1%} removed)")


# Below the shortest NSW Act (~13,700 chars) but well above a saved error or
# bot-challenge page.
NSW_MIN_CHARS = 8_000

# The statute starts at its long title. Use the first match only: schedules can
# quote another Act's long title.
NSW_LONG_TITLE = re.compile(r"^An Act\b", re.M)

# The NSW site wraps the statute in <div id="main-fragview">.
NSW_CONTENT_DIV_ID = "main-fragview"
NSW_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript", "svg", "button"}
NSW_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
                  "section", "article", "table", "blockquote"}


class _NswHtmlExtractor(HTMLParser):
    """Pull the statute text out of the content div of a saved NSW page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._depth = 0          # nesting depth once inside the content div
        self._skip = 0           # nesting depth inside a chrome tag
        self._in_content = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if not self._in_content:
            if tag == "div" and attrs.get("id") == NSW_CONTENT_DIV_ID:
                self._in_content, self._depth = True, 1
            return
        if tag in NSW_SKIP_TAGS:
            self._skip += 1
            return
        if tag == "div":
            self._depth += 1
        if tag in NSW_BLOCK_TAGS and not self._skip:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if not self._in_content:
            return
        if tag in NSW_SKIP_TAGS and self._skip:
            self._skip -= 1
            return
        if tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                self._in_content = False
        if tag in NSW_BLOCK_TAGS and not self._skip:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_content and not self._skip and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        raw = " ".join(self.parts)
        raw = re.sub(r"[ \t]*\n[ \t]*", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        return raw.strip()


def trim_to_long_title(text: str):
    """Drop the saved page's chrome by cutting to the Act's long title.

    Returns (trimmed_text, chars_dropped). The chrome would otherwise be
    retrieved as if it were law.
    """
    m = NSW_LONG_TITLE.search(text)
    if not m:
        return text, 0
    return text[m.start():], m.start()


def _html_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return unescape(m.group(1)).strip() if m else ""


def extract_nsw_html(manifest: dict) -> int:
    """Convert saved NSW .txt.html pages into corpus .txt files.

    The output filename comes from the page's <title> matched against the
    manifest, not from the saved filename, which also confirms the page is the
    right Act. Returns the number of problems.
    """
    nsw = [i for i in manifest["instruments"] if i["source"] == "legislation.nsw.gov.au"]
    pages = sorted(TEXT_DIR.glob("*.txt.html")) + sorted(TEXT_DIR.glob("*.html"))
    pages = sorted({p for p in pages})
    if not pages:
        print("  (no saved .html pages found in the corpus dir)")
        return 0

    problems = 0
    for page in pages:
        html = page.read_text(encoding="utf-8", errors="replace")
        title = _html_title(html)
        inst = next((i for i in nsw if i["title"].lower() in title.lower()), None)
        if inst is None:
            print(f"  SKIP  {page.name}: <title> {title!r} matches no NSW manifest entry")
            problems += 1
            continue

        parser = _NswHtmlExtractor()
        parser.feed(html)
        text, chrome = trim_to_long_title(parser.text())
        if not chrome:
            print(f"  WARN  {page.name}: no long title found - page chrome may remain")
        if len(text) < NSW_MIN_CHARS:
            print(f"  FAIL  {page.name}: extracted only {len(text):,} chars "
                  f"(expected >{NSW_MIN_CHARS:,}) - content div may have changed")
            problems += 1
            continue

        num = re.search(r"\bNo\s+(\d+)\b", title)
        act_no = f" No {num.group(1)}" if num else ""
        slug = re.sub(r"[^a-z0-9]+", "-", inst["title"].lower()).strip("-")
        out = TEXT_DIR / f"{slug}.txt"
        header = (f"SOURCE: {inst['title']}{act_no} ({inst['jurisdiction']}) | "
                  f"legislation.nsw.gov.au | in-force compilation, retrieved manually | "
                  f"CC BY 4.0, (c) State of New South Wales\n{'=' * 78}\n\n")
        out.write_text(header + text)
        note = "" if page.stem.replace(".txt", "") == slug else f"  [renamed from {page.name}]"
        print(f"  OK    {inst['title']}{act_no}: {len(text):,} chars "
              f"({chrome:,} chars of chrome trimmed) -> {out.name}{note}")
    return problems


def clean_nsw_artifacts() -> None:
    """Delete saved-page leftovers (.txt.html and the <slug>_files/ sidecars)."""
    removed = []
    for page in sorted(TEXT_DIR.glob("*.html")):
        page.unlink()
        removed.append(page.name)
    for sidecar in sorted(TEXT_DIR.glob("*_files")):
        if sidecar.is_dir():
            shutil.rmtree(sidecar)
            removed.append(sidecar.name + "/")
    print(f"  removed {len(removed)} artifact(s): {', '.join(removed) if removed else 'none'}")


def check_nsw(manifest: dict) -> int:
    """Report whether the manually-collected NSW Acts are present and usable.

    Returns the number of problems. Catches a saved bot-challenge page or raw
    HTML instead of the Act text.
    """
    nsw = [i for i in manifest["instruments"] if i["source"] == "legislation.nsw.gov.au"]
    problems = 0
    for inst in nsw:
        title = inst["title"]
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        path = TEXT_DIR / f"{slug}.txt"
        if not path.exists():
            print(f"  MISSING  {title} -> expected {path.name}")
            problems += 1
            continue
        text = path.read_text(errors="replace")
        issues = []
        if len(text) < NSW_MIN_CHARS:
            issues.append(f"only {len(text):,} chars (expected >{NSW_MIN_CHARS:,}) "
                          f"- is this a saved error/challenge page?")
        low = text[:4000].lower()
        if "<html" in low or "<!doctype" in low:
            issues.append("looks like raw HTML - save the text, not the page source")
        if "enable javascript" in low or "just a moment" in low:
            issues.append("this is the bot-challenge page, not the Act")
        if not text.startswith("SOURCE:"):
            issues.append("no SOURCE: provenance header (see the suggested line below)")
        if issues:
            print(f"  PROBLEM  {title} ({path.name}, {len(text):,} chars)")
            for issue in issues:
                print(f"             - {issue}")
            if not text.startswith("SOURCE:"):
                print(f"             suggested first line:\n"
                      f"             SOURCE: {title} (NSW) | legislation.nsw.gov.au | "
                      f"in-force compilation | CC BY 4.0, (c) State of New South Wales")
            problems += 1
        else:
            print(f"  ok       {title} ({path.name}, {len(text):,} chars)")
    if not nsw:
        print("  (no NSW instruments in the manifest)")
    return problems


MANUAL_NSW = """
NSW instruments - manual collection procedure
---------------------------------------------
1. Go to https://legislation.nsw.gov.au and search the Act title.
2. Open the "current" in-force version, choose the HTML or Word view.
3. Save the full text to datasets/legal/corpus/text/<slug>.txt with a SOURCE header
   (title, NSW, URL, CC BY 4.0, (c) State of New South Wales).
Acts: Succession Act 2006, Sale of Goods Act 1923, Frustrated Contracts Act 1978.

Save each as datasets/legal/corpus/text/<slug>.txt:
    succession-act-2006.txt, sale-of-goods-act-1923.txt,
    frustrated-contracts-act-1978.txt
then run `--check-nsw` to confirm they are usable before ingesting.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect the AU legal source corpus.")
    ap.add_argument("--verify", action="store_true",
                    help="Re-resolve federal register IDs AND assert the corpus on "
                         "disk is the newest complete compilation of each Act.")
    ap.add_argument("--verify-ids-only", action="store_true",
                    help="Only re-resolve register IDs; skip the currency assertion.")
    ap.add_argument("--collect", action="store_true",
                    help="Download + extract the corpus text (default if neither flag given).")
    ap.add_argument("--check-nsw", action="store_true",
                    help="Check the manually-collected NSW Acts are present and usable.")
    ap.add_argument("--extract-nsw", action="store_true",
                    help="Convert saved NSW .txt.html pages into corpus .txt files "
                         "(names them from the page title, not the saved filename).")
    ap.add_argument("--clean-artifacts", action="store_true",
                    help="Delete saved-page leftovers (*.html and *_files/ sidecars).")
    ap.add_argument("--keep-toc", action="store_true",
                    help="Keep tables of contents (they are stripped by default because "
                         "retrieval returns them instead of operative provisions).")
    ap.add_argument("--strip-toc-only", action="store_true",
                    help="Strip TOC blocks from the existing corpus without re-downloading "
                         "(use after manually adding a file, e.g. the NSW Acts).")
    args = ap.parse_args()

    manifest = load_manifest()
    do_verify = args.verify or args.verify_ids_only
    explicit = (do_verify or args.check_nsw or args.strip_toc_only
                or args.extract_nsw or args.clean_artifacts)
    do_collect = args.collect or not explicit  # default action is collect

    rc = 0
    if do_verify:
        print("Verifying federal register IDs...")
        mismatches = verify_ids(manifest)
        print(f"  {mismatches} mismatch(es).\n")
        if mismatches:
            rc = 1
    if args.verify and not args.verify_ids_only:
        print("Verifying compilation currency (date + volume completeness)...")
        stale = verify_currency(manifest)
        print(f"  {stale} currency problem(s).\n")
        if stale:
            rc = 1
    if do_collect:
        print("Collecting corpus...")
        if collect(manifest):
            rc = 1
    if args.extract_nsw:
        print("Extracting NSW Acts from saved HTML...")
        if extract_nsw_html(manifest):
            rc = rc or 1
    if args.clean_artifacts:
        print("\nCleaning saved-page artifacts...")
        clean_nsw_artifacts()
    if (do_collect or args.strip_toc_only or args.extract_nsw) and not args.keep_toc:
        print("\nStripping tables of contents...")
        strip_toc_in_place(TEXT_DIR)
    if args.check_nsw:
        print("\nChecking manually-collected NSW Acts...")
        problems = check_nsw(manifest)
        print(f"  {problems} problem(s).")
        if problems:
            print(MANUAL_NSW)
            rc = rc or 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
