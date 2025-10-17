import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as secrets from 'aws-cdk-lib/aws-secretsmanager';
import * as ses from 'aws-cdk-lib/aws-ses';

export interface KbCoreStackProps extends cdk.StackProps {}

export class KbCoreStack extends cdk.Stack {
  public readonly bucketNames: Record<string,string>;
  public readonly tableNames: Record<string,string>;
  public readonly secrets: Record<string,string>;

  constructor(scope: Construct, id: string, props?: KbCoreStackProps) {
    super(scope, id, props);

    const raw = new s3.Bucket(this, 'KbRaw', { versioned: true });
    const processed = new s3.Bucket(this, 'KbProcessed', { versioned: true });

    const items = new dynamodb.Table(this, 'KbItems', {
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'sk', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST
    });

    const clusters = new dynamodb.Table(this, 'KbClusters', {
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST
    });

    const openai = new secrets.Secret(this, 'OpenAiSecret');
    const readwise = new secrets.Secret(this, 'ReadwiseSecret');
    const reader = new secrets.Secret(this, 'ReaderSecret');
    const github = new secrets.Secret(this, 'GithubSecret');

    // SES Identity placeholder (configure domain/address manually if needed)
    new ses.EmailIdentity(this, 'KbSesIdentity', {
      identity: ses.Identity.email('you@example.com')
    });

    this.bucketNames = { raw: raw.bucketName, processed: processed.bucketName };
    this.tableNames = { items: items.tableName, clusters: clusters.tableName };
    this.secrets = { openai: openai.secretArn, readwise: readwise.secretArn, reader: reader.secretArn, github: github.secretArn };
  }
}
