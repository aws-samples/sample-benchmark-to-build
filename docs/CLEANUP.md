# Cleanup

Most of this sample costs little or nothing when idle. This page lists what does,
and how to remove everything.

## What can keep costing money

| Resource | Created by | Idle cost | Action |
|---|---|---|---|
| Custom model deployment | You, if you deploy a fine-tuned model yourself | Inference is billed per token. Delete it when you're done so nothing can call it. | **Delete** |
| Fine-tuned custom model | Module 3, if you run it | Monthly model storage | Delete if you no longer need it |
| Provisioned throughput | Not created by this sample | Billed hourly for its whole term | Delete if you find one you don't need |
| S3 buckets (datasets, results) and the S3 Vectors index | CDK stacks or the CloudFormation template | Storage only, a few cents for this data | Removed by teardown below |
| Bedrock Knowledge Base | CDK stacks or the CloudFormation template | None when idle | Removed by teardown below |
| IAM roles and policies | CDK stacks or the CloudFormation template | None | Removed by teardown below |
| Bedrock Evaluations and Inspect AI runs | The notebooks | Per run only | Nothing to clean up |

See [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) for current
rates.

The notebooks never create a model deployment: Module 4 reads pre-run results.

## Check for model deployments and provisioned throughput

Both commands only list resources:

```bash
aws bedrock list-custom-model-deployments --region us-east-1
aws bedrock list-provisioned-model-throughputs --region us-east-1
```

An empty `modelDeploymentSummaries` / `provisionedModelSummaries` list means there
is nothing to remove. To delete a deployment:

```bash
aws bedrock delete-custom-model-deployment \
  --custom-model-deployment-identifier <arn> --region us-east-1
```

Deleting a deployment does not delete the fine-tuned model, so you can deploy it
again later. In the console, see **Amazon Bedrock → Custom models → Deployments**,
with the region set to **us-east-1**.

## Tear down the infrastructure

Delete any model deployments first. They're created outside CloudFormation, so
stack deletion doesn't remove them.

If you deployed with CDK:

```bash
cd infrastructure/cdk
npx cdk destroy --all
```

If you deployed with `infrastructure/cloudformation/benchmark-to-build.yaml`, delete that stack in
the CloudFormation console. If you ran Module 3, also delete the
`benchmark-to-build-fine-tune` stack (from `fine-tune.yaml`), which empties its training bucket on deletion.

To delete a fine-tuned model you no longer need:

```bash
aws bedrock list-custom-models --region us-east-1
aws bedrock delete-custom-model --model-identifier <model-arn> --region us-east-1
```
