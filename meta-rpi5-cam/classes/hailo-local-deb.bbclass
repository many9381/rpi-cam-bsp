# Use BitBake's data archive unpacker; Debian maintainer scripts are not run.
SRC_URI:prepend = "file://${HAILO_DEB_FILE};subdir=deb;name=deb "
SRC_URI[deb.sha256sum] = "${HAILO_DEB_SHA256}"
S = "${UNPACKDIR}/deb"

# Private inputs are optional for non-Hailo images. Selecting a Hailo package
# without its archive gives a missing-provider error with this reason.
python __anonymous() {
    import os
    filename = d.getVar("HAILO_DEB_FILE")
    for directory in d.getVar("FILESPATH").split(":"):
        bb.parse.mark_dependency(d, os.path.join(directory, filename))
    if not bb.utils.which(d.getVar("FILESPATH"), filename):
        raise bb.parse.SkipRecipe("missing local Debian package %s; place it in the Hailo recipe files/ directory" % filename)
}

# file:// fetches track changes but do not enforce SRC_URI checksums.
# Verify the reviewed archive bytes before BitBake extracts any payload.
python hailo_verify_deb() {
    from rpi5cam.local_deb import verify_sha256
    uri = "file://" + d.getVar("HAILO_DEB_FILE")
    path = bb.fetch2.Fetch([uri], d).localpath(uri)
    try:
        verify_sha256(path, d.getVar("HAILO_DEB_SHA256"))
    except ValueError as error:
        bb.fatal(str(error))
}
do_unpack[prefuncs] += "hailo_verify_deb"
