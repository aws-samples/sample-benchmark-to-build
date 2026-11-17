#!/usr/bin/env node
// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { DataStack } from '../lib/stacks/data-stack';
import { EvaluationStack } from '../lib/stacks/evaluation-stack';
import { FineTuningStack } from '../lib/stacks/fine-tuning-stack';
import { KnowledgeBaseStack } from '../lib/stacks/knowledge-base-stack';
import { DomainConfig, LEGAL_DOMAIN } from '../lib/config/domains';

const app = new cdk.App();

// Select the domain with `-c domain=<id>` (default: legal). Register new domains here.
const DOMAINS: Record<string, DomainConfig> = { [LEGAL_DOMAIN.id]: LEGAL_DOMAIN };
const domainId: string = app.node.tryGetContext('domain') || 'legal';
const domain = DOMAINS[domainId];
if (!domain) {
  throw new Error(`Unknown domain "${domainId}". Known domains: ${Object.keys(DOMAINS).join(', ')}`);
}

const prefix = `AuBenchmark-${domain.id}`;

// Deploys to your configured region (us-east-1 or us-west-2), else us-east-1.
const env = { region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1' };

const dataStack = new DataStack(app, `${prefix}-Data`, { domain, env });

new EvaluationStack(app, `${prefix}-Evaluation`, {
  domain,
  env,
  datasetBucket: dataStack.datasetBucket,
  resultsBucket: dataStack.resultsBucket,
});

new FineTuningStack(app, `${prefix}-FineTuning`, {
  domain,
  env,
  datasetBucket: dataStack.datasetBucket,
  resultsBucket: dataStack.resultsBucket,
});

new KnowledgeBaseStack(app, `${prefix}-KnowledgeBase`, {
  domain,
  env,
  datasetBucket: dataStack.datasetBucket,
  resultsBucket: dataStack.resultsBucket,
});
