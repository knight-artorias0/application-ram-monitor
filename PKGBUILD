# Maintainer: application-ram-monitor contributors
# Build from a local git clone: makepkg -si

pkgname=appmon
pkgver=0.3.4
pkgrel=1
pkgdesc="Terminal monitor that aggregates RAM and CPU usage per application"
arch=('any')
url="https://github.com/knight-artorias0/application-ram-monitor"
license=('MIT')
depends=('python' 'python-textual')
optdepends=('nvidia-utils: recommended NVIDIA GPU stats via nvidia-smi fallback')
makedepends=('python-build' 'python-installer' 'python-setuptools' 'python-wheel')
_nvml_py_ver=13.610.43
source=(
  "nvidia_ml_py-${_nvml_py_ver}-py3-none-any.whl::https://files.pythonhosted.org/packages/23/45/caa600acfab94560807a20a64b5830d2cd3c3202b7f1328644d70b7d6bd8/nvidia_ml_py-${_nvml_py_ver}-py3-none-any.whl"
)
sha256sums=('f13c72698edef492f985cc225f14faafe68ae065a2e407f45bdf6f4b9b43fde8')
options=(!debug)

build() {
  cd "$startdir"
  rm -rf dist build *.egg-info
  python -m build --wheel --no-isolation
  mkdir -p dist
  cp "$srcdir/nvidia_ml_py-${_nvml_py_ver}-py3-none-any.whl" dist/
}

package() {
  cd "$startdir"
  rm -rf "$pkgdir"
  mkdir -p "$pkgdir"
  python -m installer --destdir="$pkgdir" dist/appmon-*.whl
  python -m installer --destdir="$pkgdir" dist/nvidia_ml_py-*.whl
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
