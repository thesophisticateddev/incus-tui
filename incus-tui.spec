# PyInstaller build configuration for incus-tui.
#
# NOTE: On Python 3.12 + some Linux distros, single-file (onefile) PyInstaller
# binaries fail to start with "Failed to start embedded python interpreter"
# (encodings stdlib module cannot be loaded early enough).  The onedir build
# works reliably everywhere.
#
# Build locally (requires pip install pyinstaller):
#   pyinstaller --onedir --name incus-tui \
#     --hidden-import=encodings \
#     --hidden-import=encodings.ascii \
#     --hidden-import=encodings.utf_8 \
#     --hidden-import=pyte \
#     --hidden-import=pyte.modes \
#     --hidden-import=pyte.screens \
#     --hidden-import=pyte.streams \
#     --hidden-import=incus_tui \
#     --hidden-import=incus_tui.__about__ \
#     --hidden-import=incus_tui.__main__ \
#     --hidden-import=incus_tui.app \
#     --hidden-import=incus_tui.components \
#     --hidden-import=incus_tui.components.access \
#     --hidden-import=incus_tui.components.containers \
#     --hidden-import=incus_tui.components.create \
#     --hidden-import=incus_tui.components.explorer \
#     --hidden-import=incus_tui.components.incus \
#     --hidden-import=incus_tui.components.terminal \
#     --hidden-import=incus_tui.components.welcome \
#     --collect-all=textual \
#     --collect-data=pyfiglet \
#     incus_tui/__main__.py
#
# Output: dist/incus-tui/  (a folder, not a single file)
#
# Artifacts to attach to the GitHub Release:
#   Linux:   dist/incus-tui/  →  incus-tui-<ver>-linux-x86_64.tar.gz
#   macOS:   dist/incus-tui/  →  incus-tui-<ver>-macos-arm64.tar.gz
#   macOS:   dist/incus-tui/  →  incus-tui-<ver>-macos-x86_64.tar.gz
#   Windows: dist/incus-tui/  →  incus-tui-<ver>-windows-x86_64.zip
#
# Smoke test: dist/incus-tui/incus-tui --version
