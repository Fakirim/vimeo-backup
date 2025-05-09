import os
import json
import hashlib
import time
from typing import Dict, Any, Optional, List, Tuple
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .db import ManifestDB, update_manifest_entry_db

console = Console()

# --- Constants ---
MANIFEST_FILENAME = "vmb_manifest.json"
HASH_CHUNK_SIZE = 1024 * 1024 * 4 # Read 4MB chunks for hashing

# --- Manifest Data Structure (Example) ---
# We'll use a dictionary where keys are video URIs (e.g., /videos/12345678)
# Values will be dictionaries containing metadata about the downloaded file.
# { 
#   "/videos/12345678": {
#     "filename": "12345678-My_Video_Title-original.mp4",
#     "quality": "original",
#     "sha256": "abcdef123...",
#     "download_time_utc": "2025-05-02T10:00:00Z",
#     "api_modified_time": "2025-04-30T12:00:00Z", 
#     "filesize": 123456789
#   }, ...
# }
ManifestData = Dict[str, Dict[str, Any]]


def calculate_sha256(file_path: str) -> Optional[str]:
    """Calculates the SHA-256 hash of a file.

    Reads the file in chunks to handle large files efficiently.

    Args:
        file_path: Path to the file.

    Returns:
        The hex digest of the SHA-256 hash, or None if the file doesn't exist
        or cannot be read.
    """
    try:
        if not os.path.exists(file_path):
            return None
        
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in chunks to avoid loading large files entirely in memory
            for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
                h.update(chunk)
        
        return h.hexdigest()
    except Exception as e:
        console.print(f"[red]Error calculating hash for {file_path}: {e}[/]")
        return None


def get_manifest_path(dest_dir: str) -> str:
    """Returns the path to the manifest file in the destination directory."""
    return os.path.join(dest_dir, "vmb_manifest.json")


def load_manifest(manifest_path: str) -> ManifestData:
    """Load the manifest from disk, or return an empty manifest if not found."""
    try:
        if not os.path.exists(manifest_path):
            console.print(f"[yellow]Manifest not found at {manifest_path}. Creating a new one...[/]")
            return {}
        
        with open(manifest_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        console.print(f"[red]Error: Manifest file {manifest_path} is corrupted. Starting with empty manifest.[/]")
        return {}
    except Exception as e:
        console.print(f"[red]Error loading manifest: {e}[/]")
        return {}


def save_manifest(manifest_path: str, manifest_data: ManifestData) -> bool:
    """Save the manifest to disk."""
    try:
        temp_path = f"{manifest_path}.tmp"
        
        with open(temp_path, "w") as f:
            json.dump(manifest_data, f, indent=2)
        
        # Replace the original file atomically to avoid corruption
        if os.path.exists(manifest_path):
            os.replace(temp_path, manifest_path)
        else:
            os.rename(temp_path, manifest_path)
        
        return True
    except Exception as e:
        console.print(f"[red]Error saving manifest: {e}[/]")
        return False

# Placeholder for the verification function
def verify_integrity(dest_dir: str) -> bool:
    """Checks the integrity of downloaded files against the manifest.

    Args:
        dest_dir: The directory containing the downloads and the manifest.

    Returns:
        True if all verified files match the manifest, False otherwise.
    """
    manifest_path = get_manifest_path(dest_dir)
    manifest = load_manifest(manifest_path)

    if not manifest:
        console.print("Manifest not found or empty. Nothing to verify.")
        return True # Technically correct, no failures

    console.print(f"Verifying {len(manifest)} entries against manifest '{manifest_path}'...")
    # TODO: Implement verification logic
    all_ok = True
    missing_files = 0
    hash_mismatches = 0
    verified_ok = 0

    # Use rich progress for visual feedback during hashing
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
    )

    with progress:
        verify_task = progress.add_task("Verifying files...", total=len(manifest))

        for video_uri, entry in manifest.items():
            filename = entry.get("filename")
            expected_hash = entry.get("sha256")
            video_name = entry.get("name", os.path.basename(filename) if filename else video_uri)

            if not filename or not expected_hash:
                console.print(f"[yellow]Warning:[/yellow] Skipping invalid manifest entry for {video_uri} (missing filename or hash).")
                all_ok = False
                progress.update(verify_task, advance=1)
                continue

            filepath = os.path.join(dest_dir, filename)
            progress.update(verify_task, description=f"Checking {video_name}...")

            if not os.path.exists(filepath):
                console.print(f"[red]MISSING:[/red] File '{filename}' for video '{video_name}' not found.")
                all_ok = False
                missing_files += 1
                progress.update(verify_task, advance=1)
                continue

            progress.update(verify_task, description=f"Hashing {video_name}...")
            actual_hash = calculate_sha256(filepath)

            if actual_hash is None:
                console.print(f"[red]ERROR:[/red] Could not calculate hash for existing file '{filename}'. Check permissions or disk errors.")
                all_ok = False
                # Treat as mismatch for summary?
                hash_mismatches +=1
            elif actual_hash != expected_hash:
                console.print(f"[red]MISMATCH:[/red] Hash mismatch for '{filename}' (Video: '{video_name}').")
                console.print(f"  Expected: {expected_hash}")
                console.print(f"  Actual:   {actual_hash}")
                all_ok = False
                hash_mismatches += 1
            else:
                 verified_ok += 1
                 # Optionally print success for verbose mode
                 # console.print(f"[green]OK:[/green] '{filename}'")
            
            progress.update(verify_task, advance=1)

    # --- Verification Summary --- 
    console.print("\n--- Verification Summary ---")
    if all_ok:
        console.print(f"[bold green]Success![/] All {verified_ok} files verified successfully.")
    else:
        console.print(f"Verification completed with issues:")
        console.print(f"  - [green]Files OK:[/green] {verified_ok}")
        if missing_files > 0:
            console.print(f"  - [red]Missing Files:[/red] {missing_files}")
        if hash_mismatches > 0:
             console.print(f"  - [red]Hash Mismatches:[/red] {hash_mismatches}")
        console.print("Consider running `vmb sync` again, or use `--fix` (if implemented) to attempt repairs.")

    # console.print("Verification placeholder complete.")
    return all_ok

