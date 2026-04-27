# save-config

macOS configuration backup tool. Backs up dotfiles, SSH/GPG keys, shell history, Claude Code config, and package lists to iCloud Drive with GPG encryption for sensitive data.

## Installation

```bash
uv tool install .
```

## Usage

```bash
# Interactive mode — prompts y/N before each section
save-config

# Run all sections without prompts
save-config --all

# Run specific section(s) only
save-config --section ssh,dotfiles
save-config --section encrypted
save-config --section packages

# Disable GPG encryption for sensitive files
save-config --all --no-encrypt

# Log output to file (ANSI codes stripped in log)
save-config --all --log
save-config --all --log /tmp/save-config.log

# Override the backup destination (parent of Home-<timestamp>)
save-config --all --backup-dir /Volumes/Backup/Configs
SAVE_CONFIG_BACKUP_DIR=/Volumes/Backup/Configs save-config --all
```

The default destination is `~/Library/Mobile Documents/com~apple~CloudDocs/My/my.Devices/Apple/Apple Mac Studio/Configs`. The `--backup-dir` flag wins over `SAVE_CONFIG_BACKUP_DIR`, which wins over the default. A timestamped `Home-<timestamp>` subdirectory is always appended.

## Sections

| Section | What it does |
|---|---|
| `local-bin` | Copies `~/.local/bin/*.sh` and `*.py` scripts |
| `ssh` | Encrypts `~/.ssh` as tarball (excludes sockets) |
| `my` | Encrypts `~/.my` as tarball |
| `config` | Encrypts `~/.config` as tarball |
| `gpg-keys` | Exports GPG public/secret keys and ownertrust |
| `dotfiles` | Copies dotfiles with `dot.` prefix; encrypts `.zsh_history` |
| `claude` | Copies `~/.claude.json`, `~/.claude/` settings, plugins, skills |
| `agents` | Copies `~/.agents` directory |
| `brew` | Saves Homebrew formula and cask lists |
| `mise` | Saves list of mise-installed tools |
| `cargo` | Saves Cargo installed crates list |
| `macos-apps` | Saves installed macOS applications list |

### Aliases

| Alias | Expands to |
|---|---|
| `encrypted` | `ssh,my,config` |
| `packages` | `brew,mise,cargo,macos-apps` |

## Restore

```bash
# 1. Import GPG keys first (no decryption needed)
gpg --import dot.gnupg/secret-keys.asc
gpg --import dot.gnupg/public-keys.asc
gpg --import-ownertrust dot.gnupg/ownertrust.txt

# 2. Decrypt and extract tarballs
gpg -d dir.ssh.tgz.gpg | tar -xzf - -C ~
gpg -d dir.my.tgz.gpg | tar -xzf - -C ~
gpg -d dir.config.tgz.gpg | tar -xzf - -C ~
chmod 700 ~/.ssh && chmod 600 ~/.ssh/id_*

# 3. Decrypt other files
gpg -d dot.zsh_history.gpg > ~/.zsh_history
```

## License

[MIT](LICENSE)
