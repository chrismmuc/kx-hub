import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';

interface ComputeProps extends cdk.StackProps {
  bucketNames: Record<string,string>;
  tableNames: Record<string,string>;
  secrets: Record<string,string>;
}

export class KbComputeStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ComputeProps) {
    super(scope, id, props);

    const env = {
      S3_BUCKET_RAW: props.bucketNames.raw,
      S3_BUCKET_PROCESSED: props.bucketNames.processed,
      DDB_TABLE_ITEMS: props.tableNames.items,
      DDB_TABLE_CLUSTERS: props.tableNames.clusters,
      OPENAI_SECRET_ARN: props.secrets.openai,
      READWISE_SECRET_ARN: props.secrets.readwise,
      READER_SECRET_ARN: props.secrets.reader,
      GITHUB_SECRET_ARN: props.secrets.github,
      REGION: this.region
    };

    const createFn = (name: string) =>
      new lambda.Function(this, name, {
        runtime: lambda.Runtime.NODEJS_20_X,
        handler: "index.handler",
        code: lambda.Code.fromAsset(`../../lambdas/${name}`),
        timeout: cdk.Duration.minutes(5),
        environment: env
      });

    const fns = [
      'ingest_readwise','ingest_reader','normalize_markdown','embed_openai_batch',
      'cluster_kmeans','cluster_hdbscan','link_neighbors','summarize_llm',
      'synthesis_llm','export_github','email_digest','manual_trigger_router'
    ].reduce((acc, n) => ({...acc, [n]: createFn(n)}), {} as Record<string,lambda.Function>);

    // Minimal permissions (expand as needed)
    Object.values(fns).forEach(fn => {
      fn.addToRolePolicy(new iam.PolicyStatement({
        actions: ["s3:*"], resources: ["*"]
      }));
      fn.addToRolePolicy(new iam.PolicyStatement({
        actions: ["dynamodb:*"], resources: ["*"]
      }));
      fn.addToRolePolicy(new iam.PolicyStatement({
        actions: ["secretsmanager:GetSecretValue"], resources: Object.values(props.secrets)
      }));
    });
  }
}
