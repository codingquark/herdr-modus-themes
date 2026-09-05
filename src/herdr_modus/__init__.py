"""Install Modus palettes using Herdr's public configuration format."""
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
from importlib.resources import files
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

import tomlkit

THEMES = ("modus-operandi", "modus-vivendi")
HOOK_MARKER = "# Managed by herdr-modus-themes"


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def default_config() -> Path:
    return Path(os.environ.get("HERDR_CONFIG_PATH", config_home() / "herdr/config.toml"))


def palette(name: str):
    return tomlkit.parse(files(__package__).joinpath("palettes", name + ".toml").read_text())


def atomic_write(path: Path, text: str) -> None:
    # Resolve the destination, preserving dotfile-manager symlinks.
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Manager:
    def __init__(self, config: Path):
        self.config = config.expanduser().absolute()
        self.state_path = self.config.with_name(self.config.name + ".modus-state.json")
        self.lock_path = self.state_path.with_suffix(".lock")

    @contextmanager
    def locked(self):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def read_config(self):
        return tomlkit.parse(self.config.read_text() if self.config.exists() else "")

    def read_state(self):
        if not self.state_path.exists():
            return None
        state = json.loads(self.state_path.read_text())
        if state.get("version") != 1:
            raise ValueError("Unrecognized Modus state file; leaving configuration unchanged.")
        return state

    def save_state(self, state):
        atomic_write(self.state_path, json.dumps(state, indent=2) + "\n")

    def check_owned(self, document, state):
        current = document.get("theme", {}).unwrap() if "theme" in document else None
        original = tomlkit.parse(state["original_theme"]).get("theme")
        original = original.unwrap() if original is not None else None
        if current not in (state.get("applied"), state.get("pending"), original):
            raise ValueError(
                "Herdr's [theme] was edited after applying Modus. Save those edits and "
                "restore the managed theme before switching; no changes were made."
            )

    @staticmethod
    def inactive_state():
        return {"version": 1, "original_theme": "", "backup": None,
                "applied": None, "variant": None, "hook": None}

    @staticmethod
    def is_active(state):
        return state.get("applied") is not None or state.get("pending") is not None

    def restore_theme(self, state):
        # Called with the config lock held. An idle hook must not touch settings
        # the user changes while another Omarchy theme is selected.
        if not self.is_active(state):
            return False
        document = self.read_config()
        self.check_owned(document, state)
        before = tomlkit.dumps(document)
        if "theme" in document:
            del document["theme"]
        original = tomlkit.parse(state["original_theme"])
        if "theme" in original:
            document["theme"] = original["theme"]
        after = tomlkit.dumps(document)
        if after != before:
            atomic_write(self.config, after)
        state["applied"] = None
        state.pop("pending", None)
        state["variant"] = None
        self.save_state(state)
        return after != before

    def apply(self, name: str | None):
        with self.locked():
            state = self.read_state()
            if name is None:
                name = omarchy_variant()
                if name is None:
                    return self.restore_theme(state) if state else False
            document = self.read_config()
            if state and self.is_active(state):
                self.check_owned(document, state)
            else:
                state = state or self.inactive_state()
                original = tomlkit.document()
                if "theme" in document:
                    original["theme"] = document["theme"]
                # Capture the current baseline each time we enter Modus. Users
                # may have changed their normal Herdr theme while the hook slept.
                state["original_theme"] = tomlkit.dumps(original)
                if self.config.exists() and not state["backup"]:
                    fd, backup = tempfile.mkstemp(
                        prefix=self.config.name + ".before-modus.", dir=self.config.parent
                    )
                    os.close(fd)
                    shutil.copyfile(self.config, backup)
                    state["backup"] = backup
            theme = tomlkit.table()
            theme["name"] = "terminal"
            theme["auto_switch"] = False
            theme["custom"] = palette(name)["theme"]["custom"]
            if (document.get("theme") == theme and state.get("applied") == theme.unwrap()
                    and state.get("variant") == name and "pending" not in state):
                return False
            before = tomlkit.dumps(document)
            state["pending"] = theme.unwrap()
            self.save_state(state)
            document["theme"] = theme
            after = tomlkit.dumps(document)
            if after != before:
                atomic_write(self.config, after)
            state["applied"] = state.pop("pending")
            state["variant"] = name
            self.save_state(state)
            return after != before

    def restore(self):
        with self.locked():
            state = self.read_state()
            if not state:
                return False
            hook = Path(state["hook"]) if state.get("hook") else None
            if hook and hook.exists() and HOOK_MARKER not in hook.read_text():
                raise ValueError("The installed hook has been replaced; leaving it unchanged.")
            changed = self.restore_theme(state)
            if hook:
                hook.unlink(missing_ok=True)
            self.state_path.unlink()
            return changed

    def install_hook(self):
        hook = config_home() / "omarchy/hooks/theme-set.d/80-herdr-modus"
        if hook.exists() and HOOK_MARKER not in hook.read_text():
            raise ValueError(f"Refusing to replace unrelated hook: {hook}")
        changed = self.apply(None)
        with self.locked():
            state = self.read_state() or self.inactive_state()
            # Use the installed interpreter, independent of shell PATH or checkout.
            command = shlex.join([sys.executable, "-m", "herdr_modus", "--config",
                                  str(self.config), "sync-omarchy"])
            script = "#!/bin/sh\n" + HOOK_MARKER + "\nexec " + command + "\n"
            state["hook"] = str(hook)
            self.save_state(state)
            atomic_write(hook, script)
            hook.chmod(0o755)
        return changed


