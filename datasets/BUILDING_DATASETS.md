# Building an Australian Evaluation Dataset

> **Audience:** Government procurement teams, domain experts, and technical staff who need to create jurisdiction-specific AI evaluation datasets.

This guide documents the exact process used to build the Australian legal evaluation dataset in this project. Follow the same methodology to build datasets for health, education, or any other domain.

## Overview

An evaluation dataset is a set of questions with known-correct answers that you use to score how well an AI model performs on your jurisdiction's content. The process is:

1. **Identify authoritative sources** (legislation, guidelines, standards)
2. **Extract knowledge** that a competent model should know
3. **Structure as question-answer pairs** in a machine-readable format
4. **Validate with domain experts** (critical for production use)
5. **Format for your evaluation tool** (Bedrock, fmeval, lm-harness)

## Step 1: Identify Authoritative Sources

For any Australian domain, start with the **primary legislation and official guidance**:

| Domain | Primary Sources | Why |
|--------|----------------|-----|
| Legal | legislation.gov.au, legislation.nsw.gov.au | Legislation CC BY 4.0 (see `legal/corpus/SOURCES.md`) |
| Health | pbs.gov.au, tga.gov.au, racgp.org.au | Official clinical guidelines |
| Education | australiancurriculum.edu.au, nap.edu.au | National curriculum standards |

### Licensing Considerations

- **Commonwealth legislation**: published on the Federal Register of Legislation under **CC BY 4.0** (commercial use included), per the register's [Terms of use](https://www.legislation.gov.au/terms-of-use) — attribute the Register, link the licence, and say whether you changed anything. Excludes the Commonwealth Coat of Arms.
- **State legislation**: each state sets its own terms — **check them, don't assume**. The NSW Acts in this project are **CC BY 4.0**. Note that `legislation.nsw.gov.au` blocks automated requests, so this had to be read in a browser rather than fetched — budget for manual verification steps like this.
- **Clinical guidelines**: Check individual publisher terms
- **Exam questions**: Most restrictive — generate questions *about* the content rather than reproducing exam papers

## Step 2: Extract Knowledge

For each source, identify **facts that a competent model should know**. Categories:

| Category | Example | Source |
|----------|---------|--------|
| Statutory interpretation | "What does s 180(1) of the Corporations Act require?" | legislation.gov.au |
| Factual recall | "What is the penalty for insider trading?" | legislation.gov.au |
| Application/reasoning | "Would a director who failed to read board papers breach s 180?" | Legislation, plus leading cases cited by name |
| Procedural knowledge | "What steps must be followed to register a company?" | ASIC guidance |
| Comparative | "How does the Australian Privacy Act differ from GDPR on consent?" | Cross-reference |

### What Makes a Good Evaluation Question

- **Unambiguous**: One clearly correct answer (or a well-defined rubric for open-ended)
- **Jurisdiction-specific**: The answer differs from US/UK/international law
- **Verifiable**: Can be checked against a specific section of legislation or case
- **Representative**: Covers the breadth of tasks your AI tool will perform

## Step 3: Structure as Question-Answer Pairs

### Format A: Multiple Choice (for automated scoring)

```json
{
  "prompt": "Under section 180(1) of the Corporations Act 2001 (Cth), what standard must a director exercise?\nA. Reasonable care and diligence\nB. Utmost good faith\nC. Due skill only\nD. Best endeavours",
  "referenceResponse": "A",
  "category": "directors_duties"
}
```

### Format B: Open-ended (for LLM-as-a-Judge scoring)

```json
{
  "prompt": "Under section 180(1) of the Corporations Act 2001 (Cth), what standard must a director exercise in their duties?",
  "referenceResponse": "A director must exercise their powers and discharge their duties with the degree of care and diligence that a reasonable person would exercise if they were a director of a corporation in the corporation's circumstances and occupied the office held by, and had the same responsibilities within the corporation as, the director.",
  "category": "directors_duties"
}
```

### Format C: Fine-tuning (for Bedrock custom model training)

```json
{
  "system": "You are an Australian legal expert specialising in corporate law.",
  "messages": [
    {"role": "user", "content": "What standard must a director exercise under s 180(1) of the Corporations Act?"},
    {"role": "assistant", "content": "Under section 180(1) of the Corporations Act 2001 (Cth), a director must exercise their powers and discharge their duties with the degree of care and diligence that a reasonable person would exercise if they were a director of a corporation in the corporation's circumstances and occupied the office held by, and had the same responsibilities within the corporation as, the director."}
  ]
}
```

## Step 4: Validate with Domain Experts

> **⚠️ This step is non-negotiable for production use.**

For this proof-of-concept, the dataset was constructed by referencing legislation directly. For a procurement-grade benchmark:

