#!/usr/bin/env bash
# Build .deb and .rpm packages using fpm.
# Requires: fpm (gem install fpm)
# Usage: ./make-linux-packages.sh <version> <input-dir>
# Example: ./make-linux-packages.sh 0.1.0 dist/incus-tui

set -euo pipefail

VERSION="${1:?Usage: $0 <version> <input-dir>}"
INPUT_DIR="${2:?Usage: $0 <version> <input-dir>}"
OUTPUT_DIR="${OUTPUT_DIR:-.}"

# Runtime dependencies (declared in package metadata; not bundled).
DEB_DEPS="incus, openssh-client, sshfs"
RPM_DEPS="incus, openssh-client, sshfs"

echo "=== Building .deb ==="
fpm -s dir -t deb \
  -n incus-tui \
  -v "${VERSION}" \
  -d "${DEB_DEPS}" \
  -p "${OUTPUT_DIR}/incus-tui-${VERSION}-linux-x86_64.deb" \
  -f "${INPUT_DIR}/"

echo "=== Building .rpm ==="
fpm -s dir -t rpm \
  -n incus-tui \
  -v "${VERSION}" \
  -d "${RPM_DEPS}" \
  -p "${OUTPUT_DIR}/incus-tui-${VERSION}-linux-x86_64.rpm" \
  -f "${INPUT_DIR}/"

echo "=== Done. Output in ${OUTPUT_DIR}/ ==="
ls -lh "${OUTPUT_DIR}/incus-tui-${VERSION}"-linux-x86_64.{deb,rpm}
