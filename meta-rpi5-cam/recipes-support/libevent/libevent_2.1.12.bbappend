# Stable maintenance release; existing 2.1 SONAMEs, license text and all
# inherited OE autotools/ptest patches are preserved.
PV = "2.1.13"
CVE_VERSION = "2.1.13"
SRC_URI[sha256sum] = "f7e9383b8c0baa81b687e5b5eecc01beefaf1b19b64151d95ed61647fe7a315c"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://0001-http-reject-nul-string-inputs.patch"
SRC_URI += "file://0002-http-check-duplicate-content-length-without-te.patch"
