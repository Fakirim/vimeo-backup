import os
import re # For filename sanitization
from typing import List, Dict, Any, Optional, Tuple
from rich.console import Console
from datetime import datetime, timezone # Added datetime, timezone

# Assuming verify module exists and has these definitions
from .verify import ManifestData, load_manifest, get_manifest_path 

console = Console()

# Define quality preferences order (highest to lowest)
# 'original' might be source or a high-quality transcode depending on Vimeo settings
# 'best' will try original first, then highest available resolution
QUALITY_PREFERENCE = ["original", "4k", "2k", "1080p", "720p", "540p", "360p"]

def sanitize_filename(name: str) -> str:
    """Removes potentially problematic characters from a filename."""
    # Remove characters that are definitely problematic on most OS
    name = re.sub(r'[\/*?:"<>|]', "", name)
    # Replace sequences of whitespace with a single underscore
    name = re.sub(r'\s+', '_', name)
    # Limit length to avoid issues (e.g., max 200 chars)
    return name[:200]


class DownloadJob:
    """Represents a video to be downloaded."""
    def __init__(self, video_data: Dict[str, Any], download_url: str, target_path: str, selected_quality: str):
        self.video_uri: str = video_data.get("uri", "unknown_uri")
        self.video_name: str = video_data.get("name", "unknown_name")
        self.download_url: str = download_url
        self.target_path: str = target_path
        self.selected_quality: str = selected_quality
        # Store the original video data dictionary for manifest updates
        self.video_data: Dict[str, Any] = video_data 
        # Add other relevant info if needed, e.g., expected filesize

    def __repr__(self) -> str:
        return f"DownloadJob(name='{self.video_name}', quality='{self.selected_quality}', target='{self.target_path}')"


def select_download_url(video_data: Dict[str, Any], preferred_quality: str) -> Optional[Tuple[str, str]]:
    """Selects the best available download URL based on preferred quality.

    Args:
        video_data: Dictionary containing video metadata from Vimeo API.
        preferred_quality: The desired quality ('best', 'original', '1080p', etc.).

    Returns:
        A tuple containing (selected_download_link, selected_quality_or_type) or None if no suitable link found.
    """
    download_options = video_data.get("download", [])
    if not download_options:
        console.print(f"[yellow]Warning:[/yellow] No download links found for video: {video_data.get('name', 'N/A')}")
        return None

    available_qualities: Dict[str, str] = {}
    for option in download_options:
        quality = option.get("quality")
        link_type = option.get("type") # e.g., "source", "video/mp4"
        link = option.get("link")
        if not link: continue

        # Map API quality/type to our preference keys
        key = None
        if quality and quality in ["hd", "sd"]: # General HD/SD are less preferred
            if option.get("height", 0) >= 1080: key = "1080p"
            elif option.get("height", 0) >= 720: key = "720p"
            elif option.get("height", 0) >= 540: key = "540p"
            elif option.get("height", 0) >= 360: key = "360p"
        elif quality: # Explicit qualities like 4k, 2k, 1080p etc.
             key = quality
        elif link_type and "source" in link_type.lower():
             key = "original"

        if key:
             # Store the highest resolution found for a given quality key
             # This handles cases where 'hd' might map to 1080p or 720p
             if key not in available_qualities: # Or if current link is higher res for same key (optional)
                 available_qualities[key] = link

    # Determine search order based on preference
    search_order = []
    if preferred_quality == "best":
        search_order = QUALITY_PREFERENCE
    elif preferred_quality in QUALITY_PREFERENCE:
        # Start with the exact match, then go down the list
        try:
            start_index = QUALITY_PREFERENCE.index(preferred_quality)
            search_order = QUALITY_PREFERENCE[start_index:]
        except ValueError:
            search_order = QUALITY_PREFERENCE # Fallback if preference not in list
    else: # Should not happen with click.Choice, but defensively...
        search_order = QUALITY_PREFERENCE

    # Find the best match
    for quality_key in search_order:
        if quality_key in available_qualities:
            return available_qualities[quality_key], quality_key

    # Fallback: if nothing matched preference, return the first link available
    if download_options:
         first_link = download_options[0].get("link")
         first_quality = download_options[0].get("quality", "unknown")
         if first_link:
              console.print(f"[yellow]Warning:[/yellow] Preferred quality '{preferred_quality}' not found for '{video_data.get('name')}'. Falling back to first available link ({first_quality}).")
              return first_link, first_quality

    console.print(f"[red]Error:[/red] Could not find any usable download link for video '{video_data.get('name')}'.")
    return None


