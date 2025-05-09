import time
import vimeo
import requests
import re
from typing import Optional, List, Dict, Any, NamedTuple
from datetime import datetime, timedelta, timezone
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from . import config

console = Console()

# --- Constants ---
MY_VIDEOS_ENDPOINT = "/me/videos"
MAX_PER_PAGE = 100
# Fields requested for each video (adjust as needed for sync/download)
VIDEO_FIELDS = "uri,name,created_time,modified_time,duration,files,download"
# Retry mechanism parameters
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 2
BACKOFF_FACTOR = 2

# --- Custom Exceptions ---
class APIError(Exception):
    """Base exception for API related errors."""
    pass

class DownloadJob(NamedTuple):
    """Represents a video download job."""
    url: str
    target_path: str
    video_data: Dict[str, Any]
    video_name: str
    quality: str

class VimeoAPI:
    """Class for interacting with the Vimeo API."""
    def __init__(self, token: Optional[str] = None):
        """Initialize with token or get from config."""
        self.token = token or config.get_token()
        if not self.token:
            raise APIError("Vimeo token not found. Please run 'vmb auth' first.")
        
        # Initialize client
        self.client = vimeo.VimeoClient(token=self.token)
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a request to the Vimeo API with retries and error handling."""
        retries = 0
        wait_time = INITIAL_BACKOFF_SECONDS
        
        while retries < MAX_RETRIES:
            try:
                response = self.client.get(endpoint, params=params)
                
                # Check for errors
                if response.status_code == 401:
                    raise APIError("Authentication failed (401). Token may be invalid. Run 'vmb auth' again.")
                elif response.status_code == 403:
                    raise APIError("Permission denied (403). Token might lack required scopes.")
                elif response.status_code == 429:
                    # Rate limit - use retry-after header if available
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_time = int(retry_after) + 1
                        except ValueError:
                            pass
                    
                    console.print(f"API/Network error (Rate limit): Waiting {wait_time}s before retrying... (Attempt {retries+1}/{MAX_RETRIES})")
                    time.sleep(wait_time)
                    retries += 1
                    wait_time *= BACKOFF_FACTOR
                    continue
                
                # Raise for other errors
                response.raise_for_status()
                
                # Success!
                return response.json()
            
            except requests.ConnectionError as e:
                console.print(f"API/Network error (ConnectionError): {e}. Waiting {wait_time}s before retrying... (Attempt {retries+1}/{MAX_RETRIES})")
                time.sleep(wait_time)
                retries += 1
                wait_time *= BACKOFF_FACTOR
            
            except requests.RequestException as e:
                console.print(f"API/Network error ({type(e).__name__}): {e}. Waiting {wait_time}s before retrying... (Attempt {retries+1}/{MAX_RETRIES})")
                time.sleep(wait_time)
                retries += 1
                wait_time *= BACKOFF_FACTOR
        
        # If we get here, we've exhausted retries
        raise APIError(f"API request failed after {MAX_RETRIES} retries")
    
    def get_all_videos(self, max_count: Optional[int] = None, since_dt: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get all videos from the user's account, with optional filtering.
        
        Args:
            max_count: Optional maximum number of videos to fetch
            since_dt: Optional datetime to filter videos modified since this date
            
        Returns:
            List of video data dictionaries
        """
        all_videos = []
        page = 1
        current_uri = MY_VIDEOS_ENDPOINT
        params = {"per_page": MAX_PER_PAGE, "fields": VIDEO_FIELDS}
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("Fetching video list page 1...", total=None)
            
            while current_uri:
                progress.update(task, description=f"Fetching video list page {page}...")
                
                # Make the request
                data = self._make_request(current_uri, params)
                
                # Get videos from this page
                videos = data.get("data", [])
                if not videos:
                    break
                
                # Add to our list
                all_videos.extend(videos)
                
                # Filter by date if needed
                if since_dt:
                    # Convert since_dt to UTC if it's not timezone-aware
                    if since_dt.tzinfo is None:
                        since_dt = since_dt.replace(tzinfo=timezone.utc)
                    
                    # Filter in place to avoid creating a new list
                    i = 0
                    while i < len(all_videos):
                        video = all_videos[i]
                        # Parse the modified_time
                        try:
                            modified_time = video.get("modified_time")
                            if modified_time:
                                modified_dt = datetime.fromisoformat(modified_time.replace("Z", "+00:00"))
                                if modified_dt < since_dt:
                                    # Remove videos older than the since date
                                    all_videos.pop(i)
                                    continue
                        except (ValueError, TypeError):
                            # If we can't parse the date, keep the video
                            pass
                        i += 1
                
                # Check if we've reached the maximum count
                if max_count and len(all_videos) >= max_count:
                    all_videos = all_videos[:max_count]
                    break
                
                # Get the next page
                paging = data.get("paging", {})
                next_page_uri = paging.get("next")
                
                if next_page_uri:
                    current_uri = next_page_uri
                    params = {}  # Params are included in the next URI
                    page += 1
                else:
                    break
        
        console.print(f"Found {len(all_videos)} videos.")
        return all_videos
    
    def get_user_info(self) -> Dict[str, Any]:
        """Get information about the authenticated user."""
        return self._make_request("/me")

def get_user_info(token: Optional[str] = None) -> Dict[str, Any]:
    """Get information about the authenticated user.
    
    Args:
        token: Optional token to use instead of getting from config
        
    Returns:
        Dictionary containing user information
    """
    api = VimeoAPI(token)
    return api.get_user_info()

def clean_filename(name: str) -> str:
    """Clean a string to make it suitable for use as a filename.
    
    Args:
        name: The original string
        
    Returns:
        A cleaned string suitable for use as a filename
    """
    # Replace any characters that aren't alphanumeric, underscores, hyphens, or dots with underscores
    cleaned = re.sub(r'[^\w\-\.]', '_', name)
    
    # Remove leading/trailing underscores and limit length
    cleaned = cleaned.strip('_')
    
    # Limit length to avoid hitting MAX_PATH issues
    cleaned = cleaned[:100]
    
    # Ensure we have a non-empty filename
    if not cleaned:
        cleaned = "unnamed"
    
    return cleaned

def get_best_download_url(video_data: Dict[str, Any], preferred_quality: str = "original") -> Optional[str]:
    """Get the best download URL for a video based on preferred quality.
    
    Args:
        video_data: The video data dictionary from the API
        preferred_quality: The preferred quality ("original", "hd", "sd", etc.)
        
    Returns:
        The download URL or None if no suitable URL found
    """
    # Check if direct download links are available
    download_links = video_data.get("download", [])
    
    # First, look for the preferred quality
    for download in download_links:
        quality = download.get("quality")
        if quality == preferred_quality:
            return download.get("link")
    
    # If preferred quality not found, get the highest quality available
    # Sort by resolution (height) if available
    sorted_downloads = sorted(
        download_links,
        key=lambda x: int(x.get("height", 0)),
        reverse=True
    )
    
    # Return the highest quality link if available
    if sorted_downloads:
        return sorted_downloads[0].get("link")
    
    # No download links available
    return None 