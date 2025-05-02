import os
import requests
import time
from typing import Optional, Dict, Any
from rich.progress import (
    Progress,
    BarColumn,
    DownloadColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.console import Console

from .core import DownloadJob # Assuming DownloadJob is defined in core
from .verify import calculate_sha256, update_manifest_entry, ManifestData

console = Console()

# --- Constants ---
CHUNK_SIZE = 1024 * 1024  # 1MB chunks
CONNECT_TIMEOUT = 15  # seconds
READ_TIMEOUT = 60  # seconds
TEMP_SUFFIX = "._vmb_part"
MAX_RETRIES = 3 # Retries specifically for download chunk errors
RETRY_DELAY = 5 # Seconds


def get_rich_progress() -> Progress:
    """Returns a pre-configured Rich Progress instance for downloads."""
    return Progress(
        TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
    )

def download_video(
    job: DownloadJob, 
    progress: Progress, 
    task_id,
    manifest_data: ManifestData
) -> bool:
    """Downloads a single video file specified by the DownloadJob.

    Handles streaming, progress reporting, temporary files, basic resume,
    hash calculation, and manifest update.

    Args:
        job: The DownloadJob containing download details.
        progress: The rich Progress instance to report to.
        task_id: The Task ID created within the Progress instance for this download.
        manifest_data: The dictionary representing the manifest (will be modified).

    Returns:
        True if download completed successfully, False otherwise.
    """
    target_path = job.target_path
    temp_path = target_path + TEMP_SUFFIX
    download_url = job.download_url
    retries = 0

    while retries < MAX_RETRIES:
        try:
            headers = {}
            current_size = 0
            mode = "wb" # Write binary mode

            # --- Resume Logic --- 
            if os.path.exists(temp_path):
                current_size = os.path.getsize(temp_path)
                console.print(f"Resuming download for '{job.video_name}' from byte {current_size}")
                headers["Range"] = f"bytes={current_size}-"
                mode = "ab" # Append binary mode
            else:
                current_size = 0
                mode = "wb"

            # --- Make Request --- 
            response = requests.get(
                download_url,
                stream=True,
                headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=True # Follow redirects which Vimeo might use
            )

            # Handle range requests - 206 Partial Content is expected when resuming
            if response.status_code == 206: # Partial Content
                pass # Expected when resuming
            elif response.status_code == 416: # Range Not Satisfiable
                # This means the file is likely already complete
                console.print(f"[yellow]Warning:[/yellow] Received 416 Range Not Satisfiable for '{job.video_name}'. File might be complete.")
                # Check if the temp file size matches Content-Range total size if available? Or just assume complete.
                if os.path.exists(temp_path):
                    os.rename(temp_path, target_path)
                    progress.update(task_id, completed=True, visible=False)
                    console.print(f"[green]Completed:[/green] '{job.video_name}' (assumed complete based on 416).",) 
                    return True
                else: # Should not happen, but handle defensively
                     console.print(f"[red]Error:[/red] Received 416 but no temp file found for '{job.video_name}'. Skipping.",) 
                     progress.update(task_id, visible=False) # Hide progress
                     return False
            elif response.ok:
                 # If we didn't request a range, or server ignored it, reset current_size
                 if "Range" not in headers:
                      current_size = 0
                      mode = "wb"
            else:
                # Handle other errors (4xx, 5xx)
                console.print(f"[red]Error:[/red] Failed to start download for '{job.video_name}'. Status: {response.status_code} {response.reason}")
                progress.update(task_id, visible=False)
                return False

            # --- Get Total Size --- 
            total_size_str = response.headers.get("content-length")
            total_size = None
            if total_size_str:
                 total_size = int(total_size_str) + current_size # Add already downloaded size for total
                 progress.update(task_id, total=total_size, completed=current_size)
            else:
                 # If no content-length, we can't show progress accurately
                 progress.update(task_id, total=None) # Indeterminate progress
                 console.print(f"[yellow]Warning:[/yellow] No content-length for '{job.video_name}'. Progress bar may be inaccurate.")

            # --- Download Loop --- 
            download_successful = False
            with open(temp_path, mode) as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk: # filter out keep-alive new chunks
                        f.write(chunk)
                        progress.update(task_id, advance=len(chunk))
                download_successful = True # Mark as successful only if loop completes

            # --- Finalization --- 
            # Verify final size if total_size was known and download loop finished
            if download_successful:
                final_size = os.path.getsize(temp_path)
                if total_size is not None and final_size < total_size:
                    # Don't retry here, let the outer loop handle it
                    raise requests.exceptions.RequestException(f"Download incomplete: Expected {total_size} bytes, got {final_size}")

                # --- Hash Calculation & Manifest Update --- 
                progress.update(task_id, description=f"Hashing {job.video_name}...")
                sha256_hash = calculate_sha256(temp_path)
                if sha256_hash:
                    # Move temp file to final path *after* hashing
                    os.rename(temp_path, target_path)
                    progress.update(task_id, visible=False) # Hide completed task
                    console.print(f"[green]Completed:[/green] '{job.video_name}' -> '{target_path}'")
                    
                    # Update the manifest data dictionary (in memory)
                    update_manifest_entry(
                        manifest_data,
                        job.video_data, # Get original video data from job
                        target_path,
                        job.selected_quality,
                        sha256_hash
                    )
                    return True # Success
                else:
                    # Hash calculation failed
                    console.print(f"[red]Error:[/red] Failed to calculate hash for downloaded file '{temp_path}'. Skipping manifest update and deleting temp file.")
                    progress.update(task_id, visible=False)
                    try: os.remove(temp_path) 
                    except OSError: pass
                    return False # Treat as failure
            else:
                 # Download loop didn't complete (likely connection error before loop)
                 # Error should have been raised or handled already, just ensure we return False
                 return False

        except requests.exceptions.Timeout as e:
            console.print(f"[yellow]Timeout occurred for '{job.video_name}': {e}. Retrying ({retries+1}/{MAX_RETRIES})...[/]")
        except requests.exceptions.RequestException as e:
            console.print(f"[yellow]Download error for '{job.video_name}': {e}. Retrying ({retries+1}/{MAX_RETRIES})...[/]")
        except Exception as e:
            console.print(f"[red]Unexpected error during download of '{job.video_name}': {e}. Stopping retries for this file.[/]")
            # Log full traceback here potentially
            progress.update(task_id, visible=False)
            # Clean up temp file on unexpected error?
            if os.path.exists(temp_path):
                 try: os.remove(temp_path) 
                 except OSError: pass
            return False # Abort for this file

        # If we reached here, an error occurred, wait before retrying
        retries += 1
        if retries < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    # If loop finishes, all retries failed
    console.print(f"[red]Error:[/red] Failed to download '{job.video_name}' after {MAX_RETRIES} retries.")
    progress.update(task_id, visible=False)
    # Optionally remove the potentially corrupted temp file
    # if os.path.exists(temp_path):
    #    try: os.remove(temp_path)
    #    except OSError: pass
    return False 