1. **Engage subject matter experts** (lawyers, clinicians, educators) to:
   - Verify answer correctness
   - Confirm questions are representative of real-world tasks
   - Identify gaps in coverage
   - Flag ambiguous or outdated content

2. **Peer review process**: At minimum, two independent reviewers per question

3. **Version and date**: Legislation changes. Tag each item with the date of the source material and review periodically.

## Step 5: Format for Your Evaluation Tool

### AWS Bedrock Model Evaluation (LLM-as-a-Judge)

Bedrock expects JSONL with `prompt` and `referenceResponse` fields:

```jsonl
{"prompt": "...", "referenceResponse": "...", "category": "..."}
```

Upload to S3 and run via the evaluation API (Module 2 shows both paths).

### fmeval (AWS open-source)

fmeval accepts similar JSONL. Install and run locally or on SageMaker:

```bash
pip install fmeval
```

### lm-evaluation-harness (EleutherAI)

For MCQ-style benchmarks, create a YAML task definition:

```yaml
task: au_legal_benchmark
dataset_path: datasets/legal/processed/eval-legal-au.jsonl
output_type: multiple_choice
```

## Recommended Dataset Size

| Purpose | Minimum Items | Ideal |
|---------|--------------|-------|
| Proof of concept | 50 | 100 |
| Internal evaluation | 200 | 500 |
| Procurement-grade benchmark | 500 | 1000+ |
| Published benchmark (peer-reviewed) | 1000+ | 5000+ |

## Reproducibility Checklist

For government procurement, your evaluation dataset should include:

- [ ] Source attribution for every question (Act, section, case citation)
- [ ] Date of source material
- [ ] Expert reviewer names and qualifications
- [ ] Version number and changelog
- [ ] Licensing statement
- [ ] Coverage matrix (which topics/sections are tested)
- [ ] Known limitations and gaps
- [ ] Update schedule (how often will it be refreshed)

## Next Steps

