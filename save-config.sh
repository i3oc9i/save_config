#!/bin/bash
#
# RESTORE ON A NEW MACHINE:
#   1. Import GPG keys first (no decryption needed)
#      gpg --import dot.gnupg/secret-keys.asc
#      gpg --import dot.gnupg/public-keys.asc
#      gpg --import-ownertrust dot.gnupg/ownertrust.txt
#
#   2. Decrypt and extract tarballs
#      gpg -d dir.ssh.tgz.gpg | tar -xzf - -C ~
#      gpg -d dir.my.tgz.gpg | tar -xzf - -C ~
#      gpg -d dir.config.tgz.gpg | tar -xzf - -C ~
#      chmod 700 ~/.ssh && chmod 600 ~/.ssh/id_*
#
#   3. Decrypt other files
#      gpg -d dot.zsh_history.gpg > ~/.zsh_history
#

set -e
umask 077  # Ensure all created files are owner-only

# Optional: set ENCRYPT_SENSITIVE=1 to encrypt SSH/GPG backups
ENCRYPT_SENSITIVE="${ENCRYPT_SENSITIVE:-1}"
GPG_RECIPIENT="i3oc9i@icloud.com"

# Encrypt file locally in /tmp, then move to destination (unencrypted data never touches iCloud)
encrypt_to_destination() {
    local src="$1"
    local dest_dir="$2"
    if [[ "$ENCRYPT_SENSITIVE" == "1" && -f "$src" ]]; then
        local fname=$(basename "$src")
        local tmpfile="/tmp/${fname}"
        # Only copy if source is not already the temp file
        [[ "$src" != "$tmpfile" ]] && cp "$src" "$tmpfile"
        gpg --encrypt --recipient "$GPG_RECIPIENT" --batch --yes "$tmpfile"
        mv "${tmpfile}.gpg" "$dest_dir/"
        rm -f "$tmpfile"
    else
        cp "$src" "$dest_dir/"
    fi
}

ICLOUD_BASE="/Users/ivano/Library/Mobile Documents/com~apple~CloudDocs/My"
DATE_SUFFIX=$(date +%Y.%m.%d-%H.%M.%S)
ICLOUD_DIR="${ICLOUD_BASE}/my.Devices/Apple/Apple MacStudio/Configs/Home-${DATE_SUFFIX}"
HOME_DIR="$HOME"

# Create all destination directories
mkdir -p "${ICLOUD_DIR}"/{dot.localbin,dot.gnupg}

# Backup ~/.local/bin scripts (.sh and .py files)
echo "> Backing up ~/.local/bin scripts..."
for f in "${HOME_DIR}/.local/bin/"*.sh "${HOME_DIR}/.local/bin/"*.py; do
    [[ -f "$f" ]] && cp "$f" "${ICLOUD_DIR}/dot.localbin/"
done

# Backup ~/.my directory as encrypted tarball
echo "> Backing up ~/.my..."
if [[ -d "${HOME_DIR}/.my" ]]; then
    /usr/bin/tar -C "${HOME_DIR}" -czf "/tmp/dir.my.tgz" .my
    encrypt_to_destination "/tmp/dir.my.tgz" "${ICLOUD_DIR}"
    rm -f "/tmp/dir.my.tgz"
fi

# Backup ~/.ssh as encrypted tarball (excludes sockets)
echo "> Backing up ~/.ssh..."
if [[ -d "${HOME_DIR}/.ssh" ]]; then
    /usr/bin/tar -C "${HOME_DIR}" -czf "/tmp/dir.ssh.tgz" --exclude='*.sock' --exclude='agent.*' .ssh
    encrypt_to_destination "/tmp/dir.ssh.tgz" "${ICLOUD_DIR}"
    rm -f "/tmp/dir.ssh.tgz"
fi

# Backup ~/.config as encrypted tarball
echo "> Backing up ~/.config..."
/usr/bin/tar -C "${HOME_DIR}" -czf "/tmp/dir.config.tgz" .config
encrypt_to_destination "/tmp/dir.config.tgz" "${ICLOUD_DIR}"
rm -f "/tmp/dir.config.tgz"

# Backup GPG keys and trust database
echo "> Backing up GPG keys..."
if gpg --list-secret-keys &>/dev/null; then
    gpg --export --armor > "${ICLOUD_DIR}/dot.gnupg/public-keys.asc"
    gpg --export-secret-keys --armor > "${ICLOUD_DIR}/dot.gnupg/secret-keys.asc"
    gpg --export-ownertrust > "${ICLOUD_DIR}/dot.gnupg/ownertrust.txt"
else
    echo "  Warning: No GPG secret keys found, skipping"
fi

