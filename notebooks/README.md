# Notebooks

The Jupyter notebooks for the Benchmark-to-Build sample. Run them in order in a
JupyterLab environment (for example SageMaker Unified Studio) after the CDK stacks
are deployed.

| File | Module |
|---|---|
| `Module-1-Build-Dataset.ipynb` | 1: build the jurisdiction-specific evaluation dataset |
| `Module-2-Evaluation.ipynb` | 2: benchmark foundation models against it |
| `Module-3-Fine-Tune.md` | 3 (optional): pointer to the CloudShell fine-tuning steps; no notebook |
| `Module-4-Fine-Tune-Results.ipynb` | 4: compare a fine-tuned model with its base model |
| `Module-5-RAG.ipynb` | 5: ground answers with a Knowledge Base, then add reranking |
| `Module-6-Agentic-Search.ipynb` | 6: agentic retrieval over the legislation corpus |
| `requirements-notebooks.txt` | Python dependencies, installed by each notebook's first cell |

## Notes

- **Module 3 has no notebook.** It fine-tunes Nova Micro from AWS CloudShell; the
  steps are in `docs/MODULE-3-FINE-TUNE.md` (pointer: `Module-3-Fine-Tune.md`). Fine-tuning is available in
  `us-east-1` only.
- **Module 4 reads pre-run results.** It loads
  `datasets/legal/processed/finetune-prerun-results.json` from the dataset bucket,
  so it deploys and scores nothing itself.
- **Module 5 needs the legislation corpus locally** at `datasets/legal/corpus/text/`.
  Module 6 reads it from S3 (`legal/corpus/`) and needs no local copy.
- **Keep `requirements-notebooks.txt` next to the notebooks**: the install cell
  reads it from the working directory.
- **The notebooks resolve every AWS resource from CloudFormation stack outputs**
  (bucket names, role ARNs, Knowledge Base ID). There is nothing to edit by hand.

## Testing

The notebook tests read the `.ipynb` files directly and need only the standard
library:

```bash
# from the repository root
python3 -m unittest discover -s notebooks/tests -p 'test_*.py'
```

Keep outputs cleared before committing a notebook.
