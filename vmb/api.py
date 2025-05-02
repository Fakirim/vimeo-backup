import time
import vimeo
import requests # Import requests for exception handling
from typing import Optional, List, Dict, Any
from rich.console import Console

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
class VimeoApiError(Exception):
    """Base exception for Vimeo API related errors."""
    pass

class MissingTokenError(VimeoApiError):
    """Raised when the Vimeo API token cannot be found."""
    def __init__(self, message="Vimeo token not found. Please run `vmb auth` first."):
        super().__init__(message)

class RateLimitError(VimeoApiError):
    """Raised specifically for 429 Rate Limit errors after retries."""
    pass

# --- API Client Setup ---
def get_vimeo_client() -> vimeo.VimeoClient:
    """Initializes and returns a VimeoClient instance.

    Retrieves the token from config.

    Returns:
        An initialized VimeoClient instance.

    Raises:
        MissingTokenError: If the token cannot be retrieved from the keyring.
    """
    token = config.get_token()
    if not token:
        raise MissingTokenError()

    # Consider adding a User-Agent string here for better identification
    return vimeo.VimeoClient(token=token)


# --- Core API Logic ---
def _make_api_request(
    client: vimeo.VimeoClient,
    uri: str,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Makes a GET request to the Vimeo API with error handling and retries.

    Handles rate limiting (429) with exponential backoff.
    Handles common HTTP errors (401, 403) by raising specific exceptions.

    Args:
        client: An initialized VimeoClient instance.
        uri: The API endpoint URI.
        params: Optional dictionary of query parameters.

    Returns:
        The JSON response data as a dictionary.

    Raises:
        VimeoApiError: For unrecoverable API errors (auth, permission, network).
        RateLimitError: If rate limited after exhausting retries.
        requests.exceptions.RequestException: For underlying network issues.
    """
    retries = 0
    backoff_time = INITIAL_BACKOFF_SECONDS

    while retries <= MAX_RETRIES:
        try:
            response = client.get(uri, params=params)

            # --- Handle Specific Status Codes ---
            if response.status_code == 401:
                raise VimeoApiError("Authentication failed (401). Invalid token? Run `vmb auth` again.")
            if response.status_code == 403:
                raise VimeoApiError("Permission denied (403). Token might lack required scopes (public, private, video_files). Check PAT scopes.")

            if response.status_code == 429: # Rate limit
                if retries == MAX_RETRIES:
                    raise RateLimitError(f"Rate limit exceeded after {MAX_RETRIES} retries.")

                # Respect Retry-After header if present
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait_seconds = int(retry_after) + 1 # Add a small buffer
                        console.print(f"[yellow]Rate limit hit. Respecting Retry-After: waiting {wait_seconds}s...[/] (Attempt {retries + 1}/{MAX_RETRIES})",) 
                    except ValueError:
                        # Fallback to exponential backoff if header is not an integer
                        wait_seconds = backoff_time
                        console.print(f"[yellow]Rate limit hit. Waiting {wait_seconds}s (backoff)...[/] (Attempt {retries + 1}/{MAX_RETRIES})",)
                else:
                    # Use exponential backoff
                    wait_seconds = backoff_time
                    console.print(f"[yellow]Rate limit hit. Waiting {wait_seconds}s (backoff)...[/] (Attempt {retries + 1}/{MAX_RETRIES})",)

                time.sleep(wait_seconds)
                retries += 1
                backoff_time *= BACKOFF_FACTOR
                continue # Retry the request

            # Raise for other client/server errors (4xx excluding handled ones, 5xx)
            response.raise_for_status()

            # Success!
            return response.json()

        except requests.exceptions.RequestException as e:
            # Network-level errors (DNS, connection refused, timeout etc.)
            # Also catches potential HTTP errors raised by response.raise_for_status()
            # if they weren't handled specifically above (e.g., 5xx errors).
            if retries == MAX_RETRIES:
                 # Raise the underlying network/HTTP error after max retries
                 raise VimeoApiError(f"API request failed after {MAX_RETRIES} retries: {e}") from e 
            console.print(f"[yellow]API/Network error ({type(e).__name__}): {e}. Waiting {backoff_time}s before retrying...[/] (Attempt {retries + 1}/{MAX_RETRIES})",)
            time.sleep(backoff_time)
            retries += 1
            backoff_time *= BACKOFF_FACTOR
            continue # Retry network request

    # Should not be reached if loop condition is correct, but defensive coding
    raise VimeoApiError("Exceeded retry logic unexpectedly.")


def get_all_videos() -> List[Dict[str, Any]]:
    """Fetches all video metadata from the user's Vimeo account.

    Handles pagination and uses _make_api_request for robust calls.

    Returns:
        A list of dictionaries, where each dictionary represents a video's metadata.

    Raises:
        MissingTokenError: If the authentication token is not configured.
        VimeoApiError: For other API or network related issues during fetching.
        RateLimitError: If rate limited after exhausting retries.
    """
    client = get_vimeo_client() # Can raise MissingTokenError

    all_videos: List[Dict[str, Any]] = []
    page = 1
    current_uri: str = MY_VIDEOS_ENDPOINT
    params = {"per_page": MAX_PER_PAGE, "fields": VIDEO_FIELDS}

    with console.status("[cyan]Fetching video list from Vimeo...[/]") as status:
        while current_uri:
            status.update(f"[cyan]Fetching video list page {page}...[/]")
            try:
                data = _make_api_request(client, current_uri, params=params)

                videos_on_page = data.get("data", [])
                if not videos_on_page:
                    console.print(f"Page {page} contained no video data. Stopping.")
                    break

                all_videos.extend(videos_on_page)
                console.print(f"Fetched page {page} ({len(videos_on_page)} videos). Total: {len(all_videos)}")

                # Use the URI provided in 'next' for the next request
                # This handles pagination parameters correctly
                paging = data.get("paging", {})
                next_page_uri = paging.get("next")

                if next_page_uri:
                    current_uri = next_page_uri
                    params = {} # Params are included in the 'next' URI
                    page += 1
                else:
                    break # No more pages

            except (VimeoApiError, RateLimitError, requests.exceptions.RequestException) as e:
                console.print(f"[bold red]Failed to fetch videos: {e}[/]")
                # Re-raise the specific error to be handled by the caller (e.g., CLI)
                raise
            except Exception as e:
                # Catch unexpected errors during processing
                console.print(f"[bold red]An unexpected error occurred: {e}[/]")
                raise VimeoApiError(f"Unexpected error processing video list: {e}") from e

    console.print(f"[bold green]Finished fetching. Found {len(all_videos)} videos total.[/]")
    return all_videos 