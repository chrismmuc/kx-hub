#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { KbCoreStack } from '../lib/kb-core-stack';
import { KbComputeStack } from '../lib/kb-compute-stack';
import { KbOrchestrationStack } from '../lib/kb-orchestration-stack';

const app = new cdk.App();

const core = new KbCoreStack(app, 'KbCoreStack', {});
const compute = new KbComputeStack(app, 'KbComputeStack', {
  bucketNames: core.bucketNames,
  tableNames: core.tableNames,
  secrets: core.secrets
});
new KbOrchestrationStack(app, 'KbOrchestrationStack', {
  tableNames: core.tableNames,
  bucketNames: core.bucketNames,
  secrets: core.secrets
});
