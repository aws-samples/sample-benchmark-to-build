# Module 3: Fine-Tune Nova Micro (optional)

Module 3 has no notebook. Fine-tuning runs from AWS CloudShell, outside the
notebook environment, because the training job takes longer than a notebook
session and Nova Micro fine-tuning is available in `us-east-1` only.

**Steps:** [docs/MODULE-3-FINE-TUNE.md](../docs/MODULE-3-FINE-TUNE.md)

You don't need to run it to continue. Module 4
(`Module-4-Fine-Tune-Results.ipynb`) loads pre-run fine-tuning results that ship
with the datasets. If you deploy a fine-tuned model, it bills until you delete it:
see [docs/CLEANUP.md](../docs/CLEANUP.md).