def omarchy_variant() -> str | None:
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    name_file = state_home / "omarchy/current/theme.name"
    if not name_file.is_file():
        raise ValueError("No active Omarchy theme name found. Apply a palette manually instead.")
    name = name_file.read_text().strip()
    return name if name in THEMES else None


def reload_herdr(config: Path):
    binary = shutil.which("herdr")
    if not binary:
        print("Palette saved. Herdr will use it when next started.")
        return
    env = dict(os.environ, HERDR_CONFIG_PATH=str(config))
    # Avoid directing a CLI inherited from a remote/named session elsewhere.
    env.pop("HERDR_SOCKET_PATH", None)
    env.pop("HERDR_CLIENT_SOCKET_PATH", None)
    try:
        result = subprocess.run([binary, "server", "reload-config"], env=env,
                                text=True, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Palette saved; reload unavailable: {error}", file=sys.stderr)
        return
    if result.returncode:
        print("Palette saved; no server reloaded. " + result.stderr.strip(), file=sys.stderr)
    else:
        print(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=default_config())
    parser.add_argument("--no-reload", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("apply").add_argument("theme", choices=THEMES)
    commands.add_parser("follow-omarchy", help="Follow only the two Modus themes in Omarchy")
    commands.add_parser("sync-omarchy", help="Apply Modus or restore the previous Herdr theme")
    commands.add_parser("restore", help="Restore the original theme and remove the hook")
    commands.add_parser("status")
    args = parser.parse_args()
    manager = Manager(args.config)
    try:
        if args.command == "status":
            state = manager.read_state()
            print(json.dumps({"config": str(manager.config), "state": state}, indent=2))
            return
        if args.command == "apply":
            changed = manager.apply(args.theme)
        elif args.command == "follow-omarchy":
            changed = manager.install_hook()
        elif args.command == "sync-omarchy":
            if not manager.read_state():
                return  # A removed integration must not recreate itself.
            changed = manager.apply(None)
        elif args.command == "restore":
            changed = manager.restore()
        if changed and not args.no_reload:
            reload_herdr(manager.config)
    except (ValueError, OSError, tomlkit.exceptions.TOMLKitError) as error:
        parser.exit(1, f"herdr-modus: {error}\n")
