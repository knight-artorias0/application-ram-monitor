# Maintainer: application-ram-monitor contributors
# Build from a local git clone: makepkg -si

pkgname=appmon
pkgver=0.4.0
pkgrel=1
pkgdesc="Terminal monitor that aggregates RAM and CPU usage per application"
arch=('any')
url="https://github.com/knight-artorias0/application-ram-monitor"
license=('MIT')
depends=('python' 'python-textual' 'iproute2')
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
  rm -rf "$pkgdir"
  mkdir -p "$pkgdir"
  python -m installer --destdir="$pkgdir" dist/appmon-*.whl
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
