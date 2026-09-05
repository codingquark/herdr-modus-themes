# Modus themes for Herdr

**Modus Operandi** (light) and **Modus Vivendi** (dark), adapted for
[Herdr](https://herdr.dev/) from [Protesilaos Stavrou's Modus themes](https://protesilaos.com/emacs/modus-themes).

The palettes give Herdr explicit reading surfaces, secondary text, active rows,
navigation selections, status colours, and tab accents. They work with stock
Herdr through `[theme.custom]`: no Herdr fork, compilation, or Omarchy theme
package is needed.

## Install

Requires Linux or macOS, Python 3.11+ with `venv`/`pip`, Git, and Herdr 0.8.2+.
Installation downloads the small Python dependency `tomlkit` and build tools
into a private virtual environment. It does not require root.

```sh
git clone https://github.com/codingquark/herdr-modus-themes.git
cd herdr-modus-themes
sh install.sh modus-operandi
```

Or choose `modus-vivendi`. Running `sh install.sh` without an argument installs
the command without applying a theme. Ensure `~/.local/bin` is on your `PATH`.

Switch at any time:

```sh
herdr-modus apply modus-operandi
herdr-modus apply modus-vivendi
```

The installer copies the package into `~/.local/share/herdr-modus-themes/venv`
and installs `~/.local/bin/herdr-modus`. Moving the checkout does not break it.
Pull updates and rerun the installer to update.

## Follow Modus themes in Omarchy

```sh
sh install.sh --omarchy
```

For an existing installation:

```sh
herdr-modus follow-omarchy
```

This installs one local `theme-set` hook that reads Omarchy's active `theme.name`:

- `modus-operandi` applies the Operandi palette in Herdr.
- `modus-vivendi` applies the Vivendi palette in Herdr.
- Any other desktop theme restores the Herdr theme that was active before Modus.

After restoring, the hook remains installed but leaves Herdr's config untouched
until one of those two exact Modus names is selected again. Installing the hook
while another desktop theme is active does not change Herdr's configuration.
Custom names and tinted variants are not matched. This does not change terminal
ANSI colours or require changes to `omarchy-modus-themes`.

Herdr 0.8.2 supports a single custom palette; its built-in `auto_switch` setting
cannot select external palette files. The hook applies or restores the palette
and reloads Herdr only when its configuration changes. Manual `apply` commands
still work independently of the desktop theme; the next Omarchy switch resumes
the rules above.

## Configuration and restore

The command replaces only Herdr's `[theme]` configuration. Existing keys, pane
settings, sidebar layouts, and comments outside that table are preserved. Before
the first change it saves a full `config.toml.before-modus.*` backup and records
the original theme in `config.toml.modus-state.json` beside the config.

```sh
herdr-modus status
herdr-modus restore
```

`restore` reinstates the original theme, preserves subsequent unrelated config
edits, and removes this package's Omarchy hook. It leaves the backup for recovery.
Herdr theme edits made while a non-Modus desktop theme is active are preserved
and become the restore baseline the next time you enter Modus.
If you edit the managed `[theme]` while Modus is active, switching and restoration stop rather
than silently overwrite those edits. Save your edited theme separately and put
back the last applied palette before using `restore`, or merge your desired
theme manually using the backup.

The default config respects `HERDR_CONFIG_PATH` and `XDG_CONFIG_HOME`. An explicit
path and offline operation are also supported:

```sh
herdr-modus --config /path/to/config.toml --no-reload apply modus-operandi
```

Reload targets the local server associated with that config, clearing inherited
socket overrides. Named or remote sessions may need their own config and reload.
If Herdr is not running, the saved palette takes effect on its next start.

To uninstall, run `herdr-modus restore`, then remove `~/.local/bin/herdr-modus`
and `~/.local/share/herdr-modus-themes`. With a custom `XDG_DATA_HOME`, remove
`$XDG_DATA_HOME/herdr-modus-themes` instead. The checkout can be kept or removed.

## Design and limits

Operandi uses a white canvas, black primary text, dark secondary text, pale active
rows, and blue accents. Vivendi uses a black canvas, white primary text, light
secondary text, dark active rows, and bright blue accents. Selection has its own
surface in both variants.

Tests check primary and secondary text against each authored reading surface at
7:1 or better, as well as text on the active tab accent. These are palette-pair
measurements, not a claim that every rendered Herdr state passes WCAG AAA.
Herdr can apply `dim` to some labels and status icons, reducing their displayed
contrast. Applications inside panes retain their own colours and styles.

For example, Herdr's default agent detail line is dimmed. If you want full-strength
text there, adapt your existing sidebar layout using Herdr's supported token style:

```toml
[ui.sidebar.agents]
rows = [["state_icon", "workspace", "tab"], [{ token = "agent", dim = false }]]
```

This is optional; the installer does not replace your sidebar layout.

## Development

The authored palettes are in `src/herdr_modus/palettes/`. No generation step is
required. Run the config-preservation, switching, restore, and contrast checks:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

## Credits and licence

Original Modus themes and palette design: **Protesilaos Stavrou**.
The colour reference is Modus Themes 5.2.0's non-tinted Operandi and Vivendi
palettes. This port assigns those colours to Herdr's UI roles and adapts secondary
text for highlighted surfaces. It is an independent adaptation, not an official
Modus or Herdr project.

Modus Themes: copyright 2019–2026 Free Software Foundation, Inc.
Herdr adaptation and installation tools: copyright 2026 Dhavan Vaidya.
Distributed under GPL-3.0-or-later; see [LICENSE](LICENSE).

References: [Modus colour palettes](https://protesilaos.com/emacs/modus-themes-colors),
[Herdr configuration](https://herdr.dev/docs/configuration/#theme).
