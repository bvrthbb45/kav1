#!/usr/bin/env bash
# Builds a self-contained Windows x64 zip of the server: portable CPython,
# all dependencies pre-installed, and install/run scripts. No internet or
# Python installation is needed on the target machine.
#
# Usage: server/packaging/build_offline_zip.sh [output_dir]
set -euo pipefail

PY_VERSION=3.11.9
PY_BUILD=20240814
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_BUILD}/cpython-${PY_VERSION}+${PY_BUILD}-x86_64-pc-windows-msvc-install_only.tar.gz"

SERVER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$(mkdir -p "${1:-$SERVER_DIR/dist}" && cd "${1:-$SERVER_DIR/dist}" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PKG="$WORK/WarehouseServer"
mkdir -p "$PKG"

echo "Downloading portable Python $PY_VERSION for Windows..."
curl -fsSL "$PY_URL" -o "$WORK/python.tar.gz"
tar xzf "$WORK/python.tar.gz" -C "$PKG"
# Trim debug symbols and components the server never uses.
find "$PKG/python" -name '*.pdb' -delete
rm -rf "$PKG/python/Lib/test" "$PKG/python/Lib/idlelib" "$PKG/python/Lib/tkinter" \
       "$PKG/python/Lib/turtledemo" "$PKG/python/tcl" "$PKG/python/include" \
       "$PKG/python/Lib/ensurepip" "$PKG/python/Lib/lib2to3" "$PKG/python/Lib/pydoc_data" \
       "$PKG/python/Lib/site-packages/pip" "$PKG/python/Lib/site-packages"/pip-* \
       "$PKG/python/Lib/site-packages/setuptools" "$PKG/python/Lib/site-packages"/setuptools-* \
       "$PKG/python/Lib/site-packages/_distutils_hack" "$PKG/python/Lib/site-packages/distutils-precedence.pth" \
       "$PKG/python/Lib/site-packages/pkg_resources" \
       "$PKG/python/DLLs"/_tkinter.pyd "$PKG/python/DLLs"/tcl*.dll "$PKG/python/DLLs"/tk*.dll
find "$PKG/python" -name '__pycache__' -prune -exec rm -rf {} +

echo "Installing dependencies (win_amd64 wheels)..."
python3 -m pip install --quiet --no-compile \
    --target "$PKG/python/Lib/site-packages" \
    --platform win_amd64 --python-version "${PY_VERSION%.*}" \
    --implementation cp --only-binary=:all: \
    -r "$SERVER_DIR/requirements.txt" \
    colorama  # click needs it on Windows; the marker is evaluated for the build host

echo "Bundling adb.exe (from the adbutils wheel) for wired USB sync..."
python3 -m pip download --quiet --no-deps --only-binary=:all: \
    --platform win_amd64 --python-version "${PY_VERSION%.*}" \
    -d "$WORK/adbwheel" adbutils
mkdir -p "$PKG/adb"
unzip -q -j "$WORK"/adbwheel/adbutils-*.whl 'adbutils/binaries/*.exe' 'adbutils/binaries/*.dll' -d "$PKG/adb"

echo "Copying server code and scripts..."
cp -r "$SERVER_DIR/app" "$SERVER_DIR/main.py" "$SERVER_DIR/seed.py" \
      "$SERVER_DIR/requirements.txt" "$PKG/"
find "$PKG/app" -name '__pycache__' -prune -exec rm -rf {} +
cp -r "$SERVER_DIR/packaging/windows/." "$PKG/"
mkdir -p "$PKG/logs"
# Windows batch files need CRLF line endings.
for f in "$PKG"/*.bat "$PKG"/README_HE.txt; do
    sed -i 's/\r$//; s/$/\r/' "$f"
done

ZIP="$OUT_DIR/WarehouseServer-win64-offline.zip"
rm -f "$ZIP"
(cd "$WORK" && zip -qr9 "$ZIP" WarehouseServer)
echo "Created $ZIP ($(du -h "$ZIP" | cut -f1))"
