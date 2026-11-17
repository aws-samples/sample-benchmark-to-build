// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';
import { DomainConfig } from '../config/domains';

export interface FineTuningStackProps extends cdk.StackProps {
  domain: DomainConfig;
  datasetBucket: s3.IBucket;
  resultsBucket: s3.IBucket;
}

/**
 * IAM role for Bedrock custom model training, and the notebook policy that uses it.
 */
export class FineTuningStack extends cdk.Stack {
  public readonly bedrockTrainingRole: iam.Role;

  constructor(scope: Construct, id: string, props: FineTuningStackProps) {
    super(scope, id, props);

    const account = cdk.Stack.of(this).account;
    const region = cdk.Stack.of(this).region;

    // Trust limited to this account's customization jobs (confused-deputy guard).
    this.bedrockTrainingRole = new iam.Role(this, 'BedrockTrainingRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com', {
        conditions: {
          StringEquals: { 'aws:SourceAccount': account },
          ArnEquals: { 'aws:SourceArn': `arn:aws:bedrock:${region}:${account}:model-customization-job/*` },
        },
      }),
      description: `Role for Bedrock custom model training - ${props.domain.name}`,
    });

    props.datasetBucket.grantRead(this.bedrockTrainingRole);
    props.resultsBucket.grantReadWrite(this.bedrockTrainingRole);

    new cdk.CfnOutput(this, 'BedrockTrainingRoleArn', {
      value: this.bedrockTrainingRole.roleArn,
      description: 'IAM role ARN for Bedrock custom model training',
    });

    const notebookPolicy = new iam.ManagedPolicy(this, 'NotebookFineTuningPolicy', {
      description: `Permissions for notebooks to run Bedrock fine-tuning - ${props.domain.name}`,
      statements: [
        new iam.PolicyStatement({
          sid: 'PassTrainingRoleToBedrock',
          effect: iam.Effect.ALLOW,
          actions: ['iam:PassRole'],
          resources: [this.bedrockTrainingRole.roleArn],
          conditions: { StringEquals: { 'iam:PassedToService': 'bedrock.amazonaws.com' } },
        }),
        new iam.PolicyStatement({
          sid: 'BedrockCustomModelJobs',
          effect: iam.Effect.ALLOW,
          actions: [
            'bedrock:CreateModelCustomizationJob',
            'bedrock:GetModelCustomizationJob',
            'bedrock:ListModelCustomizationJobs',
            'bedrock:StopModelCustomizationJob',
            'bedrock:GetCustomModel',
            'bedrock:ListCustomModels',
            // Custom models must be deployed before on-demand inference.
            'bedrock:CreateCustomModelDeployment',
            'bedrock:GetCustomModelDeployment',
            'bedrock:ListCustomModelDeployments',
            'bedrock:DeleteCustomModelDeployment',
          ],
          resources: ['*'],
        }),
        new iam.PolicyStatement({
          sid: 'BedrockInvokeCustomModels',
          effect: iam.Effect.ALLOW,
          actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
          resources: ['*'],
        }),
        new iam.PolicyStatement({
          sid: 'ReadDatasetWriteResults',
          effect: iam.Effect.ALLOW,
          actions: ['s3:GetObject', 's3:ListBucket', 's3:PutObject'],
          resources: [
            props.datasetBucket.bucketArn, `${props.datasetBucket.bucketArn}/*`,
            props.resultsBucket.bucketArn, `${props.resultsBucket.bucketArn}/*`,
          ],
        }),
      ],
    });

    new cdk.CfnOutput(this, 'NotebookFineTuningPolicyArn', {
      value: notebookPolicy.managedPolicyArn,
      description: 'Attach this policy to your SageMaker notebook execution role for Module 3',
    });
  }
}
