# AGENTS.md

## Project Intent

This repository is a macOS-only, pure-visual helper for `com.tencent.jkchess`.

Current design goal is:

- fixed wait after `Shift+D`
- capture one OCR ROI from the shop row
- use Apple Vision OCR to parse names and costs
- click manually calibrated slot centers

Do not evolve it toward invasive automation, memory reading, or process injection.

## Current Source Of Truth

The codebase has already been simplified around one stable path.

Treat the current implementation as intentional:

- fixed wait only
- window-relative ROI and click points
- manual 5-slot click centers
- batch clicking from right to left

Do not reintroduce previously removed branches unless the user explicitly asks for them.

## Main Runtime Flow

Runtime path:

1. `main.py`
2. `window.py`
3. `capture.py`
4. `ocr.py`
5. `matcher.py`
6. `action.py`

Hotkeys:

- `Shift+D`: run one recognition + click cycle
- `Cmd+Shift+R`: reload `config.toml`

## File Responsibilities

- `main.py`: orchestration, timing, debug output
- `trigger.py`: global hotkey listener
- `window.py`: find game window by bundle id and resolve relative geometry
- `capture.py`: Quartz screenshot only
- `ocr.py`: Apple Vision OCR and cost parsing
- `matcher.py`: OR match on target names and target costs
- `action.py`: click point resolution and batch clicking
- `calibrate.py`: record ROI and 5 manual click points into `config.toml`
- `config.toml`: runtime configuration

## Configuration Rules

Only `config.toml` is authoritative.

Important assumptions:

- `[window].enabled = true` means ROI and click points are relative to the game window
- `bundle_id = "com.tencent.jkchess"` is the canonical window match key
- `animation_delay` is the only wait control now
- `[click].slot_points` is the preferred click mode
- `click_y` is only a fallback when manual slot points are disabled or invalid

## Calibration Rules

Preferred operating mode:

- game window is not fullscreen
- window size stays fixed
- window may move

If window size changes, prefer recalibration over automatic scaling.

Use `calibrate.py` to update:

- `[roi]`
- `click_y`
- `[window].reference_width`
- `[window].reference_height`
- `[click].slot_points`

## Cost Parsing Rules

The project assumes valid costs are only `1..7`.

OCR noise from the gold icon is expected.
Examples the parser intentionally normalizes:

- `93 -> 3`
- `51 -> 1`
- `02 -> 2`
- `⑦ -> 7`

Unknown cost should remain unknown, not negative.

## Constraints For Future Changes

Prefer low-maintenance changes.

Good changes:

- improve OCR robustness within the current pipeline
- improve click stability
- improve calibration ergonomics
- improve logs and docs

Avoid these unless explicitly requested:

- adaptive wait / probe polling
- automatic scaling with resized windows
- complex window matching by title/owner keywords
- extra runtime modes that fork the codepath
- speculative architecture layering for a small script

## Editing Guidance

- keep the code simple and direct
- preserve ASCII unless the file already uses Chinese comments or messages
- prefer deleting dead branches over adding flags
- update `README.md` if user-visible behavior changes
- keep log wording precise: clicking is not the same as successful purchase

## Verification

There is no formal test suite.

Minimum verification after code changes:

```bash
.venv/bin/python -m py_compile main.py action.py calibrate.py capture.py logger.py matcher.py ocr.py permissions.py trigger.py window.py
```

If behavior changes around config or calibration, also re-read:

- `README.md`
- `config.toml`
