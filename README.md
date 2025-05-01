# Vimeo Library Backup Tool

A Python CLI tool to download and back up your Vimeo video library.

See `docs/PRD.md` for detailed requirements.

## Installation

```bash
# Clone repository
git clone <repository_url>
cd vimeo-backup

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Authenticate (first time)
vmb auth

# Sync videos
vmb sync --dest /path/to/backup

# Verify integrity
vmb verify --dest /path/to/backup
``` 