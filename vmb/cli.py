import click
import json # Added for JSON output
import sys # Added for exiting
import requests # Added for exception handling
import time # Added for time formatting
from concurrent.futures import ThreadPoolExecutor, as_completed # Added for concurrency
from rich.console import Console
from rich.table import Table # Added for table output
from . import config # Use relative import
from . import api # Import the api module
from . import core # Added core
from . import io # Added io
# Import verify module and rename to avoid conflict with verify command
from . import verify as verify_module # Import verify module and functions
from datetime import datetime, timedelta # Import timedelta
from typing import Optional # Added for optional types

console = Console()


# --- Helper for --since parsing ---
SUPPORTED_SINCE_FORMATS = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]

def parse_since_value(ctx: click.Context, param: click.Parameter, value: Optional[str]) -> Optional[datetime]:
    """Parses the --since string value into a datetime object.
    Handles specific formats and keywords like 'yesterday'.
    """
    if value is None:
        return None

    if value.lower() == 'yesterday':
        # Calculate the start of yesterday
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        # Return datetime object for the beginning of yesterday (00:00:00)
        # Make it timezone-naive for now; core logic will make it aware
        return datetime.combine(yesterday, datetime.min.time()) 

    for fmt in SUPPORTED_SINCE_FORMATS:
        try:
            # Return timezone-naive datetime; core logic will handle timezone
            return datetime.strptime(value, fmt)
        except ValueError:
            continue # Try the next format

    # If none of the formats worked
    supported_fmts_str = ", ".join(f"'{f}'" for f in SUPPORTED_SINCE_FORMATS)
    raise click.BadParameter(
        f"'{value}' does not match the formats {supported_fmts_str} or the keyword 'yesterday'."
    )

@click.group()
@click.version_option(package_name="vimeo-backup-tool")
def main() -> None:
    """Vimeo Backup Tool (vmb) - Download and back up your Vimeo library."""
    pass