def update_manifest_entry(
    manifest_data: ManifestData, 
    video_data: Dict[str, Any], 
    filepath: str,
    quality: str,
    sha256_hash: str
) -> bool:
    """Update a manifest entry for a downloaded file.
    
    Args:
        manifest_data: The manifest data to update (modified in place)
        video_data: The video metadata from the Vimeo API
        filepath: Path to the downloaded file
        quality: The video quality string
        sha256_hash: The SHA-256 hash of the downloaded file
        
    Returns:
        True if the update was successful, False otherwise
    """
    video_uri = video_data.get("uri")
    if not video_uri:
        console.print(f"[yellow]Warning:[/yellow] Cannot update manifest for video with missing URI: {video_data.get('name')}")
        return False

    filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    
    # Update manifest
    manifest_data[video_uri] = {
        "filename": os.path.basename(filepath),
        "quality": quality,
        "sha256": sha256_hash,
        "download_time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_modified_time": video_data.get("modified_time"),
        "filesize": filesize,
        "name": video_data.get("name")  # Store name for easier identification
    }
    
    return True

def update_manifest_from_files(dest_dir: str, manifest_data: ManifestData, db: Optional[ManifestDB] = None) -> bool:
    """Scans the destination directory for video files and updates the manifest.
    
    This is used to repair the manifest when files exist on disk but aren't
    properly tracked in the manifest.
    
    Args:
        dest_dir: Directory containing the downloaded files
        manifest_data: The manifest data dictionary to update
        db: Optional ManifestDB instance for database updates
        
    Returns:
        True if files were found and added to the manifest, False otherwise
    """
    console.print("Scanning directory for video files not in manifest...")
    
    # Check if directory exists
    if not os.path.exists(dest_dir):
        console.print(f"[red]Error:[/red] Directory {dest_dir} does not exist.")
        return False
    
    # Get a list of video files in the directory (excluding temporary files)
    video_extensions = ['.mp4', '.mov', '.webm', '.m4v', '.avi', '.mkv']
    video_files = []
    
    for filename in os.listdir(dest_dir):
        # Skip manifest files and temporary files
        if (filename == "vmb_manifest.json" or filename == "vmb_manifest.db" or 
            filename.endswith(".db-shm") or filename.endswith(".db-wal") or
            filename.endswith(".tmp") or filename.endswith("._vmb_part")):
            continue
        
        # Check if it's a video file
        _, ext = os.path.splitext(filename)
        if ext.lower() in video_extensions:
            video_files.append(filename)
    
    # If no video files found, return early
    if not video_files:
        console.print("[yellow]No video files found in the destination directory.[/]")
        return False
    
    # Create a lookup from filename to URI for existing manifest entries
    filename_to_uri = {}
    for uri, entry in manifest_data.items():
        if "filename" in entry:
            filename_to_uri[entry["filename"]] = uri
    
    # Progress display for processing files
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("[yellow]Processing files...", total=len(video_files))
        
        # Counter for newly added files
        added_count = 0
        exists_count = 0
        
        # Process each video file
        for filename in video_files:
            progress.update(task, description=f"[yellow]Processing {filename}[/]")
            
            # Skip if already in manifest
            if filename in filename_to_uri:
                exists_count += 1
                progress.advance(task)
                continue
            
            # Get file path and calculate hash
            file_path = os.path.join(dest_dir, filename)
            sha256_hash = calculate_sha256(file_path)
            
            if not sha256_hash:
                console.print(f"[yellow]Warning:[/] Could not calculate hash for {filename}. Skipping.")
                progress.advance(task)
                continue
            
            # Create a temporary URI for this file (we don't know the actual URI)
            # Format: /videos/local/<filename>
            temp_uri = f"/videos/local/{filename}"
            filesize = os.path.getsize(file_path)
            
            # Create manifest entry
            manifest_data[temp_uri] = {
                "filename": filename,
                "quality": "unknown",  # We don't know the quality
                "sha256": sha256_hash,
                "download_time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "api_modified_time": None,  # We don't know the API modified time
                "filesize": filesize,
                "name": os.path.splitext(filename)[0]  # Use filename without extension as name
            }
            
            # If we have a database connection, update it directly
            if db is not None:
                entry_data = manifest_data[temp_uri].copy()
                entry_data["uri"] = temp_uri
                db.update_video(entry_data)
            
            added_count += 1
            progress.advance(task)
    
    # Report results
    if added_count > 0:
        console.print(f"[green]Added {added_count} new files to manifest. {exists_count} files were already tracked.[/]")
        return True
    else:
        console.print(f"[yellow]No new files added to manifest. {exists_count} files were already tracked.[/]")
        return False

