import boto3
import subprocess
import os
import typer
from rich import print


def run_ecs_task(context: RemotfContext):
    ecs = boto3.client("ecs", region_name=context.region)

    response = ecs.run_task(
        cluster=context.cluster_name,
        taskDefinition=context.task_definition,
        launchType='FARGATE',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': context.subnets,
                'securityGroups': context.security_groups,
                'assignPublicIp': 'ENABLED'
            }
        },
        overrides={
            'containerOverrides': [{
                'name': context.task_definition_family,
                'environment': [
                    {'name': 'TF_COMMAND',          'value': command},
                    {'name': 'S3_BUCKET',           'value': context.bucket_name},
                    {'name': 'S3_CODE_ARCHIVE_KEY', 'value': context.s3_code_archive_key},
                    {'name': 'S3_ENV_ARCHIVE_KEY',  'value': context.s3_env_archive_key},
                    {'name': 'BACKEND_CONFIG',      'value': os.path.basename(context.backend_config) if context.backend_config else ''},
                    {'name': 'BOOTSTRAP',           'value': 'true' if context.bootstrap else 'false'}
                ]
            }]
        }
    )

    if response.get('failures'):
        for failure in response['failures']:
            print(f"[red]ECS launch failure: {failure.get('reason')} ({failure.get('arn')})[/red]")
        raise typer.Exit(code=1)

    if not response.get('tasks'):
        print("[red]ECS returned no tasks and no failures. Something is wrong.[/red]")
        raise typer.Exit(code=1)

    task_arn = response['tasks'][0]['taskArn']
    print(f"[dim]Task started: {task_arn.split('/')[-1]}[/dim]")

    waiter = ecs.get_waiter('tasks_running')
    waiter.wait(cluster=context.cluster_name, tasks=[task_arn], WaiterConfig={'Delay': 3, 'MaxAttempts': 40})

    print("[dim]Container is live. Streaming output:\n[/dim]")
    subprocess.run(["aws", "logs", "tail", context.log_group_name, "--follow", "--since", "1m", "--format", "short"], check=False)

    task_detail = ecs.describe_tasks(cluster=context.cluster_name, tasks=[task_arn])
    container = task_detail['tasks'][0]['containers'][0]
    exit_code = container.get('exitCode')
    if exit_code is not None and exit_code != 0:
        print(f"[red]Task exited with code {exit_code}: {container.get('reason', '')}[/red]")
        raise typer.Exit(code=exit_code)