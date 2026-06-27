# Maintainer: application-ram-monitor contributors
# Build from a local git clone: makepkg -si

pkgname=appmon
pkgver=0.3.2
pkgrel=1
pkgdesc="Terminal monitor that aggregates RAM and CPU usage per application"
arch=('any')
url="https://github.com/knight-artorias0/application-ram-monitor"
license=('MIT')
depends=('python' 'python-textual')
optdepends=('nvidia-utils: NVIDIA driver tools for GPU stats fallback')
makedepends=('python-build' 'python-installer' 'python-pip' 'python-setuptools' 'python-wheel')
source=()
options=(!debug)

build() {
  cd "$startdir"
  rm -rf dist build *.egg-info
  python -m build --wheel --no-isolation
  # Bundle the NVIDIA Python bindings inside this package (no extra pacman dep).
  python -m pip wheel nvidia-ml-py -w dist --no-deps
}

package() {
  cd "$startdir"
  rm -rf "$pkgdir"
  mkdir -p "$pkgdir"
  python -m installer --destdir="$pkgdir" dist/appmon-*.whl
  python -m installer --destdir="$pkgdir" dist/nvidia_ml_py-*.whl
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
