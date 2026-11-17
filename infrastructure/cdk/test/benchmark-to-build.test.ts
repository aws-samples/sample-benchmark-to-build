// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { DataStack } from '../lib/stacks/data-stack';
import { EvaluationStack } from '../lib/stacks/evaluation-stack';
import { FineTuningStack } from '../lib/stacks/fine-tuning-stack';
import { KnowledgeBaseStack } from '../lib/stacks/knowledge-base-stack';
import { LEGAL_DOMAIN } from '../lib/config/domains';

describe('Australian Benchmark Stacks', () => {
  const app = new cdk.App();
  const domain = LEGAL_DOMAIN;

  const dataStack = new DataStack(app, 'TestData', { domain });
  const evalStack = new EvaluationStack(app, 'TestEval', {
    domain,
    datasetBucket: dataStack.datasetBucket,
    resultsBucket: dataStack.resultsBucket,
  });
  const ftStack = new FineTuningStack(app, 'TestFT', {
    domain,
    datasetBucket: dataStack.datasetBucket,
    resultsBucket: dataStack.resultsBucket,
  });
  const kbStack = new KnowledgeBaseStack(app, 'TestKB', {
    domain,
    datasetBucket: dataStack.datasetBucket,
    resultsBucket: dataStack.resultsBucket,
  });

  test('DataStack creates two S3 buckets', () => {
    const template = Template.fromStack(dataStack);
    template.resourceCountIs('AWS::S3::Bucket', 2);
  });

  test('EvaluationStack creates Bedrock evaluation role', () => {
    const template = Template.fromStack(evalStack);
    template.hasResourceProperties('AWS::IAM::Role', {
      AssumeRolePolicyDocument: {
        Statement: [{
          Effect: 'Allow',
          Principal: { Service: 'bedrock.amazonaws.com' },
        }],
      },
    });
  });

  describe('DataStack bucket hardening', () => {
    const template = Template.fromStack(dataStack);
    const buckets = () => Object.values(template.findResources('AWS::S3::Bucket')) as any[];

    test('every bucket blocks all public access', () => {
      for (const b of buckets()) {
        expect(b.Properties.PublicAccessBlockConfiguration).toEqual({
          BlockPublicAcls: true,
          BlockPublicPolicy: true,
          IgnorePublicAcls: true,
          RestrictPublicBuckets: true,
        });
      }
    });

    test('every bucket disables ACLs (BucketOwnerEnforced)', () => {
      for (const b of buckets()) {
        expect(b.Properties.OwnershipControls).toEqual({
          Rules: [{ ObjectOwnership: 'BucketOwnerEnforced' }],
        });
      }
    });

    test('every bucket denies requests that are not over TLS', () => {
      const policies = Object.values(template.findResources('AWS::S3::BucketPolicy')) as any[];
      expect(policies).toHaveLength(2);
      for (const p of policies) {
        const denyTls = (p.Properties.PolicyDocument.Statement as any[]).find(
          (s) => s.Effect === 'Deny' && s.Condition?.Bool?.['aws:SecureTransport'] === 'false',
        );
        expect(denyTls).toBeDefined();
      }
    });
  });

  describe('FineTuningStack', () => {
    const template = Template.fromStack(ftStack);

    test('creates no SageMaker training role (nothing uses one)', () => {
      const roles = Object.values(template.findResources('AWS::IAM::Role')) as any[];
      const trusted = roles.flatMap((r) =>
        (r.Properties.AssumeRolePolicyDocument.Statement as any[]).map((s) => s.Principal?.Service),
      );
      expect(trusted).not.toContain('sagemaker.amazonaws.com');
      expect(JSON.stringify(roles)).not.toContain('AmazonSageMakerFullAccess');
    });

    test('training role trust is scoped to this account\'s customization jobs', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        AssumeRolePolicyDocument: {
          Statement: [Match.objectLike({
            Principal: { Service: 'bedrock.amazonaws.com' },
            Condition: {
              StringEquals: { 'aws:SourceAccount': { Ref: 'AWS::AccountId' } },
              ArnEquals: {
                'aws:SourceArn': {
                  'Fn::Join': ['', Match.arrayWith([Match.stringLikeRegexp(':model-customization-job/\\*$')])],
                },
              },
            },
          })],
        },
      });
    });
  });

  describe('KnowledgeBaseStack (RAG)', () => {
    const template = Template.fromStack(kbStack);

    test('uses S3 Vectors (not OpenSearch Serverless) as the vector store', () => {
      // OpenSearch Serverless has an idle cost floor and must not appear.
      template.resourceCountIs('AWS::S3Vectors::VectorBucket', 1);
      template.resourceCountIs('AWS::S3Vectors::Index', 1);
      template.resourceCountIs('AWS::OpenSearchServerless::Collection', 0);
    });

    test('vector index dimension matches the Titan V2 embedding dimension', () => {
      template.hasResourceProperties('AWS::S3Vectors::Index', {
        Dimension: 1024,
        DataType: 'float32',
        DistanceMetric: 'cosine',
      });
    });

    test('vector index marks Bedrock text/metadata keys non-filterable', () => {
      // S3 Vectors caps filterable metadata at 2048 bytes; ingestion fails otherwise.
      template.hasResourceProperties('AWS::S3Vectors::Index', {
        MetadataConfiguration: {
          NonFilterableMetadataKeys: Match.arrayWith([
            'AMAZON_BEDROCK_TEXT',
            'AMAZON_BEDROCK_METADATA',
          ]),
        },
      });
    });

    test('knowledge base wires the S3 Vectors store and Titan V2 embeddings', () => {
      template.hasResourceProperties('AWS::Bedrock::KnowledgeBase', {
        KnowledgeBaseConfiguration: {
          Type: 'VECTOR',
          VectorKnowledgeBaseConfiguration: {
            // ARN is a Fn::Join with the region ref; assert the model suffix.
            EmbeddingModelArn: {
              'Fn::Join': ['', Match.arrayWith(['::foundation-model/amazon.titan-embed-text-v2:0'])],
            },
          },
        },
        StorageConfiguration: { Type: 'S3_VECTORS' },
      });
    });

    test('data source points at the dataset bucket', () => {
      template.resourceCountIs('AWS::Bedrock::DataSource', 1);
      template.hasResourceProperties('AWS::Bedrock::DataSource', {
        DataSourceConfiguration: { Type: 'S3' },
      });
    });

    test('data source name encodes the chunk size so a chunking change can replace cleanly', () => {
      // A chunking change replaces the data source; a fixed name would collide (409).
      template.hasResourceProperties('AWS::Bedrock::DataSource', {
        Name: 'legal-legislation-corpus-fs1000',
      });
    });

    test('data source chunks large enough to hold a whole section, not the default 300 tokens', () => {
      // 1000 tokens holds a section with its subsections. HIERARCHICAL can breach
      // the S3 Vectors metadata cap.
      template.hasResourceProperties('AWS::Bedrock::DataSource', {
        VectorIngestionConfiguration: {
          ChunkingConfiguration: {
            ChunkingStrategy: 'FIXED_SIZE',
            FixedSizeChunkingConfiguration: {
              MaxTokens: 1000,
              OverlapPercentage: 20,
            },
          },
        },
      });
    });

    test('KB service role is assumable by Bedrock', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        AssumeRolePolicyDocument: {
          Statement: Match.arrayWith([
            Match.objectLike({
              Effect: 'Allow',
              Principal: { Service: 'bedrock.amazonaws.com' },
            }),
          ]),
        },
      });
    });

    test('KB service role can invoke embeddings, read S3, and access the vector store', () => {
      template.hasResourceProperties('AWS::IAM::Policy', {
        PolicyDocument: {
          Statement: Match.arrayWith([
            Match.objectLike({ Action: 'bedrock:InvokeModel' }),
            Match.objectLike({ Action: 's3:GetObject' }),
          ]),
        },
      });
      const allActions = JSON.stringify(template.findResources('AWS::IAM::Policy'));
      expect(allActions).toContain('s3vectors:QueryVectors');
    });

    test('exposes KB id and data source id as outputs for notebook auto-resolve', () => {
      template.hasOutput('KnowledgeBaseId', {});
      template.hasOutput('DataSourceId', {});
    });

    test('notebook RAG policy grants ingestion and retrieval', () => {
      const managed = JSON.stringify(template.findResources('AWS::IAM::ManagedPolicy'));
      expect(managed).toContain('bedrock:StartIngestionJob');
      expect(managed).toContain('bedrock:Retrieve');
      template.hasOutput('NotebookRagPolicyArn', {});
    });

    // bedrock:Rerank has no resource-level permissions, so it must be on "*",
    // with the model pinned on bedrock:InvokeModel instead (rerank-prereq.html).
    describe('notebook RAG policy reranking permissions', () => {
      const ragStatements = () => {
        const policies = template.findResources('AWS::IAM::ManagedPolicy');
        const rag = Object.values(policies).find((p: any) =>
          JSON.stringify(p).includes('RerankRetrievedPassages'),
        ) as any;
        expect(rag).toBeDefined();
        return rag.Properties.PolicyDocument.Statement as any[];
      };
      const bySid = (sid: string) => {
        const s = ragStatements().find((x) => x.Sid === sid);
        expect(s).toBeDefined();
        return s;
      };
      const actionsOf = (stmt: any): string[] =>
        Array.isArray(stmt.Action) ? stmt.Action : [stmt.Action];

      test('bedrock:Rerank is on "*" and alone in its own statement', () => {
        const s = bySid('RerankRetrievedPassages');
        expect(s.Effect).toBe('Allow');
        expect(actionsOf(s)).toEqual(['bedrock:Rerank']);
        expect(s.Resource).toBe('*');
        expect(s.Condition).toBeUndefined();
      });

      test('bedrock:InvokeModel is scoped to exactly the Cohere reranker ARN', () => {
        const s = bySid('InvokeRerankModel');
        expect(s.Effect).toBe('Allow');
        expect(actionsOf(s)).toEqual(['bedrock:InvokeModel']);
        // Rendered as Fn::Join over the region token.
        const parts = s.Resource['Fn::Join'][1];
        const rendered = parts
          .map((p: any) => (typeof p === 'string' ? p : '<REGION>'))
          .join('');
        expect(rendered).toBe('arn:aws:bedrock:<REGION>::foundation-model/cohere.rerank-v3-5:0');
      });

      // A "us." inference profile authorises against both the profile ARN and the
      // foundation-model ARN; granting only one fails with AccessDenied.
      test('grants InvokeModel on the Module 6 agent orchestrator, not on "*"', () => {
        const s = bySid('InvokeAgentOrchestratorModel');
        expect(s.Effect).toBe('Allow');
        // Strands streams by default, so both actions are needed.
        expect(actionsOf(s)).toEqual([
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
        ]);
        expect(s.Resource).not.toBe('*');
      });

      test('orchestrator grant covers the inference profile AND the model', () => {
        const render = (resource: any): string => {
          if (typeof resource === 'string') return resource;
          const join = resource?.['Fn::Join'];
          if (!join) return '<TOKEN>';
          return join[1]
            .map((p: any) => (typeof p === 'string' ? p : '<TOKEN>'))
            .join('');
        };
        const rendered = (bySid('InvokeAgentOrchestratorModel').Resource as any[]).map(render);
        expect(rendered).toEqual([
          'arn:aws:bedrock:<TOKEN>:<TOKEN>:inference-profile/us.amazon.nova-pro-v1:0',
          // Region wildcard, since a profile's routing regions can change; the model stays pinned.
          'arn:aws:bedrock:*::foundation-model/amazon.nova-pro-v1:0',
        ]);
      });

      // Rerank is the only action AWS forces onto "*". Nothing else in this policy
      // may quietly acquire a bucket-wide or account-wide bedrock grant.
      test('no bedrock action other than Rerank is granted on "*"', () => {
        for (const s of ragStatements()) {
          const bedrockActions = actionsOf(s).filter((a) => a.startsWith('bedrock:'));
          if (bedrockActions.length === 0) continue;
          if (s.Resource === '*') {
            expect(bedrockActions).toEqual(['bedrock:Rerank']);
          }
        }
      });
    });

    // The notebooks share scores through results/cells/. Access is limited to
    // the RAG prefixes so users in a shared account can't overwrite each other.
    describe('notebook RAG policy results-bucket scoping', () => {
      /** The RAG policy's statements, keyed by Sid. */
      const statements = () => {
        const policies = template.findResources('AWS::IAM::ManagedPolicy');
        const rag = Object.values(policies).find((p: any) =>
          JSON.stringify(p).includes('ReadWriteCellResults'),
        ) as any;
        expect(rag).toBeDefined();
        const byId: Record<string, any> = {};
        for (const s of rag.Properties.PolicyDocument.Statement) byId[s.Sid] = s;
        return byId;
      };

      /** Every Resource entry of a statement, rendered as a comparable string. */
      const resourceStrings = (stmt: any): string[] => {
        const list = Array.isArray(stmt.Resource) ? stmt.Resource : [stmt.Resource];
        return list.map((r: any) =>
          typeof r === 'string'
            ? r
            : r['Fn::Join']
              ? r['Fn::Join'][1]
                  .map((part: any) => (typeof part === 'string' ? part : '<BUCKET_ARN>'))
                  .join('')
              : '<BUCKET_ARN>',
        );
      };

      test('object access is limited to results/cells/ and handoff/', () => {
        const s = statements().ReadWriteCellResults;
        expect(s.Effect).toBe('Allow');
        // ListBucket lives in its own statement with a prefix condition.
        expect(s.Action).toEqual(['s3:GetObject', 's3:PutObject']);
        expect(resourceStrings(s).sort()).toEqual(
          ['<BUCKET_ARN>/handoff/*', '<BUCKET_ARN>/results/cells/*'].sort(),
        );
      });

      test('ListBucket is constrained by an s3:prefix condition', () => {
        const s = statements().ListCellResultsPrefixes;
        expect(s.Effect).toBe('Allow');
        expect(s.Action).toBe('s3:ListBucket');
        expect(resourceStrings(s)).toEqual(['<BUCKET_ARN>']);
        expect(s.Condition).toEqual({
          StringLike: { 's3:prefix': ['results/cells/*', 'handoff/*'] },
        });
      });

      // Notebook access to the results bucket must stay limited to its prefixes.
      test('no statement grants the whole results bucket', () => {
        for (const [sid, stmt] of Object.entries(statements())) {
          if (sid === 'UploadCorpusToDatasetBucket') continue; // dataset bucket
          for (const r of resourceStrings(stmt)) {
            expect(r).not.toBe('<BUCKET_ARN>/*');
          }
        }
      });

      // An unconditioned ListBucket would let one user enumerate every
      // other user's records even with object access narrowed.
      test('no S3 statement allows ListBucket without a prefix condition', () => {
        for (const [sid, stmt] of Object.entries(statements())) {
          const actions = Array.isArray((stmt as any).Action)
            ? (stmt as any).Action
            : [(stmt as any).Action];
          if (!actions.includes('s3:ListBucket')) continue;
          if (sid === 'UploadCorpusToDatasetBucket') continue; // dataset bucket
          expect((stmt as any).Condition?.StringLike?.['s3:prefix']).toBeDefined();
        }
      });
    });
  });
});
