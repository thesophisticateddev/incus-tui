# Distribution artifacts

This directory contains configuration and scripts for distributing `incus-tui`
through native package managers.

## Homebrew (macOS / Linux)

**Tap repo:** `homebrew-tap/` — a Homebrew tap containing the `incus-tui` formula.

**One-time setup for maintainers:**
1. Create a public GitHub repo named `<owner>/<owner>.git` (e.g. `incus-tui/incus-tui`)
   to serve as the Homebrew tap.
2. Copy `homebrew-tap/` into that repo.
3. Add a `HOMEBREW_TAP_TOKEN` secret to the main repo (GitHub Settings → Secrets)
   with a GitHub PAT that has `repo` scope on the tap repo.
4. On each release, `.github/workflows/homebrew-formula.yml` automatically opens
   a PR to the tap repo with the updated version and PyPI SHA256.

**For users:**
```bash
brew tap <owner>/<owner>
brew install incus-tui
```

## Scoop (Windows)

**Manifest:** `scoop/incus-tui.json`

**Maintainer instructions:**
Replace `$VERSION`, `$WINDOWS_ZIP_SHA256`, and `$GITHUB_REPO` with real values,
then submit to the [Scoop bucket](https://github.com/ScoopInstaller/Homebucket) or
a custom bucket.

**For users (custom bucket):**
```powershell
scoop bucket add incus-tui https://github.com/<owner>/scoop-incustui
scoop install incus-tui
```

## Linux packages (.deb / .rpm)

**Build script:** `linux/fpm/make-packages.sh`

Requires: `fpm` (`gem install fpm`) and the pre-built `dist/incus-tui/` directory
from the PyInstaller build (CI output of the `build-linux` job).

```bash
# After building the binary with PyInstaller:
./distribution/linux/fpm/make-packages.sh 0.1.0 dist/incus-tui/

# Produces:
#   incus-tui-0.1.0-linux-x86_64.deb
#   incus-tui-0.1.0-linux-x86_64.rpm
```

**Runtime dependencies** (declared in package metadata, not bundled):
- `incus` CLI
- `openssh-client`
- `sshfs` (FUSE)

## AUR (Arch Linux)

**PKGBUILD:** `archlinux/PKGBUILD`

**Maintainer instructions:**
Replace `$VERSION`, `$LINUX_TAR_SHA256`, and `$GITHUB_REPO` with real values,
then push to an AUR git repository.

**For users:**
```bash
git clone https://aur.archlinux.org/incus-tui.git
cd incus-tui
makepkg -si
```

## CI release process (summary)

When a tag `v*` is pushed:

1. Tests run on 3 OSes × 2 Python versions.
2. `publish-pypi` job builds sdist+wheel and publishes to PyPI via OIDC.
3. `create-release` creates the GitHub Release.
4. `build-linux`, `build-macos-*`, `build-windows` build binaries and upload as
   Release assets.
5. `homebrew-formula.yml` opens a PR to the Homebrew tap repo (if configured).

Steps 2–4 run in parallel after step 1 passes.
