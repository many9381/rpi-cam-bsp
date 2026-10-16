SUMMARY = "OpenAI Codex command-line coding agent"
DESCRIPTION = "Latest stable upstream ARM64 CLI with the package layout and resources required for background-server startup."
HOMEPAGE = "https://learn.chatgpt.com/docs/codex/cli"
PV = "${CODEX_RELEASE_VERSION}"
LICENSE = "Apache-2.0 & MIT & LGPL-2.0-or-later"
LIC_FILES_CHKSUM = " \
    file://${UNPACKDIR}/licenses/codex-${PV}-LICENSE;md5=a3b5a15be5a5ec6f92aa27af75fae5f2 \
    file://${UNPACKDIR}/licenses/codex-${PV}-NOTICE;md5=d2134976880b6939b6d1c91b83f5fbd5 \
    file://${UNPACKDIR}/licenses/codex-${PV}-wezterm-MIT.txt;md5=f7fd3d551bf6ddfd312b31df30183bfd \
    file://${UNPACKDIR}/ratatui-MIT.txt;md5=c7e031a8348874206cb11fb4962c9dc6 \
    file://${UNPACKDIR}/licenses/codex-${PV}-bubblewrap-COPYING;md5=5f30f0716dfdd0d91eb439ebec522ec2 \
    file://${UNPACKDIR}/ripgrep-MIT.txt;md5=8d0d0aa488af0ab9aafa3b85a7fc8e12 \
"

# codex-latest resolves these inputs before recipe parsing on each invocation.
# Keep concrete versioned URLs/checksums so downloads and sstate cannot return
# an older release just because a moving 'latest' URL stayed unchanged.
CODEX_SOURCE_REV = "${CODEX_RELEASE_SOURCE_REV}"
SRC_URI = " \
    ${CODEX_RELEASE_BINARY_URL};name=binary;downloadfilename=codex-package-${PV}-aarch64-unknown-linux-musl.tar.gz;subdir=codex \
    https://raw.githubusercontent.com/openai/codex/${CODEX_SOURCE_REV}/LICENSE;name=license;downloadfilename=codex-${PV}-LICENSE;subdir=licenses \
    https://raw.githubusercontent.com/openai/codex/${CODEX_SOURCE_REV}/NOTICE;name=notice;downloadfilename=codex-${PV}-NOTICE;subdir=licenses \
    https://raw.githubusercontent.com/openai/codex/${CODEX_SOURCE_REV}/third_party/wezterm/LICENSE;name=wezterm;downloadfilename=codex-${PV}-wezterm-MIT.txt;subdir=licenses \
    https://raw.githubusercontent.com/openai/codex/${CODEX_SOURCE_REV}/codex-rs/vendor/bubblewrap/COPYING;name=bubblewrap;downloadfilename=codex-${PV}-bubblewrap-COPYING;subdir=licenses \
    file://ratatui-MIT.txt \
    file://ripgrep-MIT.txt \
"
SRC_URI[binary.sha256sum] = "${CODEX_RELEASE_BINARY_SHA256}"
SRC_URI[license.sha256sum] = "${CODEX_RELEASE_LICENSE_SHA256}"
SRC_URI[notice.sha256sum] = "${CODEX_RELEASE_NOTICE_SHA256}"
SRC_URI[wezterm.sha256sum] = "${CODEX_RELEASE_WEZTERM_SHA256}"
SRC_URI[bubblewrap.sha256sum] = "${CODEX_RELEASE_BUBBLEWRAP_SHA256}"

python __anonymous() {
    if not d.getVar("CODEX_RELEASE_VERSION"):
        raise bb.parse.SkipRecipe("codex-cli requires INHERIT += 'codex-latest' (enabled by camera profiles)")
}

S = "${UNPACKDIR}/codex"
COMPATIBLE_HOST = "^aarch64-.*-linux.*"
PACKAGE_ARCH = "${TARGET_ARCH}"

inherit bin_package

# The CLI, code-mode helper and bwrap are static musl binaries on glibc images.
# Preserve the already-stripped release bytes; no target Rust/Node toolchain or
# musl dynamic loader is needed. In particular, Codex verifies bundled bwrap's
# embedded digest. Bundled rg uses glibc; normal dependency/ELF QA stays enabled.
INHIBIT_DEFAULT_DEPS = "1"
# Supply shlib provider metadata for the upstream glibc-linked ripgrep.
DEPENDS = "virtual/libc virtual/compilerlibs"
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
INSANE_SKIP:${PN} += "already-stripped"

# Bundled rg is glibc-linked even though the CLI itself is static musl.
# Keep its runtime providers explicit: restored package metadata can otherwise
# omit the automatic shlib dependencies and fail the normal file-rdeps QA.
RDEPENDS:${PN} = "bash bubblewrap ca-certificates git glibc libgcc ncurses-terminfo-base ripgrep"

do_install() {
    install -d ${D}${bindir}
    install -d ${D}${libdir}/codex/bin ${D}${libdir}/codex/codex-path ${D}${libdir}/codex/codex-resources
    install -m 0755 ${S}/bin/codex ${D}${libdir}/codex/bin/codex
    install -m 0755 ${S}/bin/codex-code-mode-host ${D}${libdir}/codex/bin/codex-code-mode-host
    install -m 0644 ${S}/codex-package.json ${D}${libdir}/codex/codex-package.json
    install -m 0755 ${S}/codex-path/rg ${D}${libdir}/codex/codex-path/rg
    install -m 0755 ${S}/codex-resources/bwrap ${D}${libdir}/codex/codex-resources/bwrap
    ln -s ${libdir}/codex/bin/codex ${D}${bindir}/codex
    ln -s ${libdir}/codex/bin/codex-code-mode-host ${D}${bindir}/codex-code-mode-host

    # The daemon copies its entire source package. Keep it isolated from /usr,
    # with no escaping resource symlinks. Optional zsh/voice resources and all
    # user configuration/credentials remain excluded; use the system Bash.
    install -d ${D}${datadir}/licenses/${PN}
    install -m 0644 ${UNPACKDIR}/licenses/codex-${PV}-LICENSE ${D}${datadir}/licenses/${PN}/LICENSE
    install -m 0644 ${UNPACKDIR}/licenses/codex-${PV}-NOTICE ${D}${datadir}/licenses/${PN}/NOTICE
    install -m 0644 ${UNPACKDIR}/licenses/codex-${PV}-wezterm-MIT.txt ${D}${datadir}/licenses/${PN}/wezterm-MIT.txt
    install -m 0644 ${UNPACKDIR}/ratatui-MIT.txt ${D}${datadir}/licenses/${PN}/ratatui-MIT.txt
    install -m 0644 ${UNPACKDIR}/licenses/codex-${PV}-bubblewrap-COPYING ${D}${datadir}/licenses/${PN}/bubblewrap-COPYING
    install -m 0644 ${UNPACKDIR}/ripgrep-MIT.txt ${D}${datadir}/licenses/${PN}/ripgrep-MIT.txt
}

FILES:${PN} = "${bindir}/codex ${bindir}/codex-code-mode-host ${libdir}/codex ${datadir}/licenses/${PN}"