def find_incomplete_downloads(dest_dir: str) -> List[str]:
    """Find incomplete downloads with .vmb_part extension in the destination directory.
    
    Args:
        dest_dir: Directory containing the downloaded files
        
    Returns:
        List of paths to incomplete download files
    """
    if not os.path.exists(dest_dir):
        return []
    
    incomplete_files = []
    for filename in os.listdir(dest_dir):
        if filename.endswith("._vmb_part"):
            # Get the full path
            file_path = os.path.join(dest_dir, filename)
            incomplete_files.append(file_path)
    
    return incomplete_files

def verify_backup(dest_dir: str, manifest_data: ManifestData, db: Optional[ManifestDB] = None) -> Tuple[int, int, int]:
    """Verify the integrity of downloaded files against the manifest.
    
    Args:
        dest_dir: Directory containing the downloaded files
        manifest_data: The manifest data
        db: Optional ManifestDB instance
        
    Returns:
        Tuple of (verified_count, missing_count, corrupt_count)
    """
    console.print("[bold]Verifying backup integrity...[/]")
    
    verified_count = 0
    missing_count = 0
    corrupt_count = 0
    
    if not manifest_data:
        console.print("[yellow]Warning: Empty manifest, nothing to verify.[/]")
        return verified_count, missing_count, corrupt_count
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("[yellow]Verifying files...", total=len(manifest_data))
        
        for uri, entry in manifest_data.items():
            filename = entry.get("filename")
            expected_hash = entry.get("sha256")
            
            # Skip if no filename in manifest
            if not filename:
                progress.advance(task)
                continue
                
            progress.update(task, description=f"[yellow]Verifying {filename}[/]")
            
            file_path = os.path.join(dest_dir, filename)
            
            # Check if file exists
            if not os.path.exists(file_path):
                console.print(f"[red]Missing:[/] {filename}")
                missing_count += 1
                progress.advance(task)
                continue
            
            # If we have an expected hash, verify it
            if expected_hash:
                actual_hash = calculate_sha256(file_path)
                
                if actual_hash != expected_hash:
                    console.print(f"[red]Corrupt:[/] {filename} (Hash mismatch)")
                    corrupt_count += 1
                else:
                    verified_count += 1
            else:
                # No hash to verify against, consider it verified but warn
                console.print(f"[yellow]Warning:[/] {filename} has no hash in manifest, assuming OK")
                verified_count += 1
            
            progress.advance(task)
    
    console.print(f"[bold]Verification complete:[/] {verified_count} verified, {missing_count} missing, {corrupt_count} corrupt")
    return verified_count, missing_count, corrupt_count 