# Keep the pinned OE-Core integration and use the upstream security release.
# Official release announcement: https://www.openssh.org/txt/release-10.6
# The published base64 SHA-256 was decoded and checked against the portable tarball.
PV = "10.6p1"
SRC_URI[sha256sum] = "a9dc9565dffe8640f64d863cd29a32bc4a3dbdec0566a7fc44c5d6ee767d5f39"

# Red Hat, the CNA, confirms these affect its downstream OpenSSH changes only.
# This recipe uses the official portable source without those downstream patches.
CVE_STATUS[CVE-2026-55653] = "not-applicable-platform: Red Hat-only FIPS DH-GEX known-group patch; https://access.redhat.com/security/cve/CVE-2026-55653"
CVE_STATUS[CVE-2026-55654] = "not-applicable-platform: Red Hat-only GSSAPI auth-indicators patch; https://access.redhat.com/security/cve/CVE-2026-55654"
CVE_STATUS[CVE-2026-55655] = "not-applicable-platform: Red Hat-only abstract X11 socket patch; https://access.redhat.com/security/cve/CVE-2026-55655"
