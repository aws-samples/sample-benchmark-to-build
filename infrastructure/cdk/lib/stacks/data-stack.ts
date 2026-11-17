// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';
import { DomainConfig } from '../config/domains';

export interface DataStackProps extends cdk.StackProps {
  domain: DomainConfig;
}

/**
 * Storage infrastructure for benchmark datasets and evaluation results.
 */
export class DataStack extends cdk.Stack {
  public readonly datasetBucket: s3.Bucket;
  public readonly resultsBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props: DataStackProps) {
    super(scope, id, props);

    this.datasetBucket = new s3.Bucket(this, 'DatasetBucket', {
      bucketName: cdk.PhysicalName.GENERATE_IF_NEEDED,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      enforceSSL: true,
    });

    this.resultsBucket = new s3.Bucket(this, 'ResultsBucket', {
      bucketName: cdk.PhysicalName.GENERATE_IF_NEEDED,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      enforceSSL: true,
    });

    new cdk.CfnOutput(this, 'DatasetBucketName', {
      value: this.datasetBucket.bucketName,
      description: 'S3 bucket for evaluation datasets',
    });

    new cdk.CfnOutput(this, 'ResultsBucketName', {
      value: this.resultsBucket.bucketName,
      description: 'S3 bucket for evaluation results',
    });
  }
}
