# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Single-file Python CLI tool (`save_config.py`) that backs up macOS dotfiles, credentials, and system configuration to iCloud Drive. Each run creates a timestamped directory under iCloud with GPG-encrypted sensitive data and plain copies of everything else.

Follows the exact same architecture as the sibling `../maintenance` project — single module, hatchling build, `uv tool install`, no runtime dependencies.

## Commands

```bash
poe install              # Install globally via uv tool
save-config --all        # Run all sections without prompts
save-config --section ssh,dotfiles   # Run specific sections
save-config --no-encrypt # Disable GPG encryption
save-config --log        # Tee output to timestamped log file
```

## Architecture

The module mirrors `../maintenance/maintenance.py` structure:

- **Color / Status / SectionResult** — shared UI primitives
- **Helpers** — `encrypt_to_dest()` and `tar_encrypt()` handle the encrypt-in-/tmp-then-move pattern so unencrypted data never touches iCloud
- **12 section functions** (`do_*`) — each returns `bool`, registered in `SECTIONS` list
- **Registry + dispatcher** — `SECTIONS` list of `(id, label, fn)` tuples; `run_section()` handles filtering, confirmation prompts, timing, and error catching
- **Section aliases** — `packages` (brew, volta, cargo, macos-apps), `encrypted` (ssh, my, config)
- **TeeWriter** — ANSI-stripping log tee, identical to maintenance

Key conventions:
- Output directory: `~/Library/Mobile Documents/com~apple~CloudDocs/My/my.Devices/Apple/Apple MacStudio/Configs/Home-<timestamp>`
- GPG recipient hardcoded to `i3oc9i@icloud.com`
- Dotfiles renamed with `dot.` prefix (e.g., `.zshrc` → `dot.zshrc`)
- Restore instructions are in the module docstring