@main.command()
def auth() -> None:
    """Authenticate with Vimeo using a Personal Access Token (PAT)."""
    # console.print("[bold yellow]Auth command placeholder[/]")
    # TODO: Implement authentication flow
    console.print(
        "Please provide your Vimeo Personal Access Token (PAT). "
        "It needs the 'public', 'private', and 'video_files' scopes.\n"
        "You can generate one here: https://developer.vimeo.com/apps"
    )
    token = click.prompt("Vimeo PAT", hide_input=True, type=str)

    if not token:
        console.print("[bold red]Error: Token cannot be empty.[/]")
        return

    # Basic validation (starts with 'bearer ' or is just the token part)
    # A real token is typically 32+ hex chars, but let's keep it simple
    if " " in token and not token.startswith("bearer "):
         console.print("[bold red]Error: Invalid token format. It should not contain spaces unless starting with 'bearer '. Please provide only the token itself.[/]")
         return
    elif token.startswith("bearer "):
        # Store only the token part if user included 'bearer'
        token = token.split(" ", 1)[1]

    if len(token) < 30: # Basic sanity check for length
        console.print("[bold red]Error: Token seems too short. Please double-check.[/]")
        return

    if config.store_token(token):
        console.print("[bold green]Vimeo token stored successfully in your OS keyring.[/]")
        # Optionally, attempt a test API call here to verify the token
        # e.g., try:
        #          client = VimeoClient(token=config.get_token() ...)
        #          client.get('/me')
        #          console.print("Token verified successfully with Vimeo API.")
        #      except Exception as e:
        #          console.print(f"[bold red]Token stored, but failed to verify with Vimeo API: {e}[/]")
    else:
        console.print("[bold red]Error: Failed to store token in keyring.[/] Please check logs or permissions.")


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
@click.option(
    "--since", 
    type=str, 
    callback=parse_since_value, 
    help="Only download videos modified since this date/time (e.g., '2024-01-15', 'yesterday')."
)
@click.option("--limit-rate", help="Limit download speed (e.g., '1M', '500K').")
@click.option("--dry-run", is_flag=True, help="Show what would be downloaded without downloading.")
def sync(
    dest: str,
    threads: int,
    quality: str,
    since: Optional[datetime], # Callback converts string to datetime or None
    limit_rate: str | None,
    dry_run: bool,
) -> None:
    """Download new/updated videos from your Vimeo account, updating the manifest."""
    # --- 0. Load Manifest --- 
    manifest_path = verify_module.get_manifest_path(dest)
    console.print(f"Loading manifest from: {manifest_path}")
    # Keep manifest_data in memory, it will be modified by download jobs
    manifest_data = verify_module.load_manifest(manifest_path) 

    # --- 1. Fetch Video List --- 
    try:
        console.print("Starting video list fetch...")
        videos = api.get_all_videos()
        if not videos:
            console.print("No videos found on Vimeo account or fetch failed.")
            # Save manifest even if no videos fetched, in case it was created/cleared
            verify_module.save_manifest(manifest_path, manifest_data)
            return
    except (api.MissingTokenError, api.RateLimitError, api.VimeoApiError, requests.exceptions.RequestException) as e:
        # Separate the f-string from the newline and variable
        console.print(f"[bold red]Error fetching video list:[/]") 
        console.print(f"{e}")
        # Still save manifest if it was loaded/modified (e.g., cleared due to error)
        verify_module.save_manifest(manifest_path, manifest_data)
        sys.exit(1)
    except Exception as e:
        # Separate the f-string from the newline and variable
        console.print(f"[bold red]Unexpected error fetching video list:[/]")
        console.print(f"{e}")
        verify_module.save_manifest(manifest_path, manifest_data)
        sys.exit(1)

    # --- 2. Prepare Download Jobs (Delta Check using Manifest) --- 
    console.print("Preparing download jobs (checking against manifest)...")
    # Pass manifest_data and the 'since' datetime object
    jobs = core.prepare_download_jobs(
        videos=videos, 
        dest_dir=dest, 
        preferred_quality=quality, 
        manifest_data=manifest_data,
        since_dt=since # Pass the potentially parsed datetime object
    )

    if not jobs:
        console.print("[green]All videos appear to be up-to-date based on manifest and --since filter. No downloads needed.[/]")
        # Save manifest in case any entries were cleaned during load
        verify_module.save_manifest(manifest_path, manifest_data)
        return

    console.print(f"Found {len(jobs)} videos to download.")

    # --- 3. Handle Dry Run --- 
    if dry_run:
        console.print("[yellow]--dry-run enabled. Showing planned downloads:[/]")
        for job in jobs:
            console.print(f"  - [DRY RUN] Would download '{job.video_name}' ({job.selected_quality}) to '{job.target_path}'")
        # Do not save manifest on dry run
        return

    # --- 4. Execute Downloads Concurrently --- 
    console.print(f"Starting download process with {threads} threads...")
    successful_downloads = 0
    failed_downloads = 0

    # --- Execute Downloads Concurrently --- 
    try: # Wrap the download execution in try/except KeyboardInterrupt
        progress = io.get_rich_progress()
        with progress:
            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = {}
                for job in jobs:
                    task_id = progress.add_task("", filename=job.video_name, start=False)
                    # Pass manifest_data to io.download_video
                    future = executor.submit(io.download_video, job, progress, task_id, manifest_data)
                    futures[future] = job
                
                # Process completed futures as they finish
                for future in as_completed(futures):
                    job = futures[future]
                    try:
                        success = future.result()
                        if success:
                            successful_downloads += 1
                        else:
                            failed_downloads += 1
                    except Exception as exc:
                        console.print(f"[bold red]Error processing download for '{job.video_name}': {exc}[/]")
                        failed_downloads += 1
                        # Here you might want to mark the task in progress bar as failed
                        # progress.update(task_id, description=f"[red]Failed: {job.video_name}[/]")
            # End of ThreadPoolExecutor context
        # End of Progress context
    
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Download cancelled by user.[/] Waiting for active downloads to finalize...")
        # The ThreadPoolExecutor's __exit__ (called by the 'with' statement ending)
        # will attempt to shut down threads. We don't need explicit shutdown here,
        # just allowing the exception to exit the 'with' block gracefully.
        # We'll still save the manifest with completed downloads up to this point.
        pass # Exit the try block
    
    # --- 5. Save Updated Manifest (runs even after KeyboardInterrupt) --- 
    console.print(f"\nSaving updated manifest to {manifest_path}...")
    if verify_module.save_manifest(manifest_path, manifest_data):
        console.print("[green]Manifest saved successfully.[/]")
    else:
        console.print("[bold red]Failed to save manifest![/]")

    # --- 6. Summary --- 
    console.print("--- Download Summary ---")
    console.print(f"[green]Successful downloads: {successful_downloads}[/]")
    if failed_downloads > 0:
        console.print(f"[red]Failed downloads: {failed_downloads}[/]")
    else:
        console.print("All downloads completed successfully.")
    
    # Set exit code based on failures
    if failed_downloads > 0:
        sys.exit(1)


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
    # console.print(f"[bold magenta]Verify command placeholder[/] Dest: {dest}, Fix: {fix}")
    if fix:
        console.print("[yellow]Warning: --fix functionality is not yet implemented.[/]")
        
    try:
        console.print(f"Starting verification in directory: {dest}")
        all_ok = verify_module.verify_integrity(dest)
        
        if all_ok:
            console.print("[bold green]Verification successful.[/]")
            sys.exit(0)
        else:
            console.print("[bold red]Verification failed.[/] See details above.")
            sys.exit(1)
            
    except Exception as e:
        # Separate the f-string from the newline and variable
        console.print(f"[bold red]An unexpected error occurred during verification:[/]")
        console.print(f"{e}")
        sys.exit(1)


