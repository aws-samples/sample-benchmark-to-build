// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as s3vectors from 'aws-cdk-lib/aws-s3vectors';
import { Construct } from 'constructs';
import { DomainConfig } from '../config/domains';

export interface KnowledgeBaseStackProps extends cdk.StackProps {
  domain: DomainConfig;
  /** Bucket whose `{domain}/corpus/` prefix holds the source legislation text. */
  datasetBucket: s3.IBucket;
  /** Bucket holding `results/cells/`, where the notebooks share scores. */
  resultsBucket: s3.IBucket;
}

/**
 * Bedrock Knowledge Base on S3 Vectors for the Module 5 and 6 retrieval
 * experiments. S3 Vectors has no idle cost, unlike OpenSearch Serverless.
 */
export class KnowledgeBaseStack extends cdk.Stack {
  public readonly knowledgeBase: bedrock.CfnKnowledgeBase;
  public readonly dataSource: bedrock.CfnDataSource;

  // The vector index dimension must match the embedding dimension.
  private static readonly EMBEDDING_MODEL = 'amazon.titan-embed-text-v2:0';
  private static readonly EMBEDDING_DIMENSION = 1024;

  // The only reranker offered in us-east-1. Keep in step with RERANK_MODEL_ID
  // in notebooks/Module-5-RAG.ipynb.
  private static readonly RERANK_MODEL = 'cohere.rerank-v3-5:0';

  /**
   * Drives Module 6's retrieval loop; the model under test still writes the
   * answer. Keep in step with ORCHESTRATOR_MODEL in
   * notebooks/Module-6-Agentic-Search.ipynb.
   */
  private static readonly AGENT_ORCHESTRATOR_MODEL = 'amazon.nova-pro-v1:0';

  /**
   * The only results-bucket prefixes the RAG notebooks need. Other prefixes are
   * granted by NotebookEvalPolicy and NotebookFineTuningPolicy. Keep in step
   * with CELL_RESULTS_PREFIX and HANDOFF_DEPLOYMENT_KEY in
   * notebooks/Module-5-RAG.ipynb.
   */
  private static readonly RESULTS_PREFIXES = ['results/cells/', 'handoff/'];