1. Look at the sample set, `legal/processed/eval-legal-au.jsonl`, and its
   [known limitations](#known-limitations-of-the-sample-evaluation-set)
2. Extend it with your own domain-specific questions
3. Deploy the infrastructure: `cd infrastructure/cdk && npx cdk deploy --all`
4. Run the evaluation: `notebooks/Module-2-Evaluation.ipynb`

---

## AI-Assisted Dataset Creation

The manual process above is the gold standard for quality. But it doesn't scale: every new jurisdiction, domain, or regulation requires the same expert-intensive effort from scratch.

An AI-assisted workflow can accelerate dataset creation while keeping expert validation in the loop. The approach uses three conversational phases: **Scope → Research → Create**. You can execute this with any agentic AI assistant that has web research and file generation capabilities (e.g. Amazon Q Developer CLI, or similar tools with access to web search and structured output).

### Phase 1: Scope — Define what you're evaluating

Describe your evaluation need in plain language. The assistant decomposes it into a structured specification.

**Example prompt:**

```
I need to create an evaluation dataset for Australian corporate and regulatory law.
The dataset should test whether foundation models can:

1. Correctly identify and explain statutory provisions from the Corporations Act 2001 (Cth)
2. Correctly state obligations under the Privacy Act 1988 (Cth)
3. Correctly explain consumer protections under the Australian Consumer Law
   (Competition and Consumer Act 2010, Schedule 2)
4. Correctly identify requirements under state succession legislation
   (Succession Act 2006 NSW)

For each area, I need:
- Factual recall questions (what does section X say?)
- Application questions (would scenario Y breach section X?)

Target: 50 evaluation items and 200 training items.
Categories: directors_duties, securities_law, consumer_law, succession_law, privacy_law

Output formats:

Evaluation (Bedrock):
{"prompt": "...", "referenceResponse": "...", "category": "..."}

Training (Bedrock Custom Model Training):
{"system": "You are an Australian legal expert.", "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
```

The assistant should confirm the taxonomy, category distribution, and difficulty mix before proceeding.

### Phase 2: Research — Ground in authoritative sources

Direct the assistant to retrieve actual legislative text rather than generating from memory.

**Example prompt:**

```
For each category, reference answers must be sourced ONLY from primary legislation.
Use these authoritative sources:

- Corporations Act 2001 (Cth): legislation.gov.au
  Sections: 180-184 (directors' duties), 1043A (insider trading), 588G (insolvent trading)
- Privacy Act 1988 (Cth): legislation.gov.au
  Australian Privacy Principles 1-13 (Schedule 1)
- Competition and Consumer Act 2010, Schedule 2 (Australian Consumer Law):
  Sections 18-23 (unconscionable conduct, unfair practices)
- Succession Act 2006 (NSW): legislation.nsw.gov.au
  Part 2 (making of wills)

For each section:
1. Retrieve the actual legislative text (not a summary from memory)
2. Confirm it is current (not repealed or substantially amended)
3. Note the specific subsection numbers that contain the answer

Do NOT generate answers from memory. Every reference answer must quote or closely
paraphrase the legislative text with the section number cited.
```

### Phase 3: Create — Generate the dataset

**Example prompt:**

```
Generate the dataset. For each category, produce:
- 10 evaluation items (50 total across 5 categories)
- 40 training items (200 total across 5 categories)

Rules:
1. Training and evaluation items must have ZERO question overlap
2. Both draw from the same source sections but ask different questions
3. Every reference answer must cite a specific section/subsection number
4. Vary question types: factual recall, interpretation, application to scenario
5. Vary difficulty: straightforward ("what does s.180(1) require?") through to
   complex ("would X constitute unconscionable conduct under s.21?")
6. Output as two JSONL files: eval-legal-au.jsonl and train-legal-au.jsonl

Quality checks before finalising:
- No duplicate questions across eval and train sets
- Every answer cites a specific section number
- Categories are balanced (10 eval items each, 40 training items each)
- No questions that are ambiguous or have multiple defensible answers
- No questions where the answer depends on case law interpretation
  (stick to black-letter statutory provisions for this version)
```

### Expert validation remains non-negotiable

AI-assisted generation produces a high-quality first draft faster than manual authoring. But the output still requires:

1. **Domain expert review** — a qualified practitioner checks every reference answer against the cited provision
2. **Currency check** — legislation changes; confirm all cited sections are current at time of use
3. **Ambiguity audit** — flag any questions where reasonable experts might disagree on the answer
4. **Coverage assessment** — identify gaps in the taxonomy not covered by generated items

The quality guarantee: every reference answer traces to a cited passage in authoritative legislation, not to model memory. The AI accelerates generation; the human guarantees correctness.

### Extending to other domains

The same three-phase workflow applies to any domain. Replace the legislation references:

| Domain | Sources | Example categories |
|--------|---------|-------------------|
| Health | PBS (pbs.gov.au), TGA, RACGP guidelines | drug_interactions, clinical_protocols, scheduling |
| Education | australiancurriculum.edu.au, NESA syllabuses | curriculum_standards, assessment_criteria |
| Finance | APRA prudential standards, ASX listing rules | capital_requirements, disclosure_obligations |

The methodology is jurisdiction-agnostic: same process, different inputs. Australian legal today, Singaporean health tomorrow, Canadian education next month.

---

## Building the Source Corpus (for RAG / grounding)

The evaluation dataset above tests whether a model *knows* the law. The **source
corpus** is the raw legislative text a model can *retrieve* from — the knowledge
base behind the Module 3 RAG experiment (grounding a model instead of, or as well
as, fine-tuning it). Where the eval set is 50 Q&A pairs, the corpus is the full
text of the Acts those questions are drawn from.

### What's in scope

The corpus mirrors exactly the instruments the 50-item eval set cites — a bounded
set of ~12 primary instruments, mapped to evaluation categories in
`datasets/legal/corpus/manifest.json`:

| Instrument | Jurisdiction | Grounds category |
|---|---|---|
| Corporations Act 2001 | Cth | directors_duties, securities_law |
| Fair Work Act 2009 | Cth | employment_law |
| Criminal Code Act 1995 | Cth | criminal_law |
| Privacy Act 1988 | Cth | privacy_law |
| Competition and Consumer Act 2010 (ACL = Sch 2) | Cth | consumer_law |
| Electronic Transactions Act 1999 | Cth | contract_law |
| Administrative Decisions (Judicial Review) Act 1977 | Cth | administrative_law |
| Commonwealth of Australia Constitution Act | Cth | constitutional_law |
| Administrative Appeals Tribunal Act 1975 | Cth | administrative_law |
| Succession Act 2006 | NSW | succession_law |
| Sale of Goods Act 1923 | NSW | contract_law |
| Frustrated Contracts Act 1978 | NSW | contract_law |

> **Corpus scope note:** We ingest the *full text* of each Act, not just the
> sections the eval answers cite. Handing the retriever only the answer sections
> would be teaching to the test; retrieving the right provision from thousands is
> the honest measure of whether grounding works.

### How to build it

Run the collector (Python 3, standard library only — no pip installs needed):

```bash
# Verify every Commonwealth register ID still resolves to the correct in-force
# principal Act (run if downloads start failing — legislation is re-registered):
python3 datasets/legal/scripts/collect-corpus.py --verify

# Download + extract the corpus text to datasets/legal/corpus/text/:
python3 datasets/legal/scripts/collect-corpus.py
```

The collector reads `manifest.json`, resolves each Commonwealth instrument's
latest compilation via the Federal Register OData API
(`api.prod.legislation.gov.au`), downloads the authorised Word compilation(s),
extracts plain text, and writes one `.txt` per Act with a provenance header
(title, register ID, compilation date, licence).

**The corpus text is committed to this repository**, not regenerated — a fresh
clone reproduces the exact bytes every published result was scored against,
and you don't have to re-download 14.5 MB of legislation (or do the
manual NSW step) before Module 5 will run. Each instrument is pinned in
`manifest.json` by compilation number, compilation date and SHA-256.