def prepare_download_jobs(
    videos: List[Dict[str, Any]],
    dest_dir: str,
    preferred_quality: str,
    manifest_data: ManifestData,
    since_dt: Optional[datetime] = None # Add since_dt parameter
) -> List[DownloadJob]:
    """Determines which videos need downloading based on the manifest and filters.

    Args:
        videos: List of video metadata dicts from the API.
        dest_dir: The target backup directory.
        preferred_quality: The user's preferred download quality.
        manifest_data: The loaded manifest data.
        since_dt: Optional datetime object. If provided, only videos modified
                  after this time will be considered for download.

    Returns:
        A list of DownloadJob objects for videos that need downloading.
    """
    jobs: List[DownloadJob] = []
    skipped_exist = 0
    skipped_no_url = 0
    skipped_since = 0 # Counter for --since skips
    skipped_file_exists = 0 # Counter for existing files skipped without manifest match

    # Ensure since_dt is timezone-aware (assume UTC if naive)
    aware_since_dt: Optional[datetime] = None
    if since_dt:
        if since_dt.tzinfo is None or since_dt.tzinfo.utcoffset(since_dt) is None:
            aware_since_dt = since_dt.replace(tzinfo=timezone.utc)
            console.print(f"[grey]Assuming UTC for --since filter: {aware_since_dt}[/]")
        else:
            aware_since_dt = since_dt

    for video in videos:
        video_uri = video.get("uri")
        video_name = video.get("name", "unknown_video")
        api_modified_time_str = video.get("modified_time") # String like 2024-01-15T10:00:00+00:00

        if not video_uri:
             console.print(f"[yellow]Warning: Skipping video with missing URI: {video_name}[/]")
             skipped_no_url += 1
             continue

        # --- Since Filter --- 
        video_modified_dt: Optional[datetime] = None
        if api_modified_time_str:
            try:
                # Parse ISO 8601 string into timezone-aware datetime
                video_modified_dt = datetime.fromisoformat(api_modified_time_str)
            except ValueError:
                 console.print(f"[yellow]Warning: Could not parse modified_time '{api_modified_time_str}' for video {video_name}. Skipping --since check for this video.[/]")
        
        if aware_since_dt and video_modified_dt:
            if video_modified_dt <= aware_since_dt:
                # console.print(f"[grey]Skipping:[/grey] '{video_name}' (Modified {video_modified_dt} <= Since {aware_since_dt}).")
                skipped_since += 1
                continue # Skip this video entirely if it's not newer than --since

        # --- Quality Selection --- 
        selection_result = select_download_url(video, preferred_quality)
        if not selection_result:
            skipped_no_url += 1
            continue
        download_url, selected_quality = selection_result

        # --- Filename Generation --- 
        video_id = video_uri.split('/')[-1]
        sanitized_name = sanitize_filename(video_name)
        extension = ".mp4"
        potential_filename = f"{video_id}-{sanitized_name}-{selected_quality}{extension}"
        target_path = os.path.join(dest_dir, potential_filename)

        # --- Manifest Check (Delta Logic) ---
        manifest_entry = manifest_data.get(video_uri)

        needs_download = False
        reason = ""

        if not manifest_entry:
            # --- Check if file exists even without manifest entry ---
            if os.path.exists(target_path):
                needs_download = False
                reason = "File exists on disk, but missing from manifest (skipping download)"
                skipped_file_exists += 1
            else:
                needs_download = True
                reason = "Not found in manifest and file missing"
        else:
            manifest_filename = manifest_entry.get("filename")
            manifest_filepath = os.path.join(dest_dir, manifest_filename) if manifest_filename else None

            if not manifest_filepath or not os.path.exists(manifest_filepath):
                 needs_download = True
                 reason = f"File '{manifest_filename or 'unknown'}' missing"
            # --- Add check if file exists even if manifest says it's missing ---
            elif os.path.exists(target_path):
                 needs_download = False
                 reason = f"File exists on disk, but manifest indicated missing (skipping download)"
                 skipped_file_exists += 1
            elif manifest_entry.get("quality") != selected_quality:
                 needs_download = True
                 reason = f"Quality changed (manifest: {manifest_entry.get('quality')}, wanted: {selected_quality})"
            # Check modified time only if we haven't already decided to download
            elif video_modified_dt and manifest_entry.get("api_modified_time") and video_modified_dt.isoformat() > manifest_entry.get("api_modified_time"):
                 needs_download = True
                 # Compare ISO strings for simplicity, assuming consistent format
                 reason = f"API modified time newer ({video_modified_dt.isoformat()} > {manifest_entry.get('api_modified_time')})"

        if needs_download:
            console.print(f"[cyan]Queueing:[/cyan] '{video_name}' ({selected_quality}) Reason: {reason}.")
            jobs.append(DownloadJob(video, download_url, target_path, selected_quality))
        else:
             # Only count as skipped_exist if not skipped by --since filter earlier
            skipped_exist += 1
            pass

    if skipped_since > 0:
        console.print(f"[grey]Skipped {skipped_since} videos not modified since filter date.[/]")
    if skipped_exist > 0:
        console.print(f"[grey]Skipped {skipped_exist} videos already present and up-to-date in manifest.[/]")
    if skipped_file_exists > 0:
        console.print(f"[yellow]Skipped {skipped_file_exists} videos found on disk but missing/mismatched in manifest (manifest may need update via verify/sync).[/]")
    if skipped_no_url > 0:
         console.print(f"[yellow]Skipped {skipped_no_url} videos due to missing download URLs.[/]")

    return jobs 