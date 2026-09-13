SUMMARY = "OpenAI Codex command-line coding agent"
DESCRIPTION = "Pinned upstream ARM64 CLI and code-mode helper with Yocto-managed shell, search and sandbox tools."
HOMEPAGE = "https://learn.chatgpt.com/docs/codex/cli"
LICENSE = "Apache-2.0 & MIT"
LIC_FILES_CHKSUM = " \
    file://${UNPACKDIR}/licenses/codex-${PV}-LICENSE;md5=a3b5a15be5a5ec6f92aa27af75fae5f2 \
    file://${UNPACKDIR}/licenses/codex-${PV}-NOTICE;md5=d2134976880b6939b6d1c91b83f5fbd5 \
    file://${UNPACKDIR}/licenses/codex-${PV}-wezterm-MIT.txt;md5=f7fd3d551bf6ddfd312b31df30183bfd \
    file://${UNPACKDIR}/ratatui-MIT.txt;md5=c7e031a8348874206cb11fb4962c9dc6 \
"

# The release tag resolves to this source commit; raw license URLs are immutable.
CODEX_SOURCE_REV = "6b9826e3aa83b1a5947db50f4332cb9c65f1b340"
SRC_URI = " \
    https://github.com/openai/codex/releases/download/rust-v${PV}/codex-package-aarch64-unknown-linux-musl.tar.gz;name=binary;downloadfilename=codex-package-${PV}-aarch64-unknown-linux-musl.tar.gz;subdir=codex \
    https://raw.githubusercontent.com/openai/codex/${CODEX_SOURCE_REV}/LICENSE;name=license;downloadfilename=codex-${PV}-LICENSE;subdir=licenses \
    https://raw.githubusercontent.com/openai/codex/${CODEX_SOURCE_REV}/NOTICE;name=notice;downloadfilename=codex-${PV}-NOTICE;subdir=licenses \
    https://raw.githubusercontent.com/openai/codex/${CODEX_SOURCE_REV}/third_party/wezterm/LICENSE;name=wezterm;downloadfilename=codex-${PV}-wezterm-MIT.txt;subdir=licenses \
    file://ratatui-MIT.txt \
"
SRC_URI[binary.sha256sum] = "97d93e11df72d3c26772db019e6ea8bb72c246500d46b98c760839f3240355e6"
SRC_URI[license.sha256sum] = "d17f227e4df5da1600391338865ce0f3055211760a36688f816941d58232d8dc"
SRC_URI[notice.sha256sum] = "9d71575ecfd9a843fc1677b0efb08053c6ba9fd686a0de1a6f5382fd3c220915"
SRC_URI[wezterm.sha256sum] = "331312c214f14dc1455a0e45e3a66f4b70bbc73916cffd525570e8cdb9d63bf4"

S = "${UNPACKDIR}/codex"
COMPATIBLE_HOST = "^aarch64-.*-linux.*"
PACKAGE_ARCH = "${TARGET_ARCH}"

inherit bin_package

# These two upstream executables are static musl binaries, even on glibc images.
# Preserve the already-stripped release bytes; no target Rust/Node toolchain or
# musl dynamic loader is needed. All other package QA checks remain enabled.
INHIBIT_DEFAULT_DEPS = "1"
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
INSANE_SKIP:${PN} += "already-stripped"

RDEPENDS:${PN} = "bash bubblewrap ca-certificates git ncurses-terminfo-base ripgrep"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${S}/bin/codex ${D}${bindir}/codex
    # Upstream finds this helper next to the running codex executable.
    install -m 0755 ${S}/bin/codex-code-mode-host ${D}${bindir}/codex-code-mode-host

    # Do not install the archive's bundled bwrap/rg/zsh, installer metadata,
    # user configuration, credentials or an automatic updater. Use distro tools.
    install -d ${D}${datadir}/licenses/${PN}
    install -m 0644 ${UNPACKDIR}/licenses/codex-${PV}-LICENSE ${D}${datadir}/licenses/${PN}/LICENSE
    install -m 0644 ${UNPACKDIR}/licenses/codex-${PV}-NOTICE ${D}${datadir}/licenses/${PN}/NOTICE
    install -m 0644 ${UNPACKDIR}/licenses/codex-${PV}-wezterm-MIT.txt ${D}${datadir}/licenses/${PN}/wezterm-MIT.txt
    install -m 0644 ${UNPACKDIR}/ratatui-MIT.txt ${D}${datadir}/licenses/${PN}/ratatui-MIT.txt
}

FILES:${PN} = "${bindir}/codex ${bindir}/codex-code-mode-host ${datadir}/licenses/${PN}"
