"""Job management commands for LimaCharlie CLI v2.

Commands for listing, viewing, deleting, and waiting on service
jobs.  Jobs track asynchronous operations performed by LimaCharlie
services and replicants.
"""

from __future__ import annotations

from typing import Any, Callable

import click

from ..cli import pass_context
from ..config import resolve_credentials
from ..client import Client
from ..sdk.organization import Organization
from ..sdk.jobs import Jobs as JobsSDK
from ..output import format_output, detect_output_format
from ..discovery import register_explain


# ---------------------------------------------------------------------------
# Explain texts
# ---------------------------------------------------------------------------

_EXPLAIN_LIST = """\
List service jobs in the organization.  Jobs track asynchronous
operations performed by LimaCharlie services such as scans,
replays, and bulk operations.

Use --output json to get the full job data for scripting.
"""

_EXPLAIN_GET = """\
Get the full details and status of a specific job by its ID.
Returns the job type, status, progress, and any result data.

Example:
  limacharlie job get --id <job-id>
"""

_EXPLAIN_DELETE = """\
Delete a job by its ID.  This removes the job record from the
organization.  The --confirm flag is required to prevent accidental
deletion.

Note: Deleting a running job does not cancel its execution.
"""

_EXPLAIN_WAIT = """\
Wait for a job to complete, polling at regular intervals.  Returns
the final job status when the job completes or the timeout expires.

Use --timeout to set the maximum wait time in seconds (default: 300).

Example:
  limacharlie job wait --id <job-id> --timeout 600
"""

register_explain("job.list", _EXPLAIN_LIST)
register_explain("job.get", _EXPLAIN_GET)
register_explain("job.delete", _EXPLAIN_DELETE)
register_explain("job.wait", _EXPLAIN_WAIT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_explain_callback(text: str) -> Callable[[click.Context, click.Parameter, bool], None]:
    def callback(ctx, param, value):
        if value:
            click.echo(text.strip())
            ctx.exit()
    return callback


def _output(ctx: click.Context, data: Any) -> None:
    fmt = ctx.obj.output_format or detect_output_format()
    if not ctx.obj.quiet:
        click.echo(format_output(data, fmt))


def _get_org(ctx: click.Context) -> Organization:
    creds = resolve_credentials(oid=ctx.obj.oid, environment=ctx.obj.environment)
    client = Client(oid=creds["oid"], api_key=creds.get("api_key"), uid=creds.get("uid"))
    return Organization(client)


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

@click.group("job")
def group() -> None:
    """Manage service jobs.

    Jobs track asynchronous operations performed by LimaCharlie
    services.  Use these commands to monitor progress, retrieve
    results, and clean up completed jobs.
    """


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@group.command("list")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_LIST),
    help="Show detailed explanation of this command.",
)
@pass_context
def list_jobs(ctx) -> None:
    """List service jobs.

    Example:
        limacharlie job list
    """
    org = _get_org(ctx)
    sdk = JobsSDK(org)
    data = sdk.list()
    _output(ctx, data)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "job_id", required=True, help="Job ID.")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_GET),
    help="Show detailed explanation of this command.",
)
@pass_context
def get(ctx, job_id) -> None:
    """Get job details.

    Example:
        limacharlie job get --id <job-id>
    """
    org = _get_org(ctx)
    sdk = JobsSDK(org)
    data = sdk.get(job_id)
    _output(ctx, data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "job_id", required=True, help="Job ID to delete.")
@click.option("--confirm", is_flag=True, default=False, help="Confirm deletion (required).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_DELETE),
    help="Show detailed explanation of this command.",
)
@pass_context
def delete(ctx, job_id, confirm) -> None:
    """Delete a job.

    This is a destructive operation.  Pass --confirm to proceed.

    Example:
        limacharlie job delete --id <job-id> --confirm
    """
    if not confirm:
        click.echo(
            "Error: Destructive operation requires --confirm flag.\n"
            "Suggestion: Re-run with --confirm to delete the job.",
            err=True,
        )
        ctx.exit(4)
        return

    org = _get_org(ctx)
    sdk = JobsSDK(org)
    data = sdk.delete(job_id)
    if not ctx.obj.quiet:
        click.echo(f"Job '{job_id}' deleted.")
    _output(ctx, data)


# ---------------------------------------------------------------------------
# wait
# ---------------------------------------------------------------------------

@group.command()
@click.option("--id", "job_id", required=True, help="Job ID to wait for.")
@click.option("--timeout", default=300, type=int, help="Maximum wait time in seconds (default: 300).")
@click.option(
    "--explain", is_flag=True, expose_value=False, is_eager=True,
    callback=_make_explain_callback(_EXPLAIN_WAIT),
    help="Show detailed explanation of this command.",
)
@pass_context
def wait(ctx, job_id, timeout) -> None:
    """Wait for a job to complete.

    Polls the job status until it completes or the timeout expires.

    Example:
        limacharlie job wait --id <job-id> --timeout 600
    """
    if not ctx.obj.quiet:
        click.echo(f"Waiting for job '{job_id}' (timeout: {timeout}s)...", err=True)

    org = _get_org(ctx)
    sdk = JobsSDK(org)
    data = sdk.wait(job_id, timeout=timeout)

    is_done = data.get("is_done", False) or data.get("completed", False)
    if not ctx.obj.quiet:
        if is_done:
            click.echo("Job completed.", err=True)
        else:
            click.echo("Timeout reached; job still running.", err=True)

    _output(ctx, data)
