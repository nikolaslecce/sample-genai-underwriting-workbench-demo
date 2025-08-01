#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { CdkStack } from '../lib/cdk-stack';
import { AwsSolutionsChecks } from 'cdk-nag'
import { Aspects } from 'aws-cdk-lib';

const app = new cdk.App();

new CdkStack(app, 'AWS-GENAI-UW-DEMO', {
  description: 'AWS Underwriting Assistant'
});

Aspects.of(app).add(new AwsSolutionsChecks());