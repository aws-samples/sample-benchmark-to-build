# Source Legislation — Provenance, Versions and Licensing

This directory contains the **source-legislation corpus** that the Module 3 RAG
knowledge base retrieves from: the full text of the 12 primary instruments cited
by the 50-item evaluation set (`datasets/legal/processed/eval-legal-au.jsonl`).

The text in `text/` is **committed to this repository** rather than regenerated,
so every run is repeatable: a fresh clone reproduces the exact corpus every
measured result was scored against. The machine-readable form of
this table — including a SHA-256 for each file — is `manifest.json`.

## ⚠️ This is a processed copy, not the official version

The files in `text/` are **not** authorised versions of the law and must not be
relied on as a statement of it. Processing applied:

- **Commonwealth Acts** — downloaded as the authorised Word (DOCX) compilation
  volumes from the Federal Register of Legislation, converted to plain text.
  Document structure (tables, formatting, footnotes, cross-reference styling) is
  flattened to text.
- **Tables of contents stripped.** Every compilation volume opens with a contents
  listing. These embed deceptively well against questions like "what does section
  X say" and were polluting retrieval, so they are removed by default
  (`collect-corpus.py --keep-toc` retains them).
- **NSW Acts — site chrome trimmed.** These were saved manually as HTML pages and
  the statute text extracted from the page's content div; surrounding navigation,
  headers, footers and scripts were discarded.
- A one-line `SOURCE:` provenance header is prepended to each file.

**For the authoritative text, always go to the URL in the table below.**
For Commonwealth law, the authorised version is the compilation on the Federal
Register of Legislation.

## Commonwealth instruments (9)

Source: **Federal Register of Legislation**, <https://www.legislation.gov.au>.
Resolved and downloaded programmatically via the register's OData API
(`api.prod.legislation.gov.au`) by `../scripts/collect-corpus.py`.
**Retrieved 18 September 2026.**

| Act (full title) | Jurisdiction | Register ID | Compilation used | Compilation date | Volumes | URL |
|---|---|---|---|---|---|---|
| Corporations Act 2001 | Commonwealth of Australia | `C2004A00818` | No. 148 | 27 Aug 2026 | 1–7 | <https://www.legislation.gov.au/C2004A00818/2026-08-27/2026-08-27/text> |
| Competition and Consumer Act 2010 | Commonwealth of Australia | `C2004A00109` | No. 166 | 27 Aug 2026 | 1–4 | <https://www.legislation.gov.au/C2004A00109/2026-08-27/2026-08-27/text> |
| Fair Work Act 2009 | Commonwealth of Australia | `C2009A00028` | No. 73 | 7 Jul 2026 | 1–4 | <https://www.legislation.gov.au/C2009A00028/2026-07-07/2026-07-07/text> |
| Criminal Code Act 1995 | Commonwealth of Australia | `C2004A04868` | No. 174 | 30 Jun 2026 | 1–3 | <https://www.legislation.gov.au/C2004A04868/2026-06-30/2026-06-30/text> |
| Privacy Act 1988 | Commonwealth of Australia | `C2004A03712` | No. 104 | 4 Jun 2026 | single | <https://www.legislation.gov.au/C2004A03712/2026-06-04/2026-06-04/text> |
| Administrative Appeals Tribunal Act 1975 | Commonwealth of Australia | `C2004A01401` | No. 54 | 22 May 2024 | single | <https://www.legislation.gov.au/C2004A01401/2024-05-22/2024-05-22/text> |
| Administrative Decisions (Judicial Review) Act 1977 | Commonwealth of Australia | `C2004A01697` | No. 133 | 27 Aug 2026 | single | <https://www.legislation.gov.au/C2004A01697/2026-08-27/2026-08-27/text> |
| Commonwealth of Australia Constitution Act | Commonwealth of Australia | `C2004Q00685` | No. 6 | 29 Jul 1977 | single | <https://www.legislation.gov.au/C2004Q00685/1977-07-29/1977-07-29/text> |
| Electronic Transactions Act 1999 | Commonwealth of Australia | `C2004A00553` | No. 4 | 5 Dec 2025 | single | <https://www.legislation.gov.au/C2004A00553/2025-12-05/2025-12-05/text> |

