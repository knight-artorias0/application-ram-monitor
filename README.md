# Application RAM Monitor (appmon)

Terminal monitor for **Arch Linux** (and other systemd + cgroup v2 systems) that aggregates RAM and CPU usage **per application** instead of per process.

Like `htop` or `btop`, but Firefox's main process, GPU process, and content processes show up as a single **Firefox** row.

## Features

- Aggregates **PSS memory** and **CPU %** across all processes in an application
- Groups desktop apps via **systemd cgroup app IDs** (`app.slice`)
- Supports **Flatpak** and **Snap** scope naming
- Falls back to executable name for CLI tools and terminals
- Interactive TUI with search, sort, and per-process drill-down

## Requirements

- Linux with `/proc` (tested on Arch Linux)
- Python 3.11+
- systemd user session with cgroup v2 (default on modern Arch)

## Install

| Method | Command | Best for |
|--------|---------|----------|
| **AUR** | `yay -S appmon` | Arch users — system-wide install |
| **pipx** | `pipx install git+https://github.com/YOUR_USER/application-ram-monitor.git` | Quick try without AUR |
| **Clone** | `git clone ... && ./scripts/install.sh` | Development / hacking |

### AUR (recommended)

Once published to the AUR:

```bash
yay -S appmon
appmon
```

### Clone and install

```bash
git clone https://github.com/YOUR_USER/application-ram-monitor.git
cd application-ram-monitor
./scripts/install.sh
appmon
```

Manual install:

```bash
pip install -e .          # editable dev install
# or
pipx install .            # isolated user install
```

Arch dependencies for a manual install:

```bash
sudo pacman -S python python-pip python-textual
```

## Usage

```bash
appmon                  # launch TUI (1s refresh)
appmon --interval 2     # slower refresh
python -m appmon        # same as appmon
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

The AUR package files live in [`packaging/aur/`](packaging/aur/).

1. Tag a release: `git tag v0.1.0 && git push --tags`
2. Update `pkgver` in `packaging/aur/PKGBUILD`
3. Generate metadata:

   ```bash
   cd packaging/aur
   makepkg --printsrcinfo > .SRCINFO
   ```

4. Push `PKGBUILD` and `.SRCINFO` to your AUR repo (`aur/appmon`)

## Development

```bash
pip install -e ".[dev]"
pytest
python -m appmon
```

## License

MIT — see [LICENSE](LICENSE).
