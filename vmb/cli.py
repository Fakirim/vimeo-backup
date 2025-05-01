import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option(package_name="vimeo-backup-tool")
def main() -> None:
    """Vimeo Backup Tool (vmb) - Download and back up your Vimeo library."""
    pass


@main.command()
def auth() -> None:
    """Authenticate with Vimeo using a Personal Access Token (PAT)."""
    console.print("[bold yellow]Auth command placeholder[/]")
    # TODO: Implement authentication flow


@main.command()
@click.option(
    "--dest",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, writable=True),
    help="Destination directory for backups.",
)
@click.option("--threads", type=int, default=4, help="Number of download threads.")
@click.option(
    "--quality",
    type=click.Choice(["best", "original", "1080p", "720p", "540p", "360p"]), # Simplified for now
    default="best",
    help="Preferred video quality.",
)
@click.option("--since", type=click.DateTime(), help="Only download videos added since this date/time.")
@click.option("--limit-rate", help="Limit download speed (e.g., '1M', '500K').")
@click.option("--dry-run", is_flag=True, help="Show what would be downloaded without downloading.")
def sync(
    dest: str,
    threads: int,
    quality: str,
    since: str | None,
    limit_rate: str | None,
    dry_run: bool,
) -> None:
    """Download new/updated videos from your Vimeo account."""
    console.print(f"[bold cyan]Sync command placeholder[/] Dest: {dest}, Threads: {threads}, DryRun: {dry_run}")
    # TODO: Implement sync logic


@main.command()
@click.option(
    "--dest",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Directory containing the backup and manifest.",
)
@click.option("--fix", is_flag=True, help="Attempt to re-download corrupted/missing files.")
def verify(dest: str, fix: bool) -> None:
    """Verify the integrity of the local backup using the manifest."""
    console.print(f"[bold magenta]Verify command placeholder[/] Dest: {dest}, Fix: {fix}")
    # TODO: Implement verification logic


@main.command("list")
@click.option("--json", "json_output", is_flag=True, help="Output video list as JSON.")
def list_videos(json_output: bool) -> None:
    """List videos available in your Vimeo account."""
    console.print(f"[bold green]List command placeholder[/] JSON: {json_output}")
    # TODO: Implement list logic


@main.command()
def stats() -> None:
    """Show backup statistics (total size, number of videos, etc.)."""
    console.print("[bold blue]Stats command placeholder[/]")
    # TODO: Implement stats logic


if __name__ == "__main__":
    main() 