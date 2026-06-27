# Application RAM Monitor (appmon)

Terminal monitor for **Arch Linux** that aggregates RAM and CPU usage **per application** instead of per process.

Like `htop` or `btop`, but Firefox's main process, GPU process, and content processes show up as a single **Firefox** row.

## Features

- Aggregates **PSS memory** and **CPU %** across all processes in an application
- Groups desktop apps via **systemd cgroup app IDs** (`app.slice`)
- Supports **Flatpak** and **Snap** scope naming
- Falls back to executable name for CLI tools and terminals
- Interactive TUI with search, sort, and per-process drill-down

## Requirements

- Arch Linux (or another systemd + cgroup v2 distro)
- Python 3.11+
- `base-devel` for building from source

## Install on Arch

### From a git clone (recommended)

```bash
sudo pacman -S --needed base-devel git \
  python python-build python-installer python-setuptools python-wheel python-textual

git clone https://github.com/knight-artorias0/application-ram-monitor.git
cd application-ram-monitor
makepkg -si
```

`makepkg -si` builds a pacman package and installs it system-wide. Uninstall later with:

```bash
sudo pacman -R appmon
```

### From the AUR (once published)

```bash
yay -S appmon
```

The AUR package files are in [`packaging/aur/`](packaging/aur/) for maintainers.

## Usage

```bash
appmon                  # launch TUI (1s refresh)
appmon --interval 2     # slower refresh
```

### Keybindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `/` | Filter applications by name |
| `s` | Cycle sort (RAM → CPU → name → process count) |
| `Enter` / arrow keys | Highlight app and show per-PID breakdown |
| `Esc` | Clear search filter |

## How grouping works

1. **cgroup app ID** — processes in `app.slice` scopes (KDE/GNOME-launched apps)
2. **Flatpak / Snap** — sandbox scope names
3. **executable name** — fallback for shells, scripts, and CLI tools

Memory uses **PSS** from `/proc/<pid>/smaps_rollup` when readable; otherwise RSS is used.

## Publishing to the AUR

1. Tag a release: `git tag v0.1.0 && git push --tags`
2. Update `pkgver` / `pkgrel` in [`packaging/aur/PKGBUILD`](packaging/aur/PKGBUILD) if needed
3. Regenerate metadata:

   ```bash
   cd packaging/aur
   makepkg --printsrcinfo > .SRCINFO
   ```

4. Push `PKGBUILD` and `.SRCINFO` to the AUR git remote (`aur/appmon`)

## Development

```bash
git clone https://github.com/knight-artorias0/application-ram-monitor.git
cd application-ram-monitor
pip install -e ".[dev]"
pytest
python -m appmon
```

For a local pacman package during development, use the root [`PKGBUILD`](PKGBUILD):

```bash
makepkg -si
```

## License

MIT — see [LICENSE](LICENSE).
