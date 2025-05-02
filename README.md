# Vimeo Library Backup Tool

A Python CLI tool to download and back up your Vimeo video library.

See `docs/PRD.md` for detailed requirements.

## Installation

```bash
# Clone repository
git clone https://github.com/Fakirim/vimeo-backup.git # Updated URL
cd vimeo-backup

# Set up virtual environment (Requires Python >= 3.11)
# Use the correct python command for your Python 3.11+ installation
python3.11 -m venv .venv # Or python3.12, python3, /path/to/python, etc.
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`

# Install dependencies
pip install -U pip
pip install -r requirements.txt

# Install the tool itself in editable mode
pip install -e .
```

## Usage

First, ensure your virtual environment is activated (`source .venv/bin/activate`).

```bash
# 1. Authenticate (Run once)
# Prompts for your Vimeo Personal Access Token (PAT)
# Requires 'public', 'private', 'video_files' scopes.
# Token is stored securely in your OS keyring.
vmb auth

# 2. Sync Videos
# Downloads new/updated videos to the destination directory.
# Creates/updates a 'vmb_manifest.json' file in the destination.
vmb sync --dest /path/to/your/backup --threads 4 --quality best

# Key sync options:
#   --dest DIR      [Required] Destination directory for backups.
#   --threads INT   Number of parallel downloads (default: 4).
#   --quality QUAL  Preferred quality: best, original, 1080p, 720p, etc. (default: best).
#   --since DATE    (TODO) Only download videos newer than this date/time.
#   --dry-run       Show what would be downloaded without downloading.

# 3. Verify Backup Integrity
# Checks downloaded files against the checksums in 'vmb_manifest.json'.
vmb verify --dest /path/to/your/backup

# Key verify options:
#   --dest DIR      [Required] Directory containing the backup and manifest.
#   --fix           (TODO) Attempt to re-download corrupted/missing files.

# 4. List Available Videos
# Lists videos found in your Vimeo account.
vmb list

# Key list options:
#   --json          Output the raw video data as JSON instead of a table.

# 5. Show Backup Statistics (TODO)
# (Not yet implemented)
vmb stats
```

## Manifest File

The `vmb sync` command creates and updates a file named `vmb_manifest.json` in your backup destination directory. This file stores information about each downloaded video, including:

*   Filename
*   Downloaded quality
*   SHA-256 checksum for integrity checks
*   Download timestamp
*   Video metadata (name, API modified time, etc.)

This file is used by `sync` to determine which videos need updating and by `verify` to check file integrity.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details (if one exists - typically added when formally publishing).

## Reporting Issues

Please report any bugs or request features using the [GitHub Issue Tracker](https://github.com/Fakirim/vimeo-backup/issues). # Updated URL

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues to discuss potential changes.

(Optional: Consider adding a `CONTRIBUTING.md` file with more detailed guidelines for code style, testing, and the pull request process.) 