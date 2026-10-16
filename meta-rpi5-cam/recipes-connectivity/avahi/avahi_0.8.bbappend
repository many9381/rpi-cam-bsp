FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Bound simple-protocol resources using the existing documented client limit.
# Partial mitigation: holding every slot can still deny new simple clients.
SRC_URI += "file://0001-simple-protocol-bound-clients.patch"
SRC_URI += "file://0002-simple-protocol-backoff-and-idle-deadline.patch"
