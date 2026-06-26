# typed: false
# frozen_string_literal: true

class IncusTui < Formula
  desc "Terminal UI to manage Incus containers"
  homepage "https://github.com/$GITHUB_REPO/incus-tui"
  url "https://pypi.io/packages/source/incus-tui/incus-tui-$VERSION.tar.gz"
  sha256 "$SOURCE_SHA256"
  license "MIT"
  version "$VERSION"

  depends_on "python@3.12"

  def install
    system Formula["python@3.12"].opt_bin/"pip", "install", "--prefix=", package_name, "incus-tui"
    bin.install_symlink opt_bin/"incus-tui"
  end

  test do
    assert_match "incus-tui #{version}", shell_output("#{bin}/incus-tui --version").strip
  end
end
