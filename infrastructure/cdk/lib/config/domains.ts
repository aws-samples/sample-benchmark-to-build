// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

/** A benchmark domain. Register new ones in bin/benchmark-to-build.ts. */
export interface DomainConfig {
  /** Short identifier used in resource naming */
  id: string;
  name: string;
  description: string;
  /** S3 prefix for dataset storage */
  dataPrefix: string;
  /** Models to evaluate (Bedrock model or inference profile IDs). Keep in step with CANDIDATE_MODELS in notebooks/Module-2-Evaluation.ipynb. */
  candidateModels: string[];
  /** Judge model for LLM-as-a-Judge evaluation. Keep in step with EVALUATOR_MODEL in notebooks/Module-2-Evaluation.ipynb. */
  judgeModel: string;
}

export const LEGAL_DOMAIN: DomainConfig = {
  id: 'legal',
  name: 'Australian Legal',
  description: 'Evaluation against Australian legislation, case law, and legal reasoning',
  dataPrefix: 'legal',
  candidateModels: [
    'us.amazon.nova-pro-v1:0',
    'us.amazon.nova-lite-v1:0',
    'us.amazon.nova-micro-v1:0',
    'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
    'us.anthropic.claude-haiku-4-5-20251001-v1:0',
    'us.meta.llama4-maverick-17b-instruct-v1:0',
    'us.meta.llama3-3-70b-instruct-v1:0',
    'mistral.mistral-large-3-675b-instruct',
    'mistral.ministral-3-14b-instruct',
    'openai.gpt-oss-120b-1:0',
    'openai.gpt-oss-20b-1:0',
    'nvidia.nemotron-super-3-120b',
    'nvidia.nemotron-nano-3-30b',
    'nvidia.nemotron-nano-12b-v2',
  ],
  judgeModel: 'us.anthropic.claude-sonnet-4-6',
};
