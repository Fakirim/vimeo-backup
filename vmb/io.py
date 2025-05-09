import os
import requests
import time
import threading
from typing import Optional, Dict, Any
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
    DownloadColumn,
)
from rich.console import Console

from .core import DownloadJob
from .verify import calculate_sha256, update_manifest_entry
from .db import ManifestDB, update_manifest_entry_db

console = Console()

# Number of retries for network errors
MAX_RETRIES = 3

# Constants for download chunks
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for downloads

def get_rich_progress() -> Progress:
    """Create and return a configured Progress instance for file downloads."""
    return Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
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
    manifest_data: Dict[str, Dict[str, Any]],
    manifest_path: str,
    manifest_lock: threading.Lock,
    db: Optional[ManifestDB] = None,
    _retry_count: int = 0  # Add retry counter parameter with default 0
) -> bool:
    """Downloads a single video file specified by the DownloadJob.

    Args:
        job: The download job containing URL and target path.
        progress: Progress instance for updating the UI.
        task_id: The ID of the task in the progress display.
        manifest_data: The dictionary representing the manifest (will be modified).
        manifest_path: Path to the manifest file.
        manifest_lock: Lock for thread-safe manifest updates.
        db: Optional ManifestDB instance for database storage.

    Returns:
        True if download was successful, False otherwise.
    """
    # Prepare temporary file path
    temp_path = f"{job.target_path}._vmb_part"
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
    
    # Check retry limit to prevent infinite loops
    MAX_RETRIES = 3  # Maximum number of retry attempts
    if _retry_count >= MAX_RETRIES:
        console.print(f"[bold red]Error:[/bold red] Maximum retry attempts ({MAX_RETRIES}) reached for {job.video_name}. Giving up.")
        return False
        
    # Start the download
    try:
        # Update task description to show it's now downloading
        progress.update(task_id, description=f"⬇️ DOWNLOADING: {job.video_name}")
        # Start progress tracking
        progress.start_task(task_id)
        
        # Track how much we've downloaded (used for resuming)
        downloaded_bytes = 0
        headers = {}
        
        # Check if we have a partial download already
        if os.path.exists(temp_path):
            # Get size of existing file
            downloaded_bytes = os.path.getsize(temp_path)
            # Only add Range header if we have actually downloaded something
            if downloaded_bytes > 0:
                headers["Range"] = f"bytes={downloaded_bytes}-"
                console.print(f"Resuming download from {downloaded_bytes} bytes")
        
        # Make the request
        with requests.get(job.download_url, headers=headers, stream=True, timeout=30) as response:
            # Check if the response is valid
            response.raise_for_status()
            
            # Get total size (handle range requests)
            total_size = int(response.headers.get("content-length", 0))
            if downloaded_bytes > 0 and response.status_code == 206:  # Partial content
                # Add the already downloaded bytes to the total
                total_size += downloaded_bytes
            elif downloaded_bytes > 0 and response.status_code == 200:  # Server doesn't support range
                # We need to start over
                downloaded_bytes = 0
                # Truncate the file
                open(temp_path, "wb").close()
            
            # Update progress display with the total size
            progress.update(task_id, total=total_size, completed=downloaded_bytes)
            
            # Open the file in append mode if resuming, otherwise write mode
            mode = "ab" if downloaded_bytes > 0 else "wb"
            with open(temp_path, mode) as f:
                # Download in chunks
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        # Update progress
                        downloaded_bytes += len(chunk)
                        progress.update(task_id, completed=downloaded_bytes)
        
        # Calculate SHA-256 hash for verification
        progress.update(task_id, description=f"🔍 VERIFYING: {job.video_name}")
        sha256_hash = calculate_sha256(temp_path)
        
        if not sha256_hash:
            console.print(f"[red]Error:[/red] Could not verify download hash for {job.video_name}")
            return False
        
        # Rename temporary file to final file
        os.replace(temp_path, job.target_path)
        
        # Debug output is now conditional based on environment variable
        # Set VMB_DEBUG=1 to enable these debug messages
        if os.environ.get('VMB_DEBUG') == '1':
            console.print(f"[grey][DEBUG IO] Download completed for {job.video_name}[/grey]")
            # Detailed debug info only shown when explicitly requested
            if os.environ.get('VMB_DEBUG_VERBOSE') == '1':
                console.print(f"[grey][DEBUG IO] Job object type: {type(job)}[/grey]")
                console.print(f"[grey][DEBUG IO] Job attributes: {dir(job)}[/grey]")
                if hasattr(job, 'video_data'):
                    console.print(f"[grey][DEBUG IO] Video URI: {job.video_data.get('uri')}[/grey]")
                    # Don't print the full video_data as it's too verbose
                if hasattr(job, 'selected_quality'):
                    console.print(f"[grey][DEBUG IO] Selected quality: {job.selected_quality}[/grey]")
        
        # Update the manifest
        with manifest_lock:
            if db:
                # Update both manifest_data and database at once
                updated = update_manifest_entry_db(
                    db=db,
                    manifest_data=manifest_data,
                    video_data=job.video_data,
                    filepath=job.target_path,
                    quality=job.selected_quality,
                    sha256_hash=sha256_hash
                )
                
                # Don't save the JSON manifest if we're using the database
                # This avoids creating unnecessary vmb_manifest.json files
            else:
                # Just update the in-memory manifest_data
                updated = update_manifest_entry(
                    manifest_data=manifest_data,
                    video_data=job.video_data,
                    filepath=job.target_path,
                    quality=job.selected_quality,
                    sha256_hash=sha256_hash
                )
                
                # Save the in-memory manifest to the JSON file only when not using database
                from .verify import save_manifest
                save_manifest(manifest_path, manifest_data)
        
        # Update progress description
        filesize_mb = round(downloaded_bytes / (1024 * 1024), 2)
        progress.update(task_id, description=f"✅ COMPLETED: {job.video_name} ({filesize_mb} MB)")
        # Hide completed tasks after a short delay to keep focus on active downloads
        progress.update(task_id, visible=True)
        
        return True
    
    except requests.RequestException as e:
        console.print(f"[red]Download Error:[/red] Failed to download {job.video_name}: {e}")
        # Recursively retry with incremented counter
        if _retry_count < MAX_RETRIES:
            console.print(f"Retrying download for {job.video_name} (attempt {_retry_count + 1} of {MAX_RETRIES})...")
            return download_video(job, progress, task_id, manifest_data, manifest_path, manifest_lock, db, _retry_count + 1)
        return False
    
    except (IOError, OSError) as e:
        console.print(f"[red]File Error:[/red] Failed to write {job.video_name}: {e}")
        # Recursively retry with incremented counter
        if _retry_count < MAX_RETRIES:
            console.print(f"Retrying download for {job.video_name} (attempt {_retry_count + 1} of {MAX_RETRIES})...")
            return download_video(job, progress, task_id, manifest_data, manifest_path, manifest_lock, db, _retry_count + 1)
        return False
    
    except Exception as e:
        console.print(f"[red]Unexpected Error:[/red] Failed to download {job.video_name}: {e}")
        # Recursively retry with incremented counter
        if _retry_count < MAX_RETRIES:
            console.print(f"Retrying download for {job.video_name} (attempt {_retry_count + 1} of {MAX_RETRIES})...")
            return download_video(job, progress, task_id, manifest_data, manifest_path, manifest_lock, db, _retry_count + 1)
        return False 