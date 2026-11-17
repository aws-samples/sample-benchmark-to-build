# Module 3 (optional): Fine-tune Nova Micro

⏱ **Estimated time:** 50 minutes (including ~45 minutes training time)

Module 3 has no notebook. It's a set of AWS CloudShell steps that fine-tune Amazon Nova Micro.
You can skip it: Module 4 loads results from a fine-tuning run done with
exactly these steps (`datasets/legal/processed/finetune-prerun-results.json`).

---

## What You'll Learn

- How the 200 training questions are prepared for Amazon Nova fine-tuning
- How to start a managed Bedrock fine-tuning job on Amazon Nova Micro
- How to deploy, test and delete the fine-tuned model without leaving anything billing

---

## Why This Matters

In Module 2 you measured how well Nova Micro answers Australian legal questions (the baseline). The rest of the sample tries three ways to improve that score:

1. **Fine-tuning** (Modules 3 and 4): further train the model on Australian legal questions and answers
2. **Retrieval-augmented generation, or RAG** (Module 5): look up the relevant legislation and give it to the model with each question
3. **Agentic search** (Module 6): let the model search the legislation itself until it finds what it needs

Fine-tuning is often the first approach teams try: if the model doesn't know Australian law, train it on Australian law. It's also the most involved of the three. Here, training on 200 examples takes ~45 minutes, and larger datasets or models can take longer. The trained model also has to be deployed before you can use it. The deployment is billed per token, like the base model, and storing the custom model costs $1.95 a month until you delete it.

To see whether fine-tuning helped, Module 4 scores the fine-tuned model on the same 50 evaluation questions, with the same judge and rubric as Module 2, and compares it with the baseline. None of those 50 questions are in the 200-question training set, so a better score can't come from the model having memorised the answers.

The instructions below show how to reproduce the results in Module 4.

---

## Key Concepts

> **What is Amazon Bedrock Model Customization?**
>
> Amazon Bedrock Model Customization lets you train a foundation model further on your own data, such as with fine-tuning, without managing any servers or GPUs.

> **What is AWS CloudFormation?**
>
> AWS CloudFormation is AWS's infrastructure-as-code service. It creates and manages AWS resources from a template.

**Supervised fine-tuning (SFT)** further trains a model on example questions and answers, adjusting it to produce answers like the examples.

**Key concepts:**

- **What fine-tuning learns**: Patterns that repeat across the examples, such as tone, structure and format. Each legal fact appears in only one or two examples, so the model doesn't reliably learn it.
- **When to use it**: When the model doesn't present it the way you need, for example:
  - **Format**: it writes long essays when you need a one-line conclusion followed by the supporting section
  - **Style and tone**: it sounds casual or hedges every answer when you need the plain, precise language a lawyer would use
  - **Conventions**: it doesn't cite the Act and section, or gives legal penalties in dollars instead of penalty units
  - **Consistency**: it answers the same kind of question differently each time, and you need a predictable structure
- **When not to use it**: When the model is missing facts or knowledge of the law itself, such as what a particular section says or what the current penalty is. Each fact appears in too few examples for the model to learn it reliably, and when the law changes you'd have to retrain.
- **Epochs**: How many times training passes over the 200 examples. In this module, we use 3.
- **Deployment**: A trained custom model has to be deployed before you can call it, and the deployment is billed per token used. Storing the custom model itself costs $1.95 a month until you delete it.

---

## Where to Run This: AWS CloudShell

Run everything in **AWS CloudShell**, a terminal in the AWS console. It's free, already signed in as you, and has the AWS CLI, Python and `boto3` installed.

