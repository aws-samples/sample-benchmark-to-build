// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';
import { DomainConfig } from '../config/domains';

export interface EvaluationStackProps extends cdk.StackProps {
  domain: DomainConfig;
  datasetBucket: s3.IBucket;
  resultsBucket: s3.IBucket;
}

/**
 * IAM role for Bedrock model evaluation jobs, matching the one the Bedrock
 * console creates, and the notebook policy that uses it.
 */
export class EvaluationStack extends cdk.Stack {
  public readonly evaluationRole: iam.Role;

  constructor(scope: Construct, id: string, props: EvaluationStackProps) {
    super(scope, id, props);

    const account = cdk.Stack.of(this).account;
    const region = cdk.Stack.of(this).region;

    this.evaluationRole = new iam.Role(this, 'BedrockEvalRole', {
      path: '/service-role/',
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com', {
        conditions: {
          StringEquals: { 'aws:SourceAccount': account },
          ArnEquals: { 'aws:SourceArn': `arn:aws:bedrock:${region}:${account}:evaluation-job/*` },
        },
      }),
      description: `Role for Bedrock model evaluation - ${props.domain.name}`,
    });

    this.evaluationRole.addToPolicy(new iam.PolicyStatement({
      sid: 'FetchInputBuckets',
      effect: iam.Effect.ALLOW,
      actions: ['s3:GetObject', 's3:ListBucket'],
      resources: [
        props.datasetBucket.bucketArn,
        `${props.datasetBucket.bucketArn}/*`,
      ],
      conditions: { StringEquals: { 'aws:ResourceAccount': account } },
    }));

    this.evaluationRole.addToPolicy(new iam.PolicyStatement({
      sid: 'FetchAndUpdateOutputBucket',
      effect: iam.Effect.ALLOW,
      actions: [
        's3:GetObject', 's3:ListBucket', 's3:PutObject',
        's3:GetBucketLocation', 's3:AbortMultipartUpload', 's3:ListBucketMultipartUploads',
      ],
      resources: [
        props.resultsBucket.bucketArn,
        `${props.resultsBucket.bucketArn}/*`,
      ],
      conditions: { StringEquals: { 'aws:ResourceAccount': account } },
    }));

    this.evaluationRole.addToPolicy(new iam.PolicyStatement({
      sid: 'AllowAccessToBedrockResources',
      effect: iam.Effect.ALLOW,
      actions: [
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream',
        'bedrock:CreateModelInvocationJob',
        'bedrock:StopModelInvocationJob',
        'bedrock:GetProvisionedModelThroughput',
        'bedrock:GetInferenceProfile',
        'bedrock:ListInferenceProfiles',
        'bedrock:GetImportedModel',
        'bedrock:GetPromptRouter',
        'sagemaker:InvokeEndpoint',
      ],
      resources: [
        'arn:aws:bedrock:*::foundation-model/*',
        `arn:aws:bedrock:*:${account}:inference-profile/*`,
        `arn:aws:bedrock:*:${account}:provisioned-model/*`,
        `arn:aws:bedrock:*:${account}:imported-model/*`,
        `arn:aws:bedrock:*:${account}:application-inference-profile/*`,
        `arn:aws:bedrock:*:${account}:default-prompt-router/*`,
        `arn:aws:bedrock:*:${account}:prompt-router/*`,
        `arn:aws:sagemaker:*:${account}:endpoint/*`,
        `arn:aws:bedrock:*:${account}:marketplace/model-endpoint/all-access`,
      ],
    }));

    new cdk.CfnOutput(this, 'EvaluationRoleArn', {
      value: this.evaluationRole.roleArn,
      description: 'IAM role ARN for Bedrock evaluation jobs',
    });

    // For Modules 1, 2 and 4. Modules 5 and 6 also need NotebookRagPolicy.
    const notebookPolicy = new iam.ManagedPolicy(this, 'NotebookEvalPolicy', {
      description: `Permissions for notebooks to run Bedrock evaluations - ${props.domain.name}`,
      statements: [
        new iam.PolicyStatement({
          sid: 'ReadBenchmarkStackOutputs',
          effect: iam.Effect.ALLOW,
          actions: ['cloudformation:DescribeStacks'],
          resources: [
            `arn:aws:cloudformation:${region}:${account}:stack/AuBenchmark-*/*`,
          ],
        }),
        new iam.PolicyStatement({
          sid: 'PassEvalRoleToBedrock',
          effect: iam.Effect.ALLOW,
          actions: ['iam:PassRole'],
          resources: [this.evaluationRole.roleArn],
          conditions: { StringEquals: { 'iam:PassedToService': 'bedrock.amazonaws.com' } },
        }),
        new iam.PolicyStatement({
          sid: 'BedrockEvaluationJobs',
          effect: iam.Effect.ALLOW,
          actions: [
            'bedrock:CreateEvaluationJob',
            'bedrock:GetEvaluationJob',
            'bedrock:ListEvaluationJobs',
            'bedrock:StopEvaluationJob',
          ],
          resources: ['*'],
        }),
        new iam.PolicyStatement({
          sid: 'BedrockInvokeModels',
          effect: iam.Effect.ALLOW,
          actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
          resources: ['*'],
        }),
        new iam.PolicyStatement({
          sid: 'ReadWriteDatasetBucket',
          effect: iam.Effect.ALLOW,
          actions: ['s3:GetObject', 's3:ListBucket', 's3:PutObject', 's3:DeleteObject'],
          resources: [props.datasetBucket.bucketArn, `${props.datasetBucket.bucketArn}/*`],
        }),
        new iam.PolicyStatement({
          sid: 'ReadWriteResultsBucket',
          effect: iam.Effect.ALLOW,
          actions: ['s3:GetObject', 's3:ListBucket', 's3:PutObject'],
          resources: [props.resultsBucket.bucketArn, `${props.resultsBucket.bucketArn}/*`],
        }),
      ],
    });

    new cdk.CfnOutput(this, 'NotebookPolicyArn', {
      value: notebookPolicy.managedPolicyArn,
      description: 'Attach this policy to your SageMaker notebook execution role',
    });
  }
}