# Backup individual dotfiles
echo "> Backing up same ~/dotfiles..."
DOTFILES=(.claude.json .direnvrc .fdignore .rgignore .gitconfig .zsh_history .zsh_aliases .zshrc)
for dotfile in "${DOTFILES[@]}"; do
    if [[ -f "${HOME_DIR}/${dotfile}" ]]; then
        destname="dot.${dotfile#.}"
        if [[ "$dotfile" == ".zsh_history" ]]; then
            # Sensitive: encrypt locally, then move to iCloud
            cp "${HOME_DIR}/${dotfile}" "/tmp/${destname}"
            encrypt_to_destination "/tmp/${destname}" "${ICLOUD_DIR}"
            rm -f "/tmp/${destname}"
        else
            cp "${HOME_DIR}/${dotfile}" "${ICLOUD_DIR}/${destname}"
        fi
    else
        echo "  Warning: ${dotfile} not found, skipping"
    fi
done

# Backup ~/.claude config, plugins, and per-project memory
echo "> Backing up ~/.claude/..."
CLAUDE_SRC="${HOME_DIR}/.claude"
CLAUDE_DST="${ICLOUD_DIR}/dot.claude"
mkdir -p "${CLAUDE_DST}"

# Config files
for cfg in CLAUDE.md settings.json keybindings.json; do
    if [[ -f "${CLAUDE_SRC}/${cfg}" ]]; then
        cp "${CLAUDE_SRC}/${cfg}" "${CLAUDE_DST}/${cfg}"
    else
        echo "  Warning: ~/.claude/${cfg} not found, skipping"
    fi
done

# Plugin config files
for pcfg in installed_plugins.json blocklist.json known_marketplaces.json; do
    if [[ -f "${CLAUDE_SRC}/plugins/${pcfg}" ]]; then
        mkdir -p "${CLAUDE_DST}/plugins"
        cp "${CLAUDE_SRC}/plugins/${pcfg}" "${CLAUDE_DST}/plugins/${pcfg}"
    else
        echo "  Warning: ~/.claude/plugins/${pcfg} not found, skipping"
    fi
done

# Skills directory (copy regular files, record symlinks for restore)
if [[ -d "${CLAUDE_SRC}/skills" ]]; then
    mkdir -p "${CLAUDE_DST}/skills"
    for item in "${CLAUDE_SRC}/skills"/*; do
        [[ -e "${item}" ]] || continue
        if [[ -L "${item}" ]]; then
            echo "ln -s \"$(readlink "${item}")\" \"$(basename "${item}")\"" >> "${CLAUDE_DST}/skills/SYMLINKS.sh"
        else
            cp -R "${item}" "${CLAUDE_DST}/skills/"
        fi
    done
else
    echo "  Warning: ~/.claude/skills not found, skipping"
fi

# Optional config directories (rules, commands, agents, agent-memory)
for cfgdir in rules commands agents agent-memory; do
    if [[ -d "${CLAUDE_SRC}/${cfgdir}" ]]; then
        mkdir -p "${CLAUDE_DST}/${cfgdir}"
        cp -R "${CLAUDE_SRC}/${cfgdir}/." "${CLAUDE_DST}/${cfgdir}/"
    fi
done

# Backup ~/.agents directory
echo "> Backing up ~/.agents..."
if [[ -d "${HOME_DIR}/.agents" ]]; then
    mkdir -p "${ICLOUD_DIR}/dot.agents"
    cp -R "${HOME_DIR}/.agents/." "${ICLOUD_DIR}/dot.agents/"
else
    echo "  Warning: ~/.agents not found, skipping"
fi

# Save Homebrew packages list
echo "> Saving Installed Homebrew packages..."
if command -v brew &>/dev/null; then
    brew leaves -r > "${ICLOUD_DIR}/brew-formulas.txt" 2>/dev/null || true
    brew list --cask > "${ICLOUD_DIR}/brew-casks.txt" 2>/dev/null || true
else
    echo "  Warning: Homebrew not found, skipping"
fi

# Save Volta packages list
echo "> Saving Installed Volta packages..."
if command -v volta &>/dev/null; then
    volta list all > "${ICLOUD_DIR}/volta-packages.txt" 2>/dev/null || true
else
    echo "  Warning: Volta not found, skipping"
fi

# Save Cargo installed packages list
echo "> Saving Installed Cargo packages..."
if command -v cargo &>/dev/null; then
    cargo install --list 2>/dev/null | grep -E '^\S' | sed 's/:$//' > "${ICLOUD_DIR}/cargo-packages.txt" || true
else
    echo "  Warning: Cargo not found, skipping"
fi

# Save list of installed macOS applications
echo "> Saving installed macOS applications..."
system_profiler SPApplicationsDataType -json 2>/dev/null \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
skip_prefixes = ('/System/', '/Library/Apple/')
for app in sorted(data.get('SPApplicationsDataType', []), key=lambda a: a.get('_name', '').lower()):
    path = app.get('path', '')
    if app.get('obtained_from', '') == 'apple' and any(path.startswith(p) for p in skip_prefixes):
        continue
    name = app.get('_name', '')
    version = app.get('version', 'n/a')
    print(f'{name}\t{version}\t{path}')
" > "${ICLOUD_DIR}/macos-apps.txt" 2>/dev/null || true

echo "Backup complete: ${ICLOUD_DIR#$ICLOUD_BASE/}"