  constructor(scope: Construct, id: string, props: KnowledgeBaseStackProps) {
    super(scope, id, props);

    const embeddingModelArn =
      `arn:aws:bedrock:${this.region}::foundation-model/${KnowledgeBaseStack.EMBEDDING_MODEL}`;

    // S3 Vectors names must be lowercase.
    const vectorBucket = new s3vectors.CfnVectorBucket(this, 'VectorBucket', {
      vectorBucketName: `aubenchmark-${props.domain.id}-vectors-${this.account}`,
    });

    const vectorIndex = new s3vectors.CfnIndex(this, 'VectorIndex', {
      indexName: `${props.domain.id}-legal-index`,
      vectorBucketArn: vectorBucket.attrVectorBucketArn,
      dataType: 'float32',
      dimension: KnowledgeBaseStack.EMBEDDING_DIMENSION,
      distanceMetric: 'cosine',
      // S3 Vectors caps filterable metadata at 2048 bytes per vector. Legislative
      // chunks exceed that, so ingestion fails unless Bedrock's keys are
      // non-filterable.
      metadataConfiguration: {
        nonFilterableMetadataKeys: ['AMAZON_BEDROCK_TEXT', 'AMAZON_BEDROCK_METADATA'],
      },
    });
    vectorIndex.addResourceDependency(vectorBucket);

    const kbRole = new iam.Role(this, 'KnowledgeBaseRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com', {
        conditions: { StringEquals: { 'aws:SourceAccount': this.account } },
      }),
      description: `Service role for the Bedrock Knowledge Base - ${props.domain.name}`,
    });

    kbRole.addToPolicy(new iam.PolicyStatement({
      sid: 'InvokeEmbeddingModel',
      effect: iam.Effect.ALLOW,
      actions: ['bedrock:InvokeModel'],
      resources: [embeddingModelArn],
    }));

    kbRole.addToPolicy(new iam.PolicyStatement({
      sid: 'ReadCorpusFromS3',
      effect: iam.Effect.ALLOW,
      actions: ['s3:ListBucket'],
      resources: [props.datasetBucket.bucketArn],
    }));
    kbRole.addToPolicy(new iam.PolicyStatement({
      sid: 'GetCorpusObjects',
      effect: iam.Effect.ALLOW,
      actions: ['s3:GetObject'],
      resources: [`${props.datasetBucket.bucketArn}/${props.domain.dataPrefix}/corpus/*`],
    }));

    // S3 Vectors uses its own IAM namespace (s3vectors:*), not s3:*.
    kbRole.addToPolicy(new iam.PolicyStatement({
      sid: 'AccessVectorStore',
      effect: iam.Effect.ALLOW,
      actions: [
        's3vectors:GetIndex',
        's3vectors:PutVectors',
        's3vectors:GetVectors',
        's3vectors:ListVectors',
        's3vectors:DeleteVectors',
        's3vectors:QueryVectors',
      ],
      resources: [vectorBucket.attrVectorBucketArn, vectorIndex.attrIndexArn],
    }));

    this.knowledgeBase = new bedrock.CfnKnowledgeBase(this, 'KnowledgeBase', {
      name: `AuBenchmark-${props.domain.id}-legal-kb`,
      roleArn: kbRole.roleArn,
      description: `Australian legislation corpus for RAG - ${props.domain.name}`,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn,
          embeddingModelConfiguration: {
            bedrockEmbeddingModelConfiguration: {
              dimensions: KnowledgeBaseStack.EMBEDDING_DIMENSION,
              embeddingDataType: 'FLOAT32',
            },
          },
        },
      },
      storageConfiguration: {
        type: 'S3_VECTORS',
        s3VectorsConfiguration: {
          vectorBucketArn: vectorBucket.attrVectorBucketArn,
          indexArn: vectorIndex.attrIndexArn,
        },
      },
    });
    this.knowledgeBase.node.addDependency(vectorIndex);
    this.knowledgeBase.node.addDependency(kbRole);

    const chunkMaxTokens = 1000;
    const chunkOverlapPercent = 20;

    this.dataSource = new bedrock.CfnDataSource(this, 'CorpusDataSource', {
      knowledgeBaseId: this.knowledgeBase.attrKnowledgeBaseId,
      // Chunking is immutable, so changing it replaces this resource, and the
      // replacement is created before the original is deleted. The chunk size is
      // in the name so the two don't collide on Bedrock's unique-name check.
      name: `${props.domain.id}-legislation-corpus-fs${chunkMaxTokens}`,
      dataSourceConfiguration: {
        type: 'S3',
        s3Configuration: {
          bucketArn: props.datasetBucket.bucketArn,
          inclusionPrefixes: [`${props.domain.dataPrefix}/corpus/`],
        },
      },
      // Bedrock's 300-token default splits a section from its subsections; ~1000
      // tokens holds a whole section. HIERARCHICAL chunking can exceed the S3
      // Vectors metadata cap. Changing this needs a full re-ingestion.
      vectorIngestionConfiguration: {
        chunkingConfiguration: {
          chunkingStrategy: 'FIXED_SIZE',
          fixedSizeChunkingConfiguration: {
            maxTokens: chunkMaxTokens,
            overlapPercentage: chunkOverlapPercent,
          },
        },
      },
      dataDeletionPolicy: 'DELETE',
    });

    // For Modules 5 and 6. Attach alongside the eval and fine-tuning policies.
    const notebookPolicy = new iam.ManagedPolicy(this, 'NotebookRagPolicy', {
      description: `Permissions for notebooks to ingest and query the KB - ${props.domain.name}`,
      statements: [
        new iam.PolicyStatement({
          sid: 'ManageIngestionJobs',
          effect: iam.Effect.ALLOW,
          actions: [
            'bedrock:StartIngestionJob',
            'bedrock:GetIngestionJob',
            'bedrock:ListIngestionJobs',
            'bedrock:StopIngestionJob',
          ],
          resources: [this.knowledgeBase.attrKnowledgeBaseArn],
        }),
        new iam.PolicyStatement({
          sid: 'QueryKnowledgeBase',
          effect: iam.Effect.ALLOW,
          actions: ['bedrock:Retrieve', 'bedrock:RetrieveAndGenerate'],
          resources: [this.knowledgeBase.attrKnowledgeBaseArn],
        }),
        new iam.PolicyStatement({
          // bedrock:Rerank has no resource-level permissions, so it must be on "*";
          // any narrower resource silently never matches. The model is pinned on
          // InvokeModel below instead. See
          // docs.aws.amazon.com/bedrock/latest/userguide/rerank-prereq.html
          sid: 'RerankRetrievedPassages',
          effect: iam.Effect.ALLOW,
          actions: ['bedrock:Rerank'],
          resources: ['*'],
        }),
        new iam.PolicyStatement({
          // Rerank calls the reranker through InvokeModel, which can be scoped.
          sid: 'InvokeRerankModel',
          effect: iam.Effect.ALLOW,
          actions: ['bedrock:InvokeModel'],
          resources: [
            `arn:aws:bedrock:${this.region}::foundation-model/${KnowledgeBaseStack.RERANK_MODEL}`,
          ],
        }),
        new iam.PolicyStatement({
          // Module 6's agent model. A `us.` inference profile authorises against
          // both the profile ARN and the foundation model in whichever region it
          // routes to, so both are needed; the region is a wildcard because that
          // set can change. Strands streams by default, hence both actions.
          sid: 'InvokeAgentOrchestratorModel',
          effect: iam.Effect.ALLOW,
          actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
          resources: [
            `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/us.${KnowledgeBaseStack.AGENT_ORCHESTRATOR_MODEL}`,
            `arn:aws:bedrock:*::foundation-model/${KnowledgeBaseStack.AGENT_ORCHESTRATOR_MODEL}`,
          ],
        }),
        new iam.PolicyStatement({
          // Scoped to RESULTS_PREFIXES, not the whole bucket, so users in a shared
          // account can't overwrite each other's scores.
          sid: 'ReadWriteCellResults',
          effect: iam.Effect.ALLOW,
          actions: ['s3:GetObject', 's3:PutObject'],
          resources: KnowledgeBaseStack.RESULTS_PREFIXES.map(
            (p) => `${props.resultsBucket.bucketArn}/${p}*`,
          ),
        }),
        new iam.PolicyStatement({
          // ListBucket is bucket-level, so the prefix is limited by condition.
          sid: 'ListCellResultsPrefixes',
          effect: iam.Effect.ALLOW,
          actions: ['s3:ListBucket'],
          resources: [props.resultsBucket.bucketArn],
          conditions: {
            StringLike: {
              's3:prefix': KnowledgeBaseStack.RESULTS_PREFIXES.map((p) => `${p}*`),
            },
          },
        }),
        new iam.PolicyStatement({
          sid: 'UploadCorpusToDatasetBucket',
          effect: iam.Effect.ALLOW,
          actions: ['s3:PutObject', 's3:GetObject', 's3:ListBucket'],
          resources: [
            props.datasetBucket.bucketArn,
            `${props.datasetBucket.bucketArn}/${props.domain.dataPrefix}/corpus/*`,
          ],
        }),
      ],
    });

    // The notebooks read these outputs.
    new cdk.CfnOutput(this, 'KnowledgeBaseId', {
      value: this.knowledgeBase.attrKnowledgeBaseId,
      description: 'Bedrock Knowledge Base ID for RAG retrieval (Modules 5 and 6)',
    });
    new cdk.CfnOutput(this, 'NotebookRagPolicyArn', {
      value: notebookPolicy.managedPolicyArn,
      description: 'Attach this policy to your SageMaker notebook execution role for Modules 5 and 6',
    });
    new cdk.CfnOutput(this, 'DataSourceId', {
      value: this.dataSource.attrDataSourceId,
      description: 'KB data source ID - pass to StartIngestionJob after uploading the corpus',
    });
    new cdk.CfnOutput(this, 'VectorBucketName', {
      value: vectorBucket.ref,
      description: 'S3 Vectors bucket backing the knowledge base',
    });
  }
}
