import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tomlkit

from herdr_modus import Manager, THEMES, omarchy_variant, palette, main


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.environment = patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_STATE_HOME": str(self.root / "state"),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.config = self.root / "config/herdr/config.toml"
        self.config.parent.mkdir(parents=True)
        self.original = '''# My configuration
onboarding = false
[theme]
name = "nord"
[theme.custom]
accent = "#abcdef"
[keys]
prefix = "ctrl+space" # keep this comment
[ui]
accent = "blue"
[ui.sidebar.agents]
rows = [["workspace"], [{token="agent", dim=false}]]
'''
        self.config.write_text(self.original)
        self.manager = Manager(self.config)

    def test_repeated_switches_preserve_settings_and_restore_original_theme(self):
        original = tomlkit.parse(self.original).unwrap()
        for name in [THEMES[0], THEMES[1], THEMES[0], THEMES[0]]:
            self.manager.apply(name)
            actual = tomlkit.parse(self.config.read_text()).unwrap()
            self.assertEqual(actual["theme"]["custom"], palette(name)["theme"]["custom"].unwrap())
            self.assertEqual({k:v for k,v in actual.items() if k != "theme"},
                             {k:v for k,v in original.items() if k != "theme"})
            self.assertIn('# keep this comment', self.config.read_text())
        self.manager.restore()
        self.assertEqual(tomlkit.parse(self.config.read_text()).unwrap(), original)
        self.assertEqual(len(list(self.config.parent.glob("config.toml.before-modus.*"))), 1)

    def test_restore_keeps_later_non_theme_changes(self):
        self.manager.apply(THEMES[0])
        self.config.write_text(self.config.read_text().replace('prefix = "ctrl+space"', 'prefix = "ctrl+a"'))
        self.manager.restore()
        self.assertEqual(tomlkit.parse(self.config.read_text())["keys"]["prefix"], "ctrl+a")

    def test_manual_theme_changes_are_not_overwritten(self):
        self.manager.apply(THEMES[0])
        self.config.write_text(self.config.read_text().replace('#ffffff', '#eeeeee'))
        changed = self.config.read_text()
        with self.assertRaises(ValueError):
            self.manager.apply(THEMES[1])
        with self.assertRaises(ValueError):
            self.manager.restore()
        self.assertEqual(self.config.read_text(), changed)

    def test_symlink_and_file_mode_survive(self):
        target = self.root / "dotfiles.toml"
        self.config.rename(target)
        target.chmod(0o640)
        self.config.symlink_to(target)
        self.manager.apply(THEMES[0])
        self.manager.restore()
        self.assertTrue(self.config.is_symlink())
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_missing_config_can_be_restored(self):
        self.config.unlink()
        self.manager.apply(THEMES[0])
        self.manager.restore()
        self.assertEqual(tomlkit.parse(self.config.read_text()).unwrap(), {})

    def test_invalid_toml_does_not_create_state_or_modify_config(self):
        self.config.write_text('[theme\n')
        with self.assertRaises(tomlkit.exceptions.TOMLKitError):
            self.manager.apply(THEMES[0])
        self.assertFalse(self.manager.state_path.exists())
        self.assertEqual(self.config.read_text(), '[theme\n')

    def test_interrupted_apply_recovers_using_pending_theme(self):
        self.manager.apply(THEMES[0])
        state = self.manager.read_state()
        state['pending'] = state['applied']
        state['applied'] = None
        self.manager.save_state(state)
        self.manager.apply(THEMES[1])
        self.manager.restore()
        self.assertEqual(tomlkit.parse(self.config.read_text()).unwrap(), tomlkit.parse(self.original).unwrap())

    def active_omarchy_theme(self, name):
        theme = self.root / "state/omarchy/current/theme"
        theme.mkdir(parents=True, exist_ok=True)
        (theme.parent / "theme.name").write_text(name + "\n")
        return theme

    def test_omarchy_only_matches_exact_modus_names(self):
        for name, expected in [(THEMES[0], THEMES[0]), (THEMES[1], THEMES[1]),
                               ("catppuccin", None), ("modus-operandi-custom", None),
                               ("modus-vivendi-tinted", None)]:
            theme = self.active_omarchy_theme(name)
            # Names are authoritative even if palette metadata is contradictory.
            (theme / "colors.toml").write_text('mode = "dark"\n')
            (theme / "light.mode").touch()
            self.assertEqual(omarchy_variant(), expected)

    def test_modus_other_modus_cycle_restores_and_keeps_hook(self):
        self.active_omarchy_theme(THEMES[0])
        self.manager.install_hook()
        hook = Path(self.manager.read_state()["hook"])
        self.active_omarchy_theme("catppuccin")
        self.assertTrue(self.manager.apply(None))
        self.assertEqual(tomlkit.parse(self.config.read_text()).unwrap(),
                         tomlkit.parse(self.original).unwrap())
        self.assertTrue(hook.exists())
        self.assertIsNone(self.manager.read_state()["variant"])
        before = self.config.read_bytes()
        stamp = self.config.stat().st_mtime_ns
        self.active_omarchy_theme("gruvbox-light")
        self.assertFalse(self.manager.apply(None))
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(self.config.stat().st_mtime_ns, stamp)
        self.active_omarchy_theme(THEMES[1])
        self.assertTrue(self.manager.apply(None))
        self.assertEqual(self.manager.read_state()["variant"], THEMES[1])
        self.active_omarchy_theme(THEMES[0])
        self.assertTrue(self.manager.apply(None))
        self.assertEqual(self.manager.read_state()["variant"], THEMES[0])
        self.manager.restore()
        self.assertFalse(hook.exists())
        self.assertEqual(tomlkit.parse(self.config.read_text()).unwrap(),
                         tomlkit.parse(self.original).unwrap())

    def test_install_and_uninstall_on_other_theme_do_not_touch_config(self):
        self.active_omarchy_theme("catppuccin")
        stamp = self.config.stat().st_mtime_ns
        self.assertFalse(self.manager.install_hook())
        self.assertEqual(self.config.read_text(), self.original)
        self.assertEqual(self.config.stat().st_mtime_ns, stamp)
        self.assertFalse(list(self.config.parent.glob("config.toml.before-modus.*")))
        self.assertFalse(self.manager.restore())
        self.assertEqual(self.config.read_text(), self.original)
        self.assertEqual(self.config.stat().st_mtime_ns, stamp)

    def test_idle_theme_edits_become_next_restore_baseline(self):
        self.active_omarchy_theme(THEMES[0])
        self.manager.install_hook()
        self.active_omarchy_theme("catppuccin")
        self.manager.apply(None)
        edited = self.config.read_text().replace('name = "nord"', 'name = "dracula"')
        self.config.write_text(edited)
        self.assertFalse(self.manager.apply(None))
        self.active_omarchy_theme(THEMES[1])
        self.manager.apply(None)
        self.active_omarchy_theme("gruvbox")
        self.manager.apply(None)
        self.assertEqual(tomlkit.parse(self.config.read_text()).unwrap(),
                         tomlkit.parse(edited).unwrap())
        self.manager.restore()
        self.assertEqual(tomlkit.parse(self.config.read_text()).unwrap(),
                         tomlkit.parse(edited).unwrap())

    def test_other_theme_without_config_leaves_it_absent(self):
        self.config.unlink()
        self.active_omarchy_theme("nord")
        self.manager.install_hook()
        self.assertFalse(self.config.exists())
        self.manager.restore()
        self.assertFalse(self.config.exists())

    def test_sync_noop_does_not_reload_server(self):
        self.active_omarchy_theme("nord")
        self.manager.install_hook()
        with patch.object(sys, "argv", ["herdr-modus", "--config", str(self.config), "sync-omarchy"]):
            with patch("herdr_modus.reload_herdr") as reload:
                main()
                reload.assert_not_called()

    def test_active_theme_edits_are_preserved_when_leaving_modus(self):
        self.active_omarchy_theme(THEMES[0])
        self.manager.install_hook()
        edited = self.config.read_text().replace('#ffffff', '#eeeeee')
        self.config.write_text(edited)
        self.active_omarchy_theme("catppuccin")
        with self.assertRaises(ValueError):
            self.manager.apply(None)
        self.assertEqual(self.config.read_text(), edited)

    def test_missing_theme_name_does_not_guess_from_light_marker(self):
        theme = self.active_omarchy_theme(THEMES[0])
        (theme / "light.mode").touch()
        (theme.parent / "theme.name").unlink()
        with self.assertRaises(ValueError):
            self.manager.install_hook()
        self.assertEqual(self.config.read_text(), self.original)

    def test_unrelated_hook_is_preserved_before_config_changes(self):
        self.active_omarchy_theme(THEMES[0])
        hook = self.root / "config/omarchy/hooks/theme-set.d/80-herdr-modus"
        hook.parent.mkdir(parents=True)
        hook.write_text("echo custom\n")
        with self.assertRaises(ValueError):
            self.manager.install_hook()
        self.assertEqual(self.config.read_text(), self.original)
        self.assertEqual(hook.read_text(), "echo custom\n")


def luminance(color):
    channels = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    return sum(v*w for v,w in zip(channels, (.2126, .7152, .0722)))


def contrast(a, b):
    a, b = sorted((luminance(a), luminance(b)))
    return (b + .05) / (a + .05)


class PaletteTests(unittest.TestCase):
    def test_text_and_active_tab_contrast(self):
        for name in THEMES:
            p = palette(name)["theme"]["custom"]
            for fg in ("text", "overlay0", "overlay1", "subtext0"):
                for bg in ("panel_bg", "sidebar_bg", "active_row_bg", "selection_bg", "surface0", "surface1"):
                    with self.subTest(theme=name, fg=fg, bg=bg):
                        self.assertGreaterEqual(contrast(p[fg], p[bg]), 7)
            self.assertGreaterEqual(contrast(p["panel_bg"], p["accent"]), 7)
            self.assertNotEqual(p["active_row_bg"], p["selection_bg"])


if __name__ == '__main__':
    unittest.main()
