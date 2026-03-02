"""macOS configuration backup tool."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TextIO


# ------------------------------------------------------------------- Colors
class Color:
    BOLD_BLUE = "\033[1;34m"
    BOLD_GREEN = "\033[1;32m"
    BOLD_YELLOW = "\033[1;33m"
    BOLD_RED = "\033[1;31m"
    DIM = "\033[2m"
    RESET = "\033[0m"


# ------------------------------------------------------------------- Status
class Status(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SectionResult:
    id: str
    label: str
    status: Status
    elapsed: float


# ------------------------------------------------------------------- Config
GPG_RECIPIENT = "i3oc9i@icloud.com"
HOME = Path.home()
ICLOUD_BASE = HOME / "Library/Mobile Documents/com~apple~CloudDocs/My"

DOTFILES = [
    ".direnvrc", ".fdignore", ".rgignore",
    ".gitconfig", ".zsh_history", ".zsh_aliases", ".zshrc",
]
ENCRYPTED_DOTFILES = {".zsh_history"}

# Set in main() before sections run
BACKUP_DIR: Path = Path()
ENCRYPT: bool = True


# ------------------------------------------------------------------- Helpers
def format_duration(secs: float) -> str:
    s = int(secs)
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m{s % 60}s"


def require_cmd(cmd: str, label: str) -> bool:
    if shutil.which(cmd) is None:
        print(f"{Color.BOLD_RED}  \u2717 '{cmd}' not found \u2014 skipping {label}{Color.RESET}")
        return False
    return True


def confirm(label: str, run_all: bool) -> bool:
    if run_all:
        return True
    try:
        response = input(f"{Color.BOLD_YELLOW}==> Back up {label}? (y/N): {Color.RESET}")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return response.strip().lower() in ("y", "yes")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)


def encrypt_to_dest(src: Path, dest_dir: Path) -> None:
    """Encrypt file in /tmp then move to dest (unencrypted data never touches iCloud)."""
    if ENCRYPT:
        tmp = Path("/tmp") / src.name
        if src != tmp:
            shutil.copy2(src, tmp)
        run(
            ["gpg", "--encrypt", "--recipient", GPG_RECIPIENT, "--batch", "--yes", str(tmp)],
            check=True,
        )
        shutil.move(f"{tmp}.gpg", dest_dir / f"{src.name}.gpg")
        tmp.unlink(missing_ok=True)
    else:
        shutil.copy2(src, dest_dir / src.name)


def tar_encrypt(name: str, base: Path, includes: list[str], dest: Path, *, excludes: list[str] | None = None) -> None:
    """Create tarball under base dir, then encrypt and move to dest."""
    tmp_tar = Path("/tmp") / f"{name}.tgz"
    cmd = ["/usr/bin/tar", "-C", str(base), "-czf", str(tmp_tar)]
    for exc in excludes or []:
        cmd.extend(["--exclude", exc])
    cmd.extend(includes)
    run(cmd, check=True)
    encrypt_to_dest(tmp_tar, dest)
    tmp_tar.unlink(missing_ok=True)


# ------------------------------------------------------------------- Sections
def do_local_bin() -> bool:
    src = HOME / ".local/bin"
    if not src.is_dir():
        print(f"  {Color.DIM}~/.local/bin not found, skipping{Color.RESET}")
        return True
    dest = BACKUP_DIR / "dot.localbin"
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in sorted(src.iterdir()):
        if f.suffix in (".sh", ".py") and f.is_file():
            shutil.copy2(f, dest / f.name)
            count += 1
    print(f"  Copied {count} scripts")
    return True


def do_ssh() -> bool:
    if not (HOME / ".ssh").is_dir():
        print(f"  {Color.DIM}~/.ssh not found, skipping{Color.RESET}")
        return True
    tar_encrypt("dir.ssh", HOME, [".ssh"], BACKUP_DIR, excludes=["*.sock", "agent.*"])
    return True


def do_my() -> bool:
    if not (HOME / ".my").is_dir():
        print(f"  {Color.DIM}~/.my not found, skipping{Color.RESET}")
        return True
    tar_encrypt("dir.my", HOME, [".my"], BACKUP_DIR)
    return True


def do_config() -> bool:
    if not (HOME / ".config").is_dir():
        print(f"  {Color.DIM}~/.config not found, skipping{Color.RESET}")
        return True
    tar_encrypt("dir.config", HOME, [".config"], BACKUP_DIR)
    return True


def do_gpg_keys() -> bool:
    if not require_cmd("gpg", "GPG Keys"):
        return False
    result = run(["gpg", "--list-secret-keys"], capture_output=True)
    if result.returncode != 0:
        print(f"  {Color.DIM}No GPG secret keys found, skipping{Color.RESET}")
        return True
    dest = BACKUP_DIR / "dot.gnupg"
    dest.mkdir(parents=True, exist_ok=True)
    for cmd_args, fname in [
        (["--export", "--armor"], "public-keys.asc"),
        (["--export-secret-keys", "--armor"], "secret-keys.asc"),
        (["--export-ownertrust"], "ownertrust.txt"),
    ]:
        r = run(["gpg", *cmd_args], capture_output=True, text=True, check=True)
        (dest / fname).write_text(r.stdout)
    return True


def do_dotfiles() -> bool:
    for dotfile in DOTFILES:
        src = HOME / dotfile
        if not src.is_file():
            print(f"  {Color.DIM}{dotfile} not found, skipping{Color.RESET}")
            continue
        destname = f"dot.{dotfile.lstrip('.')}"
        if dotfile in ENCRYPTED_DOTFILES:
            tmp = Path("/tmp") / destname
            shutil.copy2(src, tmp)
            encrypt_to_dest(tmp, BACKUP_DIR)
            tmp.unlink(missing_ok=True)
        else:
            shutil.copy2(src, BACKUP_DIR / destname)
    return True


def do_claude() -> bool:
    src = HOME / ".claude"
    if not src.is_dir():
        print(f"  {Color.DIM}~/.claude not found, skipping{Color.RESET}")
        return True
    dest = BACKUP_DIR / "dot.claude"
    dest.mkdir(parents=True, exist_ok=True)

    # ~/.claude.json (lives in ~ not ~/.claude)
    claude_json = HOME / ".claude.json"
    if claude_json.is_file():
        shutil.copy2(claude_json, dest / "dot.claude.json")
    else:
        print(f"  {Color.DIM}~/.claude.json not found, skipping{Color.RESET}")

    # Config files inside ~/.claude/
    for cfg in ("CLAUDE.md", "settings.json", "keybindings.json"):
        p = src / cfg
        if p.is_file():
            shutil.copy2(p, dest / cfg)
        else:
            print(f"  {Color.DIM}~/.claude/{cfg} not found, skipping{Color.RESET}")

    # Plugin config files
    for pcfg in ("installed_plugins.json", "blocklist.json", "known_marketplaces.json"):
        p = src / "plugins" / pcfg
        if p.is_file():
            (dest / "plugins").mkdir(exist_ok=True)
            shutil.copy2(p, dest / "plugins" / pcfg)
        else:
            print(f"  {Color.DIM}~/.claude/plugins/{pcfg} not found, skipping{Color.RESET}")

    # Skills directory (copy regular files, record symlinks for restore)
    skills_src = src / "skills"
    if skills_src.is_dir():
        skills_dest = dest / "skills"
        skills_dest.mkdir(exist_ok=True)
        symlinks: list[str] = []
        for item in sorted(skills_src.iterdir()):
            if item.is_symlink():
                symlinks.append(f'ln -s "{os.readlink(item)}" "{item.name}"')
            elif item.is_dir():
                shutil.copytree(item, skills_dest / item.name, dirs_exist_ok=True)
            else:
                shutil.copy2(item, skills_dest / item.name)
        if symlinks:
            (skills_dest / "SYMLINKS.sh").write_text("\n".join(symlinks) + "\n")
    else:
        print(f"  {Color.DIM}~/.claude/skills not found, skipping{Color.RESET}")

    # Optional config directories
    for cfgdir in ("rules", "commands", "agents", "agent-memory"):
        cfgdir_src = src / cfgdir
        if cfgdir_src.is_dir():
            shutil.copytree(cfgdir_src, dest / cfgdir, dirs_exist_ok=True)

    return True


def do_agents() -> bool:
    src = HOME / ".agents"
    if not src.is_dir():
        print(f"  {Color.DIM}~/.agents not found, skipping{Color.RESET}")
        return True
    dest = BACKUP_DIR / "dot.agents"
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return True


def do_brew() -> bool:
    if not require_cmd("brew", "Homebrew"):
        return False
    formulas = run(["brew", "leaves", "-r"], capture_output=True, text=True)
    (BACKUP_DIR / "brew-formulas.txt").write_text(formulas.stdout)
    casks = run(["brew", "list", "--cask"], capture_output=True, text=True)
    (BACKUP_DIR / "brew-casks.txt").write_text(casks.stdout)
    return True


def do_volta() -> bool:
    if not require_cmd("volta", "Volta"):
        return False
    result = run(["volta", "list", "all"], capture_output=True, text=True)
    (BACKUP_DIR / "volta-packages.txt").write_text(result.stdout)
    return True


def do_cargo() -> bool:
    if not require_cmd("cargo", "Cargo"):
        return False
    result = run(["cargo", "install", "--list"], capture_output=True, text=True)
    lines = [re.sub(r":$", "", line) for line in result.stdout.splitlines() if line and not line[0].isspace()]
    (BACKUP_DIR / "cargo-packages.txt").write_text("\n".join(lines) + "\n" if lines else "")
    return True


def do_macos_apps() -> bool:
    result = run(
        ["system_profiler", "SPApplicationsDataType", "-json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  {Color.BOLD_RED}system_profiler failed{Color.RESET}")
        return False
    data = json.loads(result.stdout)
    skip_prefixes = ("/System/", "/Library/Apple/")
    lines: list[str] = []
    for app in sorted(data.get("SPApplicationsDataType", []), key=lambda a: a.get("_name", "").lower()):
        path = app.get("path", "")
        if app.get("obtained_from") == "apple" and any(path.startswith(p) for p in skip_prefixes):
            continue
        name = app.get("_name", "")
        version = app.get("version", "n/a")
        lines.append(f"{name}\t{version}\t{path}")
    (BACKUP_DIR / "macos-apps.txt").write_text("\n".join(lines) + "\n" if lines else "")
    return True


# ------------------------------------------------------------------- Section Registry
SECTIONS: list[tuple[str, str, Callable[[], bool]]] = [
    ("local-bin", "Local Scripts (~/.local/bin)", do_local_bin),
    ("ssh", "SSH (~/.ssh)", do_ssh),
    ("my", "Private Dir (~/.my)", do_my),
    ("config", "Config Dir (~/.config)", do_config),
    ("gpg-keys", "GPG Keys", do_gpg_keys),
    ("dotfiles", "Dotfiles", do_dotfiles),
    ("claude", "Claude Code (~/.claude)", do_claude),
    ("agents", "Agents (~/.agents)", do_agents),
    ("brew", "Homebrew Packages", do_brew),
    ("volta", "Volta Packages", do_volta),
    ("cargo", "Cargo Packages", do_cargo),
    ("macos-apps", "macOS Applications", do_macos_apps),
]

SECTION_ALIASES = {
    "packages": ["brew", "volta", "cargo", "macos-apps"],
    "encrypted": ["ssh", "my", "config"],
}

SECTION_IDS = [s[0] for s in SECTIONS]


# ------------------------------------------------------------------- Dispatcher
def run_section(
    id: str, label: str, fn: Callable[[], bool], *, run_all: bool, only: list[str],
) -> SectionResult:
    # Section filter
    if only and id not in only:
        return SectionResult(id, label, Status.SKIPPED, 0.0)

    # Confirm (skip prompt if sections were explicitly requested)
    if not only and not confirm(label, run_all):
        return SectionResult(id, label, Status.SKIPPED, 0.0)

    # Execute
    print(f"\n{Color.BOLD_GREEN}Backing up {label}...{Color.RESET}")
    start = time.monotonic()
    try:
        success = fn()
    except subprocess.CalledProcessError:
        success = False
    except Exception as exc:
        print(f"{Color.BOLD_RED}  Error: {exc}{Color.RESET}")
        success = False
    elapsed = time.monotonic() - start

    status = Status.SUCCESS if success else Status.FAILED
    return SectionResult(id, label, status, elapsed)


# ------------------------------------------------------------------- Summary
def print_summary(results: list[SectionResult]) -> None:
    print(f"\n{Color.BOLD_BLUE}--- Summary ---{Color.RESET}")
    print(f"  {'Section':<30} {'Status':<10} {'Time'}")
    print(f"  {'\u2500' * 27:<30} {'\u2500' * 8:<10} {'\u2500' * 5}")
    for r in results:
        match r.status:
            case Status.SUCCESS:
                color = Color.BOLD_GREEN
            case Status.FAILED:
                color = Color.BOLD_RED
            case _:
                color = Color.DIM
        print(f"  {r.label:<30} {color}{r.status.value:<10}{Color.RESET} {format_duration(r.elapsed)}")

    print(f"\n{Color.BOLD_BLUE}--- Backup Complete! ---{Color.RESET}")


# ------------------------------------------------------------------- Logging
class TeeWriter:
    """Wraps stdout to also write ANSI-stripped text to a log file."""

    _ansi_re = re.compile(r"\x1b\[[0-9;]*m")

    def __init__(self, original: TextIO, log_file: TextIO) -> None:
        self._original = original
        self._log_file = log_file

    def write(self, text: str) -> int:
        self._original.write(text)
        stripped = self._ansi_re.sub("", text)
        self._log_file.write(stripped)
        self._log_file.flush()
        return len(text)

    def flush(self) -> None:
        self._original.flush()
        self._log_file.flush()

    def fileno(self) -> int:
        return self._original.fileno()

    def isatty(self) -> bool:
        return self._original.isatty()


def setup_logging(path: str) -> None:
    log_fh = open(path, "a")  # noqa: SIM115
    tee = TeeWriter(sys.stdout, log_fh)
    sys.stdout = tee
    sys.stderr = TeeWriter(sys.stderr, log_fh)
    print(f"{Color.DIM}Logging to {path}{Color.RESET}")


# ------------------------------------------------------------------- CLI
def version() -> str:
    try:
        return importlib.metadata.version("save-config")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="save-config",
        description="Backs up macOS dotfiles and configuration to iCloud Drive.",
    )
    parser.add_argument("--all", action="store_true", dest="run_all", help="Run all sections without prompts")
    parser.add_argument(
        "--section", dest="sections", metavar="NAME[,NAME,...]",
        help=f"Run only named section(s), comma-separated. Names: {', '.join(SECTION_IDS)}. Aliases: {', '.join(SECTION_ALIASES)}",
    )
    parser.add_argument(
        "--no-encrypt", action="store_true",
        help="Disable GPG encryption for sensitive files",
    )
    parser.add_argument(
        "--log", nargs="?", const=True, default=None, metavar="PATH",
        help="Tee output to log file (default: ~/save-config-<timestamp>.log)",
    )
    parser.add_argument("--version", action="version", version=f"save-config v{version()}")

    args = parser.parse_args(argv)

    # Validate and expand --section (resolve aliases)
    if args.sections:
        raw = [s.strip() for s in args.sections.split(",")]
        valid_names = {*SECTION_IDS, *SECTION_ALIASES}
        invalid = [s for s in raw if s not in valid_names]
        if invalid:
            parser.error(f"invalid section(s): {', '.join(invalid)}. Choose from: {', '.join(SECTION_IDS)}, {', '.join(SECTION_ALIASES)}")
        expanded: list[str] = []
        for s in raw:
            expanded.extend(SECTION_ALIASES.get(s, [s]))
        args.sections = expanded

    # Module-level config
    global BACKUP_DIR, ENCRYPT
    ENCRYPT = not args.no_encrypt

    timestamp = time.strftime("%Y.%m.%d-%H.%M.%S")
    BACKUP_DIR = ICLOUD_BASE / f"my.Devices/Apple/Apple MacStudio/Configs/Home-{timestamp}"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Restrictive umask — all created files are owner-only
    os.umask(0o077)

    # Logging
    if args.log is not None:
        if args.log is True:
            log_path = os.path.expanduser(f"~/save-config-{time.strftime('%Y%m%d-%H%M%S')}.log")
        else:
            log_path = args.log
        setup_logging(log_path)

    # Header
    if args.run_all or args.sections:
        print(f"{Color.BOLD_BLUE}--- CONFIG BACKUP (AUTO MODE) ---{Color.RESET}")
    else:
        print(f"{Color.BOLD_BLUE}--- CONFIG BACKUP ---{Color.RESET}")
    if not ENCRYPT:
        print(f"{Color.BOLD_YELLOW}  Encryption disabled{Color.RESET}")
    print(f"{Color.DIM}  Destination: {BACKUP_DIR}{Color.RESET}")

    # Run sections
    results: list[SectionResult] = []
    for sid, label, fn in SECTIONS:
        result = run_section(
            sid, label, fn,
            run_all=args.run_all, only=args.sections or [],
        )
        results.append(result)

    # Summary
    print_summary(results)

    # Exit code
    if any(r.status == Status.FAILED for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
