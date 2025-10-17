import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as lambda from 'aws-cdk-lib/aws-lambda';

interface OrchestrationProps extends cdk.StackProps {
  bucketNames: Record<string,string>;
  tableNames: Record<string,string>;
  secrets: Record<string,string>;
}

export class KbOrchestrationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: OrchestrationProps) {
    super(scope, id, props);

    const getFn = (name: string) => lambda.Function.fromFunctionName(this, name, name);

    const pipeline = new sfn.StateMachine(this, 'KbPipeline', {
      definition: new tasks.LambdaInvoke(this, 'Normalize', { lambdaFunction: getFn('normalize_markdown') })
        .next(new tasks.LambdaInvoke(this, 'Embed', { lambdaFunction: getFn('embed_openai_batch') }))
        .next(new tasks.Choice(this, 'ClusterChoice')
          .when(sfn.Condition.stringEquals('$.clustering.method', 'hdbscan'),
                new tasks.LambdaInvoke(this, 'ClusterHdbscan', { lambdaFunction: getFn('cluster_hdbscan') }))
          .otherwise(new tasks.LambdaInvoke(this, 'ClusterKMeans', { lambdaFunction: getFn('cluster_kmeans') })))
        .next(new tasks.LambdaInvoke(this, 'LinkNeighbors', { lambdaFunction: getFn('link_neighbors') }))
        .next(new tasks.LambdaInvoke(this, 'Summaries', { lambdaFunction: getFn('summarize_llm') }))
        .next(new tasks.LambdaInvoke(this, 'Synthesis', { lambdaFunction: getFn('synthesis_llm') }))
        .next(new tasks.LambdaInvoke(this, 'ExportGithub', { lambdaFunction: getFn('export_github') }))
        .next(new tasks.LambdaInvoke(this, 'EmailDigest', { lambdaFunction: getFn('email_digest') })),
      timeout: cdk.Duration.minutes(30)
    });

    // Daily schedule 05:00 Europe/Berlin (UTC offset handled at account level; adjust if needed)
    new events.Rule(this, 'DailySchedule', {
      schedule: events.Schedule.cron({ minute: '0', hour: '5' }),
      targets: [new targets.SfnStateMachine(pipeline)]
    });
  }
}
