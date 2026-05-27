# Treasury Real Data Updater Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `the-dial-treasury-v1` from a static snapshot into an independently runnable Treasury dashboard with real public data and a daily background update loop.

**Architecture:** Add a Python stdlib ETL layer that fetches public data, normalizes it into `data/dashboard.json`, and a small local server that serves the app while running the ETL once per day. The browser keeps the current static fallback but prefers `data/dashboard.json` when served locally.

**Tech Stack:** Python 3 stdlib (`urllib`, `csv`, `xml.etree`, `json`, `http.server`, `threading`), vanilla HTML/CSS/JS, `unittest`.

---

### Task 1: Data Source Parsing

**Files:**
- Create: `the-dial-treasury-v1/treasury_data/sources.py`
- Test: `the-dial-treasury-v1/tests/test_sources.py`

- [x] Write tests for FRED CSV and Treasury XML parsing.
- [x] Run `python3 -m unittest discover -s the-dial-treasury-v1/tests` and confirm imports fail.
- [x] Implement source fetchers and parsers.
- [x] Re-run tests and confirm parser tests pass.

### Task 2: Dashboard JSON Builder

**Files:**
- Create: `the-dial-treasury-v1/treasury_data/build_dashboard.py`
- Test: `the-dial-treasury-v1/tests/test_build_dashboard.py`

- [x] Write tests for the generated JSON contract: `asOf`, `curve`, `groups`, `sourceStatus`, `generatedAt`.
- [x] Run tests and confirm builder import/contract fails.
- [x] Implement builder with real-source output and explicit modeled/manual source flags.
- [x] Re-run tests and confirm builder tests pass.

### Task 3: Update CLI And Daily Server

**Files:**
- Create: `the-dial-treasury-v1/scripts/update_data.py`
- Create: `the-dial-treasury-v1/scripts/serve.py`
- Test: `the-dial-treasury-v1/tests/test_scheduler.py`

- [x] Write tests for next-run scheduling and output file writing.
- [x] Run tests and confirm failures.
- [x] Implement update CLI and background daily server.
- [x] Re-run tests and confirm all Python tests pass.

### Task 4: Frontend Runtime Data Loading

**Files:**
- Modify: `the-dial-treasury-v1/index.html`
- Modify: `the-dial-treasury-v1/app.js`

- [x] Add a visible data status line in the hero/footer.
- [x] Make the frontend fetch `data/dashboard.json` with `cache: "no-store"` and fall back to `DEFAULT_DATA` if unavailable.
- [x] Preserve local score/weight overrides through `localStorage`.
- [x] Verify with Playwright that the generated JSON is used and the scorecard still works.

### Task 5: Documentation And Verification

**Files:**
- Modify: `the-dial-treasury-v1/README.md`

- [x] Document real data sources, source gaps, and daily background run command.
- [x] Run `python3 the-dial-treasury-v1/scripts/update_data.py --output the-dial-treasury-v1/data/dashboard.json`.
- [x] Run `python3 -m unittest discover -s the-dial-treasury-v1/tests`.
- [x] Run `node --check the-dial-treasury-v1/app.js`.
- [x] Start `python3 the-dial-treasury-v1/scripts/serve.py --once --port 8451` only when a browser verification is needed; otherwise use direct file checks.