@main.command("list")
@click.option("--json", "json_output", is_flag=True, help="Output video list as JSON.")
def list_videos(json_output: bool) -> None:
    """List videos available in your Vimeo account."""
    # console.print(f"[bold green]List command placeholder[/] JSON: {json_output}")
    # TODO: Implement list logic
    try:
        videos = api.get_all_videos()

        if not videos:
            console.print("No videos found or API fetch was interrupted.")
            return

        if json_output:
            # Dump the raw data as JSON
            console.print(json.dumps(videos, indent=2))
        else:
            # Display in a formatted table
            table = Table(title="Vimeo Videos", show_header=True, header_style="bold magenta")
            table.add_column("Name", style="dim", width=50)
            table.add_column("Duration", justify="right")
            table.add_column("Created Time", justify="right")
            table.add_column("URI", justify="left")

            for video in videos:
                # Format duration (seconds -> MM:SS or HH:MM:SS)
                duration_s = video.get("duration", 0)
                if duration_s > 3600:
                    duration_str = time.strftime("%H:%M:%S", time.gmtime(duration_s))
                else:
                    duration_str = time.strftime("%M:%S", time.gmtime(duration_s))

                table.add_row(
                    video.get("name", "N/A"),
                    duration_str,
                    video.get("created_time", "N/A").split("T")[0], # Just the date part
                    video.get("uri", "N/A"),
                )
            console.print(table)

    except api.MissingTokenError as e:
        # Separate the f-string from the newline and variable
        console.print(f"[bold red]Authentication Error:[/]")
        console.print(f"{e}")
        sys.exit(1)
    except api.RateLimitError as e:
        # Separate the f-string from the newline and variable
        console.print(f"[bold red]API Rate Limit Error:[/]")
        console.print(f"{e}")
        sys.exit(1)
    except api.VimeoApiError as e:
        # Separate the f-string from the newline and variable
        console.print(f"[bold red]Vimeo API Error:[/]")
        console.print(f"{e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        # Separate the f-string from the newline and variable
        console.print(f"[bold red]Network Error:[/]") 
        console.print(f"Could not connect to Vimeo API. Check your internet connection.")
        console.print(f"Details: {e}")
        sys.exit(1)
    except Exception as e:
        # Separate the f-string from the newline and variable
        console.print(f"[bold red]An unexpected error occurred:[/]")
        console.print(f"{e}")
        # Consider logging the full traceback here for debugging
        sys.exit(1)


@main.command()
def stats() -> None:
    """Show backup statistics (total size, number of videos, etc.)."""
    console.print("[bold blue]Stats command placeholder[/]")
    # TODO: Implement stats logic


if __name__ == "__main__":
    main() 