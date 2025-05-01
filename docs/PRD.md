# Product Requirements Document (PRD)

## Project: **Vimeo Library Backup Tool**

Version 0.1 — 1 May 2025

---

### 1. Objective

Provide a cross‑platform **Python CLI** application that lets any Vimeo Pro user download and incrementally back‑up **their entire video library** (≈ 5 TB+) to local storage, with resume, integrity verification, and simple scheduling.
The tool *must* use Vimeo’s official API (`video_files` scope) to stay within Terms of Service. citeturn0search0

---

### 2. Success Criteria

| KPI                            | Target                             |
| ------------------------------ | ---------------------------------- |
| Complete 5 TB first‑run backup | ≤ 7 days on 100 Mb s⁻¹ line        |
| Re‑run after new uploads       | downloads ≥ 1 GB min within 10 min |
| Integrity check (`vmb verify`) | 100 % SHA‑256 match                |
| Unit‑test coverage             | ≥ 90 %                             |
| Cross‑OS support               | Win 11 • macOS 14 • Ubuntu 22.04   |

---

### 3. Scope

**In‑scope**

* OAuth 2 PAT authentication (`public private video_files`). citeturn0search7
* Paginated `/me/videos` retrieval (100 / page).
* Selecting highest‑resolution download file (`download` array). citeturn0search14
* Parallel, resumable, rate‑limited downloads.
* SHA‑256 manifest + `verify` command.
* Weekly scheduling example (cron / Task Scheduler).

**Out‑of‑scope**

* Uploading backups to cloud buckets.
* GUI or mobile app.
* Non‑owner video scraping.

---

### 4. User Stories

1. **Creator**: “As a content creator I run `vmb sync` and my external HDD gains every new clip automatically.”
2. **Sysadmin**: “As a sysadmin I schedule `vmb sync` weekly so backups happen overnight.”
3. **Auditor**: “As an auditor I run `vmb verify` and get a pass/fail report on my archive integrity.”

---

### 5. Non‑Functional Requirements

| Category        | Requirement                                                                     |
| --------------- | ------------------------------------------------------------------------------- |
| Performance     | ≥ 40 Mb s⁻¹/thread; obey Vimeo 500 req/5 min API throttle. citeturn0search11 |
| Reliability     | Resume partials; 5× exponential back‑off retries                                |
| Security        | PAT stored in OS keyring; TLS enforced                                          |
| Maintainability | PEP 8 + MyPy typed; modular packages                                            |
| Documentation   | Quick‑start, architecture diagram, API token guide                              |
| License         | MIT                                                                             |

---

### 6. Technical Stack

* **Python 3.11+** inside a **venv** (standard since 3.3). citeturn0search3turn0search6
* **PyVimeo** official SDK. citeturn0search1
* `requests`, `tqdm`, `click`, `keyring`, `pytest`, `rich`.

---

### 7. Architecture Overview

```
┌ Config (.env/CLI) ┐     token      ┌ Vimeo API Adapter ┐
└───────────────────┘──────────────▶│  /me/videos list  │──┐
                                     └──────────────────┘  │
                                               file links   ▼
                                       ┌──────────────┐  chunks  ┌────────────┐
                                       │ Downloader   │─────────▶│ Local Disk │
                                       └──────────────┘         └────────────┘
                                               ▲     verify          │
                                               └──── manifest ◀─────┘
```

**Packages & Responsibility**

| Module       | Purpose                                      |
| ------------ | -------------------------------------------- |
| `vmb.config` | Parse `.env`, CLI flags, keyring PAT         |
| `vmb.api`    | Pagination, link refresh, rate‑limit guard   |
| `vmb.core`   | Delta calc, job queue                        |
| `vmb.io`     | Stream download, resume, temp → final rename |
| `vmb.verify` | SHA‑256 manifest creation and checking       |

---

### 8. CLI Specification

| Command    | Example                                                      | Key Flags                              |
| ---------- | ------------------------------------------------------------ | -------------------------------------- |
| **sync**   | `vmb sync --dest /data/Vimeo --threads 4 --quality original` | `--since`, `--limit-rate`, `--dry-run` |
| **verify** | `vmb verify --dest /data/Vimeo`                              | `--fix`                                |
| **list**   | `vmb list --json`                                            | —                                      |
| **stats**  | `vmb stats`                                                  | —                                      |

---

### 9. Installation & Environment Setup

```bash
# clone project
$ git clone https://github.com/yourorg/vimeo-backup.git && cd vimeo-backup

# create isolated environment
$ python -m venv .venv               # built‑in venv module citeturn0search3
$ source .venv/bin/activate          # Windows: .venv\Scripts\activate
$ pip install -U pip && pip install -r requirements.txt

# first‑time auth
$ vmb auth  # prompts for PAT & stores in keyring
```

---

### 10. Testing & CI/CD

* **Unit tests** with `pytest` & `pytest-httpx` mocks.
* **Integration tests** using local HTTP server to emulate large files.
* GitHub Actions matrix: `ubuntu-latest`, `windows-latest`, `macos-latest` running `pytest`, `ruff`, `mypy`.

---

### 11. Milestones

| # | Deliverable                       | Owner | Due         |
| - | --------------------------------- | ----- | ----------- |
| 1 | Repo scaffold, venv, CLI skeleton | Dev   | 05‑May‑2025 |
| 2 | Auth flow + pagination            | Dev   | 10‑May‑2025 |
| 3 | Concurrent downloader + resume    | Dev   | 17‑May‑2025 |
| 4 | Verify & manifest logic           | Dev   | 22‑May‑2025 |
| 5 | Windows/macOS standalone builds   | Dev   | 27‑May‑2025 |
| 6 | Docs & README                     | Dev   | 29‑May‑2025 |
| 7 | Final QA & hand‑off               | PM    | 31‑May‑2025 |

---

### 12. Risks & Mitigation

| Risk              | Mitigation                                     |
| ----------------- | ---------------------------------------------- |
| API schema change | Pin PyVimeo version; daily CI smoke test       |
| PAT revoked       | Tool exits non‑zero; user alerted by log/email |
| ISP throttling    | `--limit-rate` flag, configurable threads      |

---

### 13. References

1. Vimeo API — *Working with Video File Links*. citeturn0search0
2. PyVimeo GitHub README. citeturn0search1
3. Python docs — `venv` module. citeturn0search3turn0search6
4. Vimeo API — Authentication & PAT scopes. citeturn0search7
5. Vimeo API — Rate limits. citeturn0search11

---

*Document owner:* **Kinane**
Prepared by: ChatGPT (OpenAI o3) — 1 May 2025