Notes on two entries that look wrong but are not:

- **Constitution — compilation No. 6, dated 1977.** This *is* the current
  compilation; the last amendment by referendum was Act No. 84 of 1977. The
  register ID is a Q-series "collection" ID, not an A-series Act ID.
- **Administrative Appeals Tribunal Act 1975 — REPEALED 14 Oct 2024**, replaced
  by the Administrative Review Tribunal Act 2024 (repeal effected by
  `C2024A00038`). Compilation No. 54 is therefore the final one. It is retained
  because an eval item cites the AAT; that item is flagged for currency review.
  See `manifest.json` (`in_force: false`).

### Licence — Commonwealth: CC BY 4.0 ✅ verified

Per the Federal Register of Legislation
[Terms of use](https://www.legislation.gov.au/terms-of-use), which states that
with the exception of the Commonwealth Coat of Arms and where otherwise noted,
content on the Legislation Register is licensed under the
**Creative Commons Attribution 4.0 International (CC BY 4.0)** licence —
including for commercial purposes — provided you link to the Register, attribute
the content to the Federal Register of Legislation, link to the licence, and
indicate whether changes were made.

Required attribution, in the form the Register prescribes for **changed**
material (our text is processed — see above):

> Based on content from the Federal Register of Legislation at 18 September 2026.
> For the latest information on Australian Government legislation please go to
> <https://www.legislation.gov.au>.

Licence: <https://creativecommons.org/licenses/by/4.0/>.
Excluded from the licence: the Commonwealth Coat of Arms, and any third-party
material identified as such (none knowingly included here).

> The `SOURCE:` line at the top of each committed Commonwealth `.txt` file reads
> "Crown copyright, Copyright Act 1968 (Cth) s 182A". That line predates the
> licence check and is more restrictive than the actual terms. **This file is the
> licence statement that applies: CC BY 4.0.**

## NSW instruments (3)

Source: **NSW legislation website**, <https://legislation.nsw.gov.au>, published
by the Parliamentary Counsel's Office of New South Wales.
**Retrieved manually on 16 September 2026.** These must be collected manually.

| Act (full title) | Jurisdiction | Act number | Version used | Latest amendment visible in the text | URL |
|---|---|---|---|---|---|
| Succession Act 2006 | New South Wales | No 80 of 2006 | In-force ("current") version as at 16 Sep 2026 — **exact version date not recorded** | 2023 No 7 | <https://legislation.nsw.gov.au/view/html/inforce/current/act-2006-080> |
| Sale of Goods Act 1923 | New South Wales | No 1 of 1923 | In-force ("current") version as at 16 Sep 2026 — **exact version date not recorded** | 2010 No 57 | <https://legislation.nsw.gov.au/view/html/inforce/current/act-1923-001> |
| Frustrated Contracts Act 1978 | New South Wales | No 105 of 1978 | In-force ("current") version as at 16 Sep 2026 — **exact version date not recorded** | 2014 No 88 | <https://legislation.nsw.gov.au/view/html/inforce/current/act-1978-105> |

The nine Commonwealth URLs above were each checked and return HTTP 200. The three NSW URLs **could not be checked** — the domain
returns 403 to automated requests — so they are given in the site's standard
`view/html/inforce/current/act-<year>-<number>` form and are best confirmed in a
browser.

⚠️ **The NSW version pinning is weaker than the Commonwealth pinning, and
honestly so.** The NSW site states its currency as a "Current version for
*&lt;date&gt;* to date" banner, which sits in the page chrome that the extractor
discards — so the files on disk do not record it and it cannot now be recovered
from them. What *is* recorded:

- the **retrieval date** (16 September 2026) — the version in force on that date;
- the **latest amending Act referenced in the text itself**, from the historical
  notes (column above) — a verifiable lower bound on currency, not the version date;
- a **SHA-256 per file** in `manifest.json` — so the bytes used for every measured
  result are pinned exactly, even though the upstream version label is not.

To tighten this, re-save the three pages and record the "Current version for …"
banner date before trimming chrome.

### Licence — NSW: CC BY 4.0 ✅ confirmed

The three NSW Acts — **Succession Act 2006**, **Sale of Goods Act 1923** and
**Frustrated Contracts Act 1978** — are licensed under the
**Creative Commons Attribution 4.0 International (CC BY 4.0)** licence, the same
licence as the Commonwealth material above, commercial use included.

Per the NSW Legislation website's
[Copyright](https://legislation.nsw.gov.au/copyright) page: unless otherwise
noted, material on the site is licensed under CC BY 4.0, commercial use included.
Reusers must keep the copyright notice, attribute the State of New South Wales as
the source, and use the site's prescribed wording. The government coat of arms and
logos are excluded from the licence.

Required attribution, in the form the site prescribes for **changed** material
(our text is processed — see above):

> Based on content from the New South Wales Legislation website at 16 September
> 2026. For the latest information on New South Wales Government legislation
> please go to <https://www.legislation.nsw.gov.au>.
>
> © State of New South Wales.

Licence: <https://creativecommons.org/licenses/by/4.0/>.

> The `SOURCE:` line in the three NSW `.txt` files reads "NSW Crown copyright".
> **This file is the licence statement that applies: CC BY 4.0**, which permits
> commercial use.

**Both jurisdictions publish under CC BY 4.0, so all 12 files may be redistributed in a
public samples repository** with the attributions recorded here.

## Why the corpus is the *full* text of each Act

We ingest every Act in full, not only the sections the eval answers cite.
Handing the retriever just the answer sections would be teaching to the test;
retrieving the right provision out of thousands is the honest measure of whether
grounding works. This is also why the Corporations Act alone is 6.3 MB.

## Corpus at a glance

12 files, ~14.5 MB total. Sizes and SHA-256 digests are in `manifest.json`.

| File | Bytes |
|---|---|
| `text/corporations-act-2001.txt` | 6,310,655 |
| `text/competition-and-consumer-act-2010.txt` | 2,976,904 |
| `text/fair-work-act-2009.txt` | 2,058,436 |
| `text/criminal-code-act-1995.txt` | 1,837,402 |
| `text/privacy-act-1988.txt` | 607,832 |
| `text/administrative-appeals-tribunal-act-1975.txt` | 256,514 |
| `text/succession-act-2006.txt` | 175,124 |
| `text/administrative-decisions-judicial-review-act-1977.txt` | 117,655 |
| `text/commonwealth-of-australia-constitution-act.txt` | 79,663 |
| `text/sale-of-goods-act-1923.txt` | 52,084 |
| `text/electronic-transactions-act-1999.txt` | 45,394 |
| `text/frustrated-contracts-act-1978.txt` | 13,991 |

## Verifying what you have

```bash
# Confirm the committed corpus matches the pinned digests in manifest.json:
python3 - <<'PY'
import hashlib, json, pathlib
root = pathlib.Path("datasets/legal/corpus")
m = json.loads((root / "manifest.json").read_text())
for i in m["instruments"]:
    p = root / i["file"]
    got = hashlib.sha256(p.read_bytes()).hexdigest()
    print(("OK  " if got == i["sha256"] else "DIFF"), i["file"])
PY

# Re-check the Commonwealth register IDs and compilation currency upstream
# (this reports drift from the pinned versions; it does not change the files):
python3 datasets/legal/scripts/collect-corpus.py --verify
```

`--verify` comparing the pinned compilation against the register's newest is the
point: when it reports drift, that is a deliberate decision to make — re-pin and
re-measure, or stay pinned — not something the collector should do silently.

## Known limitations

1. **Re-running the collector replaces the pinned text.** `collect-corpus.py`
   always fetches the newest compilation, so a plain run over this corpus swaps
   the pinned versions for newer law, and scores measured on the old text stop
   being reproducible. Use `--verify` to see whether upstream has moved, and
   treat a full run as a deliberate re-pin.
2. **The `SOURCE:` licence line in the 12 committed files is out of date** (see
   above). The collector writes the CC BY 4.0 line for newly collected files.
   Rewriting the committed files changes every digest, so it's left for the next
   re-pin.
