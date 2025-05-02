import os
import json
import hashlib
from typing import Dict, Any, Optional
from rich.console import Console

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


def calculate_sha256(filepath: str) -> Optional[str]:
    """Calculates the SHA-256 hash of a file.

    Reads the file in chunks to handle large files efficiently.

    Args:
        filepath: Path to the file.

    Returns:
        The hex digest of the SHA-256 hash, or None if the file doesn't exist
        or cannot be read.
    """
    if not os.path.exists(filepath):
        return None
    
    hasher = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(HASH_CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError as e:
        console.print(f"[red]Error reading file for hashing '{filepath}': {e}[/]")
        return None
    except Exception as e: # Catch any other unexpected errors
        console.print(f"[red]Unexpected error hashing file '{filepath}': {e}[/]")
        return None


def get_manifest_path(dest_dir: str) -> str:
    """Returns the expected path to the manifest file in the destination directory."""
    return os.path.join(dest_dir, MANIFEST_FILENAME)


def load_manifest(manifest_path: str) -> ManifestData:
    """Loads the manifest data from a JSON file.

    Args:
        manifest_path: The full path to the manifest JSON file.

    Returns:
        A dictionary containing the manifest data. Returns an empty dict if
        the file doesn't exist or is invalid JSON.
    """
    if not os.path.exists(manifest_path):
        return {}
    try:
        with open(manifest_path, "r") as f:
            data = json.load(f)
            if not isinstance(data, dict): # Basic validation
                 console.print(f"[yellow]Warning:[/yellow] Manifest file '{manifest_path}' does not contain a valid JSON object. Starting fresh.")
                 return {}
            return data
    except json.JSONDecodeError as e:
        console.print(f"[red]Error decoding manifest file '{manifest_path}': {e}. Starting fresh.[/]")
        return {}
    except OSError as e:
         console.print(f"[red]Error reading manifest file '{manifest_path}': {e}. Starting fresh.[/]")
         return {}
    except Exception as e: # Catch any other unexpected errors
         console.print(f"[red]Unexpected error loading manifest '{manifest_path}': {e}. Starting fresh.[/]")
         return {}


def save_manifest(manifest_path: str, manifest_data: ManifestData) -> bool:
    """Saves the manifest data to a JSON file.

    Args:
        manifest_path: The full path to the manifest JSON file.
        manifest_data: The dictionary containing the manifest data.

    Returns:
        True if saving was successful, False otherwise.
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=2) # Use indent for readability
        return True
    except OSError as e:
        console.print(f"[red]Error writing manifest file '{manifest_path}': {e}[/]")
        return False
    except Exception as e: # Catch any other unexpected errors
        console.print(f"[red]Unexpected error saving manifest '{manifest_path}': {e}[/]")
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
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
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

# Placeholder for updating the manifest after download
def update_manifest_entry(
    manifest_data: ManifestData, 
    video_data: Dict[str, Any], 
    filepath: str,
    quality: str,
    sha256_hash: str
) -> None:
    """Adds or updates an entry in the manifest data dictionary.
    
    Args:
        manifest_data: The dictionary representing the manifest (will be modified).
        video_data: The video metadata from the Vimeo API.
        filepath: The final path of the downloaded file.
        quality: The quality identifier for the downloaded file.
        sha256_hash: The calculated SHA-256 hash of the downloaded file.
    """
    video_uri = video_data.get("uri")
    if not video_uri:
        console.print(f"[yellow]Warning:[/yellow] Cannot update manifest for video with missing URI: {video_data.get('name')}")
        return

    filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    
    manifest_data[video_uri] = {
        "filename": os.path.basename(filepath),
        "quality": quality,
        "sha256": sha256_hash,
        "download_time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_modified_time": video_data.get("modified_time"),
        "filesize": filesize,
        "name": video_data.get("name") # Store name for easier identification
    }
    # Note: This modifies the dictionary in-place. Caller needs to save it. 