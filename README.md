# Vimeo Backup Tool

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)

A robust command-line tool for backing up your Vimeo videos to local storage, designed for large video collections (10,000+ videos).

## 📋 Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Authentication](#authentication)
- [Usage](#usage)
  - [Basic Sync](#basic-sync)
  - [Advanced Options](#advanced-options)
  - [Verification](#verification)
  - [Manifest Repair](#manifest-repair)
  - [Resume Downloads](#resume-downloads)
  - [Build Database](#build-database)
- [Upgrading from JSON to SQLite](#upgrading-from-json-to-sqlite)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)

## ✨ Features

- **Robust SQLite Database Backend**: Efficiently manages large video collections (17,000+ videos) with better performance and reliability than JSON
- **Automatic Manifest Repair**: Can scan and detect existing videos not in the manifest
- **Auto-Resume Downloads**: Automatically resumes interrupted downloads
- **Verify Integrity**: Validates downloaded videos against checksums
- **Concurrent Downloads**: Speeds up backup process with multi-threading
- **Quality Selection**: Choose your preferred video quality
- **Date Filtering**: Only download videos updated since a specific date
- **Incremental Backup**: Skip videos that already exist locally
- **Database Builder**: Build a database from existing downloaded videos without creating JSON files
- **Graceful Cancellation**: Safely interrupt downloads with Ctrl+C while preserving progress

## 🚀 Installation

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package in development mode
pip install -e .

# Ensure you have the correct version of rich
pip install rich==13.7.0
```

## 🔑 Authentication

Before using the tool, you need to authenticate with Vimeo:

```bash
vmb auth
```

This will prompt you to enter your Vimeo Personal Access Token (PAT).

**Important**: Your token needs the following scopes:
- `public`
- `private`
- `video_files`

Generate your token at [https://developer.vimeo.com/apps](https://developer.vimeo.com/apps).

## 📥 Usage

### Basic Sync

To download all your Vimeo videos to a local directory:

```bash
vmb sync --dest /path/to/download/directory
```

### Advanced Options

| Option | Description | Example |
|--------|-------------|---------|
| `--threads` | Set number of concurrent downloads | `--threads 5` |
| `--since` | Only download videos modified after date | `--since 2023-01-01` |
| `--quality` | Specify video quality to download | `--quality 1080p` |
| `--use-json` | Use JSON storage instead of SQLite | `--use-json` |
| `--dry-run` | Preview downloads without downloading | `--dry-run` |

Example with multiple options:

```bash
vmb sync --dest /path/to/videos --threads 5 --since 2023-01-01 --quality 1080p
```

### Verification

Verify the integrity of your downloaded videos:

```bash
vmb verify --dest /path/to/download/directory
```

### Manifest Repair

Detect videos in your destination directory that aren't tracked in the manifest:

```bash
vmb verify --dest /path/to/download/directory --repair-manifest
```

### Resume Downloads

Find and resume any interrupted downloads:

```bash
vmb verify --dest /path/to/download/directory --resume-incomplete
```

### Build Database

Create a database from existing downloaded videos without generating JSON files:

```bash
vmb build-db --dest /path/to/download/directory
```

## 🔄 Upgrading from JSON to SQLite

If you've been using an older version with JSON storage:

1. The tool will automatically detect your JSON manifest
2. It will convert it to SQLite the first time you run with the `--use-db` flag (which is now the default)
3. Your original JSON files will be preserved

## ❓ Troubleshooting

### Network Issues

If you encounter `Network is unreachable` errors:

1. Check your internet connection
2. Verify you can reach Vimeo's API: `ping api.vimeo.com`
3. Configure proxy settings if behind a proxy

### API Errors

If you encounter API errors:

1. Verify your token is valid: Run `vmb auth` to set a new token
2. Check for rate limiting (the tool automatically retries with backoff)
3. Check [Vimeo Developer Status](https://developer.vimeo.com/api/status) for service issues

### Keyring Issues

If you see `No recommended backend was available` during authentication:

1. Install a supported keyring backend: `pip install keyrings.alt`
2. For headless environments, use the file-based backend

### Rich Library Issues

If you see `ImportError: cannot import name 'FileTransferSpeedColumn' from 'rich.progress'`:

1. Update your rich library: `pip install rich==13.7.0`
2. This specific version includes the components needed for progress display

## 🛠️ Development

### Project Structure

```
vmb/
├── api.py      # Vimeo API interaction
├── cli.py      # Command-line interface
├── config.py   # Configuration and token management
├── core.py     # Core functionality and types
├── db.py       # SQLite database backend
├── io.py       # File I/O and download logic
└── verify.py   # Verification and manifest management
```

### Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
