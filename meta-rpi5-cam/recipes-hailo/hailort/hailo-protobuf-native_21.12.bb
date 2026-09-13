SUMMARY = "Private native protobuf compiler for HailoRT 4.24.0"
HOMEPAGE = "https://protobuf.dev/"
LICENSE = "BSD-3-Clause"
LIC_FILES_CHKSUM = "file://LICENSE;md5=37b5762e07f0af8c74ce80a8bda4266b"

require hailo-protobuf-source.inc

S = "${HAILO_PROTOBUF_SOURCE}"

inherit cmake native

EXTRA_OECMAKE = " \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -Dprotobuf_BUILD_TESTS=OFF \
    -Dprotobuf_BUILD_EXAMPLES=OFF \
    -Dprotobuf_BUILD_SHARED_LIBS=OFF \
    -Dprotobuf_WITH_ZLIB=OFF \
    -Dprotobuf_INSTALL=OFF \
"
OECMAKE_TARGET_COMPILE = "protoc"

# Keep this compiler separate from OE's current protobuf-native. No native
# protobuf libraries or CMake import files are exposed to the target build.
do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${B}/protoc ${D}${bindir}/hailo-protoc
}
