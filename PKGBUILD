# Maintainer: application-ram-monitor contributors
# Build from a local git clone: makepkg -si

pkgname=appmon
pkgver=0.3.1
pkgrel=1
pkgdesc="Terminal monitor that aggregates RAM and CPU usage per application"
arch=('any')
url="https://github.com/knight-artorias0/application-ram-monitor"
license=('MIT')
depends=('python' 'python-textual' 'python-nvidia-ml-py')
optdepends=('nvidia-utils: optional nvidia-smi fallback for GPU stats')
makedepends=('python-build' 'python-installer' 'python-setuptools' 'python-wheel')
source=()
options=(!debug)

build() {
  cd "$startdir"
  rm -rf dist build *.egg-info
  python -m build --wheel --no-isolation
}

package() {
  cd "$startdir"
  # Leftover pkg/ files from a failed makepkg run can block reinstall.
  rm -rf "$pkgdir"
  mkdir -p "$pkgdir"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
