# Legacy Archive: 2026-05-25

These files were moved out of the MarcoMonitor root when
`the-dial-treasury-v1/` became the only active US Treasury factor dashboard.

## Archived Directories

- `my-app/`: older Next.js product-style prototype.
- `static-site/`: older standalone static pages.
- `the-dial-personal/`: older personal static version with CSV import scripts.
- `the-dial-optimized/`: optimized static HTML/CSS/JS snapshot.
- `the-dial-v3/`: previous macro dashboard mainline.
- `output/`: historical Playwright screenshots and visual QA artifacts.
- `test-results/`: historical test output artifacts.

`output/` and `test-results/` are retained as historical QA artifacts from the
legacy implementations. Do not append new runtime artifacts here; current
visual checks and test output should stay under ignored local paths unless a
specific artifact is intentionally promoted into documentation.

## Archived Root Files

- `TechSpec.md`
- `design.md`
- `CHANGES.md`
- `fix.md`
- `The Dial.pdf`
- `sp500_history.csv`

## Active Replacement

Use `../../../../the-dial-treasury-v1/` for current development and runtime
work. Use `../../../../PROJECT_STATUS.md` and `../../../../README.md` for the
current workspace orientation.

Archived content is retained only for reference. Do not wire new features,
tests, or docs against these paths.