⚠️ **The collector always fetches the *newest* compilation**, so re-running it
over the committed corpus replaces pinned text with newer law and invalidates the
recorded scores. Run it only when you intend to re-pin, then update the
manifest and re-measure. `--verify` is read-only and safe.

### Why a manifest + collector (not hardcoded URLs)

Register IDs are **not guessable** — a wrong ID is a silent 404. Resolving IDs
against the register API and storing them in a reviewable manifest makes the
corpus reproducible and its provenance auditable (satisfying the reproducibility
checklist above: source attribution, date of source material, licensing).

### Currency and manual steps

- **Currency flag:** the collector marks any instrument that is no longer in
  force. The **Administrative Appeals Tribunal Act 1975 was repealed on 14 Oct
  2024** (replaced by the Administrative Review Tribunal). It is still collected
  for the eval item that references it, but that item should be refreshed in a
  currency review — a live example of why datasets need a review schedule.
- **NSW instruments** (Succession, Sale of Goods, Frustrated Contracts Acts) are
  not on the Commonwealth register; the collector prints manual steps to fetch
  them from `legislation.nsw.gov.au`. See `MANUAL_NSW` in the script.

### Licensing and provenance

Full per-Act provenance — exact compilation number and date, version URL,
retrieval date, SHA-256, and the verified licence position for each source — is in
**[`legal/corpus/SOURCES.md`](legal/corpus/SOURCES.md)**. In short:

- **Commonwealth (9 Acts)** — **CC BY 4.0**, per the Federal
  Register of Legislation's [Terms of use](https://www.legislation.gov.au/terms-of-use).
  Commercial use permitted; attribution required.
- **NSW (3 Acts)** — **CC BY 4.0**, per the NSW Legislation
  website's [Copyright](https://legislation.nsw.gov.au/copyright) page. Attribution:
  "Based on content from the New South Wales Legislation website at 16 September
  2026. For the latest information on New South Wales Government legislation
  please go to https://www.legislation.nsw.gov.au." © State of New South Wales.

All 12 files are therefore CC BY 4.0 and redistributable, commercial use included.

The committed text is a **processed copy, not an authorised version** of the law:
tables of contents are stripped and NSW site chrome trimmed. Cite the official
source, never this corpus.

## Known limitations of the sample evaluation set

- **Every item was checked against the committed legislation.** Five items that
  cited the wrong provision (ids 23, 26, 41, 49 and 50) were corrected. Expect
  the same in your own set: question writers, human or AI, often cite a
  neighbouring section, and a wrong citation turns a correct answer into a
  "wrong" one.
- **Item 46 can't be answered by retrieval.** It asks for the elements of a valid
  contract at Australian common law. The answer comes from case law, which the
  legislation corpus doesn't contain, so it measures what a model already knows,
  and no retrieval configuration can score it.
- **Item 2 (the s1043A insider-trading penalty) is hard on purpose.** Every part of
  the answer is in the corpus, but the penalty row sits away from the section's
  opening words, so models often miss it even when it's retrieved.
- **50 items is a small benchmark.** Scores move by several points between runs
  on identical inputs, so compare configurations with the paired McNemar test the
  notebooks report rather than by the headline score alone.

## Licence of the datasets in this repository

| Files | What they are | Licence |
|---|---|---|
| `legal/corpus/text/*.txt` | Processed copies of 12 Australian Acts | **CC BY 4.0**, from the original publishers. Attribution is in `legal/corpus/SOURCES.md` and `NOTICE`. |
| `legal/processed/eval-legal-au*.jsonl`, `legal/processed/train-legal-au.jsonl` | Questions and answers written for this project about that legislation | **MIT-0**, with the rest of this repository. The answers paraphrase and cite CC BY 4.0 legislation, so the attribution above still applies to anything they reproduce. Case law is cited by name only. |
| `legal/processed/finetune-prerun-results.json` | Model answers and judge scores from one run on Amazon Bedrock | **MIT-0** |

The question and answer sets are a **sample for demonstrating the method**, not
legal advice and not an expert-validated benchmark. Validate your own dataset with
domain experts before relying on its scores (see Step 4).