Each step below is one block you paste into CloudShell. Every block finds what it needs (the stack's outputs, the latest job, your deployment) for itself, so **it doesn't matter if CloudShell times out** during the 45 minutes of training: open it again and carry on with the next step.

You need an AWS account where you can create an S3 bucket and an IAM role, and call Bedrock's fine-tuning and deployment APIs.

---

## Step 1: Open CloudShell and Upload Two Files

1. From this repository, download `infrastructure/cloudformation/fine-tune.yaml` and
   `datasets/legal/processed/train-legal-au.jsonl` to your computer.

2. In the AWS console, switch to **US East (N. Virginia) us-east-1**, then open **CloudShell** from the toolbar. Nova Micro fine-tuning is only available in us-east-1. This module uses its own template and bucket, independent of the other stacks.
3. Choose **Actions → Upload file** and upload `fine-tune.yaml`. Repeat for `train-legal-au.jsonl`
4. Check both are there:

```bash
ls fine-tune.yaml train-legal-au.jsonl
```

The training data is 200 questions on Australian law that share none with the 50 evaluation questions.

---

## Step 2: Deploy the Fine-Tuning Template

The template creates an S3 bucket for the training data and the job's output, and the IAM role Bedrock assumes to read and write them. Only fine-tuning jobs in your account can assume the role.

```bash
aws cloudformation deploy --template-file fine-tune.yaml --stack-name benchmark-to-build-fine-tune --capabilities CAPABILITY_NAMED_IAM --region us-east-1
```

**Watch for:** `Successfully created/updated stack`.

---

## Step 3: Convert the Training Data and Upload It

Nova fine-tuning wants each system prompt and message as a list of `{"text": ...}` objects, plus a `schemaVersion`. It also rejects files containing reserved strings such as `User:` or `[EOS]`, so this checks for those first: a format error fails the job about 10 minutes in.

```bash
python3 - <<'EOF'
import boto3, json, time
from datetime import datetime, timezone
REGION, STACK = "us-east-1", "benchmark-to-build-fine-tune"
JOB_PREFIX, DEPLOYMENT_PREFIX = "nova-micro-legal-sft-", "nova-micro-au-legal-own-"
out = {o["OutputKey"]: o["OutputValue"] for o in boto3.client("cloudformation", region_name=REGION)
       .describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
BUCKET, ROLE_ARN = out["FineTuneBucketName"], out["BedrockTrainingRoleArn"]
s3, bedrock = boto3.client("s3", region_name=REGION), boto3.client("bedrock", region_name=REGION)
def latest_job():
    jobs = bedrock.list_model_customization_jobs(nameContains=JOB_PREFIX, sortBy="CreationTime",
                                                 sortOrder="Descending")["modelCustomizationJobSummaries"]
    return bedrock.get_model_customization_job(jobIdentifier=jobs[0]["jobArn"]) if jobs else None
def my_deployments():
    return [d for d in bedrock.list_custom_model_deployments()["modelDeploymentSummaries"]
            if d["customModelDeploymentName"].startswith(DEPLOYMENT_PREFIX)]

with open("train-legal-au.jsonl") as f:
    train = [json.loads(line) for line in f if line.strip()]
RESERVED = ("User:", "Bot:", "Assistant:", "System:", "<image>", "<video>", "[EOS]")
bad = [i for i, item in enumerate(train)
       if any(k in t for k in RESERVED for t in [item["system"], *(m["content"] for m in item["messages"])])]
assert not bad, f"Reserved strings in items {bad[:5]}"
nova = [{"schemaVersion": "bedrock-conversation-2024",
         "system": [{"text": item["system"]}],
         "messages": [{"role": m["role"], "content": [{"text": m["content"]}]} for m in item["messages"]]}
        for item in train]
s3.put_object(Bucket=BUCKET, Key="training/train-legal-au-nova.jsonl",
              Body="\n".join(json.dumps(r) for r in nova).encode())
print(f"Uploaded {len(nova)} training items to s3://{BUCKET}/training/")
EOF
```

**Watch for:** `Uploaded 200 training items`.

---

## Step 4: Start the Fine-Tuning Job

These are the settings behind Module 4's results. **Run this once:** each run starts another billable job.

```bash
python3 - <<'EOF'
import boto3, json, time
from datetime import datetime, timezone
REGION, STACK = "us-east-1", "benchmark-to-build-fine-tune"
JOB_PREFIX, DEPLOYMENT_PREFIX = "nova-micro-legal-sft-", "nova-micro-au-legal-own-"
out = {o["OutputKey"]: o["OutputValue"] for o in boto3.client("cloudformation", region_name=REGION)
       .describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
BUCKET, ROLE_ARN = out["FineTuneBucketName"], out["BedrockTrainingRoleArn"]
s3, bedrock = boto3.client("s3", region_name=REGION), boto3.client("bedrock", region_name=REGION)
def latest_job():
    jobs = bedrock.list_model_customization_jobs(nameContains=JOB_PREFIX, sortBy="CreationTime",
                                                 sortOrder="Descending")["modelCustomizationJobSummaries"]
    return bedrock.get_model_customization_job(jobIdentifier=jobs[0]["jobArn"]) if jobs else None
def my_deployments():
    return [d for d in bedrock.list_custom_model_deployments()["modelDeploymentSummaries"]
            if d["customModelDeploymentName"].startswith(DEPLOYMENT_PREFIX)]

stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
bedrock.create_model_customization_job(
    jobName=f"{JOB_PREFIX}{stamp}",
    customModelName=f"nova-micro-au-legal-{stamp}",
    baseModelIdentifier="amazon.nova-micro-v1:0:128k",
    customizationType="FINE_TUNING",
    trainingDataConfig={"s3Uri": f"s3://{BUCKET}/training/train-legal-au-nova.jsonl"},
    outputDataConfig={"s3Uri": f"s3://{BUCKET}/output/{stamp}/"},
    roleArn=ROLE_ARN,
    hyperParameters={"epochCount": "3", "batchSize": "1", "learningRate": "0.00001"},
)
print(f"Started {JOB_PREFIX}{stamp}. Training takes about 45 minutes.")
EOF
```

---

## Step 5: Check Whether Training Has Finished

Run this whenever you like. You can close CloudShell while you wait.

```bash
python3 - <<'EOF'
import boto3, json, time
from datetime import datetime, timezone
REGION, STACK = "us-east-1", "benchmark-to-build-fine-tune"
JOB_PREFIX, DEPLOYMENT_PREFIX = "nova-micro-legal-sft-", "nova-micro-au-legal-own-"
out = {o["OutputKey"]: o["OutputValue"] for o in boto3.client("cloudformation", region_name=REGION)
       .describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
BUCKET, ROLE_ARN = out["FineTuneBucketName"], out["BedrockTrainingRoleArn"]
s3, bedrock = boto3.client("s3", region_name=REGION), boto3.client("bedrock", region_name=REGION)
def latest_job():
    jobs = bedrock.list_model_customization_jobs(nameContains=JOB_PREFIX, sortBy="CreationTime",
                                                 sortOrder="Descending")["modelCustomizationJobSummaries"]
    return bedrock.get_model_customization_job(jobIdentifier=jobs[0]["jobArn"]) if jobs else None
def my_deployments():
    return [d for d in bedrock.list_custom_model_deployments()["modelDeploymentSummaries"]
            if d["customModelDeploymentName"].startswith(DEPLOYMENT_PREFIX)]

job = latest_job()
print(f"{job['jobName']}: {job['status']}" if job else "No job found. Run Step 4.")
EOF
```

**Watch for:** `Completed`. `InProgress` is normal for about 45 minutes. You can also follow it in the Bedrock console under **Custom models → Training jobs**.

---

## Step 6: Deploy the Fine-Tuned Model

The finished job produces a custom model. This deploys it on demand and waits until it's `Active`, which takes a few minutes.

```bash
python3 - <<'EOF'
import boto3, json, time
from datetime import datetime, timezone
REGION, STACK = "us-east-1", "benchmark-to-build-fine-tune"
JOB_PREFIX, DEPLOYMENT_PREFIX = "nova-micro-legal-sft-", "nova-micro-au-legal-own-"
out = {o["OutputKey"]: o["OutputValue"] for o in boto3.client("cloudformation", region_name=REGION)
       .describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
BUCKET, ROLE_ARN = out["FineTuneBucketName"], out["BedrockTrainingRoleArn"]
s3, bedrock = boto3.client("s3", region_name=REGION), boto3.client("bedrock", region_name=REGION)
def latest_job():
    jobs = bedrock.list_model_customization_jobs(nameContains=JOB_PREFIX, sortBy="CreationTime",
                                                 sortOrder="Descending")["modelCustomizationJobSummaries"]
    return bedrock.get_model_customization_job(jobIdentifier=jobs[0]["jobArn"]) if jobs else None
def my_deployments():
    return [d for d in bedrock.list_custom_model_deployments()["modelDeploymentSummaries"]
            if d["customModelDeploymentName"].startswith(DEPLOYMENT_PREFIX)]

job = latest_job()
assert job and job["status"] == "Completed", "Training hasn't finished yet. Re-run Step 5."
if my_deployments():
    print("Already deployed:", my_deployments()[0]["customModelDeploymentName"])
else:
    arn = bedrock.create_custom_model_deployment(
        modelDeploymentName=DEPLOYMENT_PREFIX + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        modelArn=job["outputModelArn"])["customModelDeploymentArn"]
    while bedrock.get_custom_model_deployment(customModelDeploymentIdentifier=arn)["status"] != "Active":
        time.sleep(30)
    print("Deployment Active. Step 8 deletes it.")
EOF
```

> **Delete the Deployment When You're Done**
>
> Inference is billed per token, but anyone with access to the account can invoke the deployment until it's deleted. Do Step 8 as soon as you've finished, even if Step 7 fails.

---

## Step 7: Ask It a Question

Change `QUESTION` to try others.

```bash
python3 - <<'EOF'
import boto3, json, time
from datetime import datetime, timezone
REGION, STACK = "us-east-1", "benchmark-to-build-fine-tune"
JOB_PREFIX, DEPLOYMENT_PREFIX = "nova-micro-legal-sft-", "nova-micro-au-legal-own-"
out = {o["OutputKey"]: o["OutputValue"] for o in boto3.client("cloudformation", region_name=REGION)
       .describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
BUCKET, ROLE_ARN = out["FineTuneBucketName"], out["BedrockTrainingRoleArn"]
s3, bedrock = boto3.client("s3", region_name=REGION), boto3.client("bedrock", region_name=REGION)
def latest_job():
    jobs = bedrock.list_model_customization_jobs(nameContains=JOB_PREFIX, sortBy="CreationTime",
                                                 sortOrder="Descending")["modelCustomizationJobSummaries"]
    return bedrock.get_model_customization_job(jobIdentifier=jobs[0]["jobArn"]) if jobs else None
def my_deployments():
    return [d for d in bedrock.list_custom_model_deployments()["modelDeploymentSummaries"]
            if d["customModelDeploymentName"].startswith(DEPLOYMENT_PREFIX)]

QUESTION = "What does section 1041H of the Corporations Act 2001 prohibit in relation to financial services?"
deployment = my_deployments()[0]
reply = boto3.client("bedrock-runtime", region_name=REGION).converse(
    modelId=deployment["customModelDeploymentArn"],
    messages=[{"role": "user", "content": [{"text": QUESTION}]}],
    inferenceConfig={"maxTokens": 512, "temperature": 0.0})
print(reply["output"]["message"]["content"][0]["text"])
EOF
```

To score it on all 50 questions with the same rubric and judge, deploy the rest of the sample (see the main README), then add the deployment's ARN to `CANDIDATE_MODELS` in `notebooks/Module-2-Evaluation.ipynb`.

---

## Step 8: Delete the Deployment

```bash
python3 - <<'EOF'
import boto3, json, time
from datetime import datetime, timezone
REGION, STACK = "us-east-1", "benchmark-to-build-fine-tune"
JOB_PREFIX, DEPLOYMENT_PREFIX = "nova-micro-legal-sft-", "nova-micro-au-legal-own-"
out = {o["OutputKey"]: o["OutputValue"] for o in boto3.client("cloudformation", region_name=REGION)
       .describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
BUCKET, ROLE_ARN = out["FineTuneBucketName"], out["BedrockTrainingRoleArn"]
s3, bedrock = boto3.client("s3", region_name=REGION), boto3.client("bedrock", region_name=REGION)
def latest_job():
    jobs = bedrock.list_model_customization_jobs(nameContains=JOB_PREFIX, sortBy="CreationTime",
                                                 sortOrder="Descending")["modelCustomizationJobSummaries"]
    return bedrock.get_model_customization_job(jobIdentifier=jobs[0]["jobArn"]) if jobs else None
def my_deployments():
    return [d for d in bedrock.list_custom_model_deployments()["modelDeploymentSummaries"]
            if d["customModelDeploymentName"].startswith(DEPLOYMENT_PREFIX)]

for d in my_deployments():
    bedrock.delete_custom_model_deployment(customModelDeploymentIdentifier=d["customModelDeploymentArn"])
    print("Deleted", d["customModelDeploymentName"])
time.sleep(5)
print("Still deployed:", [d["customModelDeploymentName"] for d in my_deployments()] or "nothing")
EOF
```

**Watch for:** `Still deployed: nothing`. The custom model is kept, so you can deploy it again later by re-running Step 6. Storing it costs $1.95 a month until Step 9 deletes it.

---

## Step 9: Delete the Custom Model and Template

The custom model costs **$1.95 a month** to store until you delete it. This step deletes only custom models whose names start with `nova-micro-au-legal-` (the name Step 4 gives yours), then deletes the fine-tuning stack, which empties and deletes its bucket. Do Step 8 first: a model can't be deleted while it's deployed.

First, list the models it will delete:

```bash
aws bedrock list-custom-models --name-contains nova-micro-au-legal- --region us-east-1 --query "modelSummaries[].modelName"
```

> **Sharing an Account?**
>
> If someone else in this account also ran this module, their models have the same prefix. Check that every name listed is yours. If not, delete yours one at a time with `aws bedrock delete-custom-model --model-identifier <name> --region us-east-1`, and skip the model loop below.

```bash
python3 - <<'EOF'
import boto3
REGION, STACK, MODEL_PREFIX = "us-east-1", "benchmark-to-build-fine-tune", "nova-micro-au-legal-"
bedrock = boto3.client("bedrock", region_name=REGION)
cfn = boto3.client("cloudformation", region_name=REGION)
for m in bedrock.list_custom_models(nameContains=MODEL_PREFIX)["modelSummaries"]:
    if m["modelName"].startswith(MODEL_PREFIX):
        bedrock.delete_custom_model(modelIdentifier=m["modelArn"])
        print("Deleted model", m["modelName"])
cfn.delete_stack(StackName=STACK)
cfn.get_waiter("stack_delete_complete").wait(StackName=STACK)
print("Deleted stack", STACK)
EOF
```

**Watch for:** `Deleted stack benchmark-to-build-fine-tune`. The fine-tuning jobs stay listed in Bedrock as a record; they don't bill.

---

## Key Takeaways

- Managed fine-tuning needs no training infrastructure, so it's cheap to try.
- Fine-tuning changes how a model answers more reliably than what it knows.
- Training and evaluation sets must not share questions.
- Training is a one-off cost; storing the custom model bills monthly until you delete it, and its deployment is billed per token.

---

## Resources

- [Customize your model to improve its performance for your use case](https://docs.aws.amazon.com/bedrock/latest/userguide/custom-models.html)
- [Prepare data for fine-tuning your models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-customization-prepare.html)
- [Preparing data for supervised fine-tuning: Formatting and quality](https://aws.amazon.com/blogs/machine-learning/preparing-data-for-supervised-fine-tuning-part-1-formatting-and-quality/)
- [Model customization, RAG, or both: A case study with Amazon Nova](https://aws.amazon.com/blogs/machine-learning/model-customization-rag-or-both-a-case-study-with-amazon-nova/)
- [AWS CloudFormation Documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/)

---

## Next Steps

Open `notebooks/Module-4-Fine-Tune-Results.ipynb` to see how the fine-tuned model scored.
