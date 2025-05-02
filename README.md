# Vimeo Library Backup Tool (`vmb`)

<!-- Badges (update URLs when available) -->
[![Build Status](https://img.shields.io/github/actions/workflow/status/Fakirim/vimeo-backup/ci.yml?branch=main)](https://github.com/Fakirim/vimeo-backup/actions)
[![PyPI version](https://img.shields.io/pypi/v/vimeo-backup-tool.svg)](https://pypi.org/project/vimeo-backup-tool/)
[![Python Version](https://img.shields.io/pypi/pyversions/vimeo-backup-tool.svg)](https://pypi.org/project/vimeo-backup-tool/)
[![License](https://img.shields.io/github/license/Fakirim/vimeo-backup.svg)](https://github.com/Fakirim/vimeo-backup/blob/main/LICENSE)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A robust, cross-platform Python CLI tool designed for Vimeo Pro (and above) users to download and incrementally back up their **entire video library** to local storage. Built using the official Vimeo API to ensure compliance.

## Key Features

*   **Full Library Backup:** Downloads all videos accessible via your Vimeo API token.
*   **Incremental Sync:** Uses a local manifest (`vmb_manifest.json`) to track downloaded files and only downloads new or updated videos on subsequent runs.
*   **Quality Selection:** Choose your preferred video quality (`best`, `original`, `1080p`, `720p`, etc.).
*   **Resumable Downloads:** Automatically resumes interrupted downloads.
*   **Integrity Verification:** Calculates SHA-256 checksums after download and provides a `verify` command to check local files against the manifest.
*   **Concurrent Downloads:** Utilizes multiple threads (`--threads`) for faster downloading.
*   **Secure Token Storage:** Stores your Vimeo Personal Access Token (PAT) securely in the OS keyring.
*   **Cross-Platform:** Designed to work on macOS, Linux, and Windows.

## Installation

Requires **Python >= 3.11**.

```bash
# 1. Clone the repository
git clone https://github.com/Fakirim/vimeo-backup.git
cd vimeo-backup

# 2. Create and activate a virtual environment
#    (Use the command for your Python 3.11+ interpreter)
python3.11 -m venv .venv 
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate

# 3. Install dependencies
pip install -U pip
pip install -r requirements.txt

# 4. Install the tool in editable mode (recommended for development)
#    This makes the `vmb` command available in your activated environment.
pip install -e .

# OR: Install for general use (if published to PyPI later)
# pip install vimeo-backup-tool
```

## Usage

First, ensure your virtual environment is activated (`source .venv/bin/activate`).

**1. Authentication (Run Once)**

```bash
# Prompts for your Vimeo Personal Access Token (PAT).
# Requires 'public', 'private', and 'video_files' scopes.
# Get a token: https://developer.vimeo.com/apps
vmb auth
```
The token is stored securely in your OS keyring.

**2. Syncing Videos**

```bash
# Basic sync: Downloads new/updated videos to the specified directory
vmb sync --dest /path/to/your/backup

# Sync with options:
vmb sync --dest ~/Videos/VimeoBackup --threads 8 --quality 1080p

# Sync only videos modified since a specific date:
vmb sync --dest _Downloads --since "2024-05-01"

# Sync only videos modified since yesterday:
vmb sync --dest _Downloads --since "yesterday"

# See what would be downloaded without actually downloading:
vmb sync --dest /path/to/your/backup --dry-run
```
*   `--dest DIR`: **Required.** Directory to store downloaded videos and the manifest.
*   `--threads INT`: Number of parallel downloads (default: 4).
*   `--quality QUAL`: `best`, `original`, `4k`, `2k`, `1080p`, `720p`, `540p`, `360p` (default: `best`).
*   `--since STR`: Only consider videos modified since this date/time (formats: `YYYY-MM-DD`, `YYYY-MM-DD HH:MM:SS`, or `yesterday`).
*   `--dry-run`: Show actions without downloading.

**3. Verifying Backups**

```bash
# Check integrity of files in the backup directory against the manifest
vmb verify --dest /path/to/your/backup
```
*   `--dest DIR`: **Required.** Directory containing the videos and `vmb_manifest.json`.
*   `--fix`: (TODO) Attempt to re-download corrupted/missing files.

**4. Listing Videos**

```bash
# List videos in your Vimeo account in a table
vmb list

# List videos as raw JSON data
vmb list --json
```

**5. Showing Statistics (TODO)**

```bash
# (Not yet implemented)
vmb stats
```

## Manifest File (`vmb_manifest.json`)

The `vmb sync` command creates and updates `vmb_manifest.json` in your backup destination. This crucial file tracks:

*   Which videos have been downloaded (`video_uri` as key).
*   The local `filename` (including video ID and quality).
*   The downloaded `quality`.
*   The `sha256` checksum for integrity verification.
*   Vimeo's last `api_modified_time` for the video when it was downloaded.
*   Other metadata (`filesize`, `name`, `download_time_utc`).

It enables incremental downloads and the `vmb verify` command.

## Development Setup

Follow the Installation steps 1-4 above to set up an editable install.

To run linters and type checkers (as configured in `pyproject.toml`):

```bash
# Ensure virtual environment is active
source .venv/bin/activate

# Linting and formatting with Ruff
ruff check .
ruff format .

# Type checking with MyPy
mypy vmb/

# Running tests (TODO: Add tests!)
# pytest
```

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues on the [GitHub Issue Tracker](https://github.com/Fakirim/vimeo-backup/issues) to discuss potential changes or report bugs.

(Optional: Consider adding a `CONTRIBUTING.md` file with more detailed guidelines for code style, testing, and the pull request process.)

## License

This project is licensed under the MIT License. See the `LICENSE` file for details (if one exists).