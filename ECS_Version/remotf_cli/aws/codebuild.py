import boto3
import time
import typer
from rich import print
def wait_for_codebuild(build_id: str, cb_client, region: str):
    """Poll CodeBuild and stream logs live."""
    logs = boto3.client("logs", region_name=region)
    project_name = build_id.split(':')[0]
    log_group = f"/aws/codebuild/{project_name}"
    log_stream = None
    next_token = None
    seen_tokens = set()

    print("[dim]Waiting for build to start...[/dim]")

    while True:
        response = cb_client.batch_get_builds(ids=[build_id])
        build = response['builds'][0]
        status = build['buildStatus']

        if not log_stream:
            log_stream = build.get('logs', {}).get('streamName')
            if log_stream:
                print(f"[dim]Log stream found: {log_stream}[/dim]")

        if log_stream:
            try:
                kwargs = {
                    "logGroupName": log_group,
                    "logStreamName": log_stream,
                    "startFromHead": True if next_token is None else False
                }
                if next_token:
                    kwargs["nextToken"] = next_token

                log_response = logs.get_log_events(**kwargs)
                log_response = logs.get_log_events(**kwargs)
                print(f"[dim]DEBUG: got {len(log_response.get('events', []))} events, token: {log_response.get('nextForwardToken')}[/dim]")
                new_token = log_response.get('nextForwardToken')

                if new_token not in seen_tokens:
                    for event in log_response.get('events', []):
                        print(f"[dim]{event['message'].rstrip()}[/dim]")
                    seen_tokens.add(new_token)
                    next_token = new_token

            except Exception:
                pass

        if status == 'SUCCEEDED':
            # flush any remaining logs before exiting
            if log_stream:
                try:
                    log_response = logs.get_log_events(
                        logGroupName=log_group,
                        logStreamName=log_stream,
                        startFromHead=True,
                        **({'nextToken': next_token} if next_token else {})
                    )
                    for event in log_response.get('events', []):
                        print(f"[dim]{event['message'].rstrip()}[/dim]")
                except Exception:
                    pass
            print("[green]Image built successfully![/green]")
            return
        elif status in ('FAILED', 'FAULT', 'STOPPED', 'TIMED_OUT'):
            print(f"[red]Build failed with status: {status}[/red]")
            raise typer.Exit(code=1)

        time.sleep(5)
