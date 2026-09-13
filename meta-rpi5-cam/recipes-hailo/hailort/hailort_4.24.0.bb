SUMMARY = "Hailo-8 userspace runtime and diagnostic CLI"
HOMEPAGE = "https://github.com/hailo-ai/hailort"
LICENSE = "MIT & BSD-2-Clause & BSD-3-Clause & MPL-2.0 & Zlib"
LIC_FILES_CHKSUM = " \
    file://hailort/LICENSE;md5=ed57bbf10be0c74ecf2c80710208b2b3 \
    file://${HAILO_PROTOBUF_SOURCE}/LICENSE;md5=37b5762e07f0af8c74ce80a8bda4266b \
    file://${UNPACKDIR}/spdlog-${HAILO_SPDLOG_REV}/LICENSE;md5=9573510928429ad0cbe5ba4de77546e9 \
    file://${UNPACKDIR}/readerwriterqueue-${HAILO_QUEUE_REV}/LICENSE.md;md5=74e53ed227208b73f15a08361fd99b9d \
    file://${UNPACKDIR}/readerwriterqueue-${HAILO_QUEUE_REV}/atomicops.h;beginline=362;endline=379;md5=a7b8d194f0354b9416f6c0cc7693613b \
    file://${UNPACKDIR}/xxHash-${HAILO_XXHASH_REV}/LICENSE;md5=13be6b481ff5616f77dda971191bb29b \
    file://${UNPACKDIR}/eigen-${HAILO_EIGEN_REV}/COPYING.MPL2;md5=815ca599c9df247a0c7f619bab123dad \
    file://${UNPACKDIR}/eigen-${HAILO_EIGEN_REV}/COPYING.BSD;md5=2dd0510ee95e59ca28834b875bc96596 \
    file://${UNPACKDIR}/CLI11-${HAILO_CLI11_REV}/LICENSE;md5=9ad746b5f49c0fd53c08ca1faff1922c \
    file://${UNPACKDIR}/nlohmann_json_cmake_fetchcontent-${HAILO_JSON_REV}/LICENSE.MIT;md5=f8a8f918f1513404c8366d7a63ab6d97 \
    file://${UNPACKDIR}/DotWriter-${HAILO_DOTWRITER_REV}/LICENSE;md5=1accdb7c0604e459642c7a408366688c \
"

SRC_URI = " \
    git://github.com/hailo-ai/hailort.git;protocol=https;branch=hailo8 \
    file://0001-use-native-protoc-and-respect-cross-install.patch \
"
SRCREV = "63adffec12da88f1e7cfdc07f2e07681671e83e8"
S = "${UNPACKDIR}/git"

require hailo-protobuf-source.inc

# These are the exact revisions in upstream hailort/cmake/external/*.cmake.
# Fetching here makes the build work with BitBake's task network isolation.
HAILO_SPDLOG_REV = "27cb4c76708608465c413f6d0e6b8d99a4d84302"
HAILO_QUEUE_REV = "435e36540e306cac40fcfeab8cc0a22d48464509"
HAILO_XXHASH_REV = "bbb27a5efb85b92a0486cf361a8635715a53f6ba"
HAILO_EIGEN_REV = "3147391d946bb4b6c68edd901f2add6ac1f31f8c"
HAILO_CLI11_REV = "ae78ac41cf225706e83f57da45117e3e90d4a5b4"
HAILO_JSON_REV = "391786c6c3abdd3eeb993a3154f1f2a4cfe137a0"
HAILO_DOTWRITER_REV = "e5fa8f281adca10dd342b1d32e981499b8681daf"
SRC_URI += " \
    https://codeload.github.com/gabime/spdlog/tar.gz/${HAILO_SPDLOG_REV};name=spdlog;downloadfilename=spdlog-${HAILO_SPDLOG_REV}.tar.gz \
    https://codeload.github.com/cameron314/readerwriterqueue/tar.gz/${HAILO_QUEUE_REV};name=queue;downloadfilename=readerwriterqueue-${HAILO_QUEUE_REV}.tar.gz \
    https://codeload.github.com/Cyan4973/xxHash/tar.gz/${HAILO_XXHASH_REV};name=xxhash;downloadfilename=xxHash-${HAILO_XXHASH_REV}.tar.gz \
    https://gitlab.com/libeigen/eigen/-/archive/${HAILO_EIGEN_REV}/eigen-${HAILO_EIGEN_REV}.tar.gz;name=eigen \
    https://codeload.github.com/hailo-ai/CLI11/tar.gz/${HAILO_CLI11_REV};name=cli11;downloadfilename=CLI11-${HAILO_CLI11_REV}.tar.gz \
    https://codeload.github.com/ArthurSonzogni/nlohmann_json_cmake_fetchcontent/tar.gz/${HAILO_JSON_REV};name=json;downloadfilename=nlohmann_json_cmake_fetchcontent-${HAILO_JSON_REV}.tar.gz \
    https://codeload.github.com/hailo-ai/DotWriter/tar.gz/${HAILO_DOTWRITER_REV};name=dotwriter;downloadfilename=DotWriter-${HAILO_DOTWRITER_REV}.tar.gz \
"
SRC_URI[spdlog.sha256sum] = "7d512b37019b61646cd6fd1e48f52a3cf3e098f36b33ba9c059fe51301ff40b3"
SRC_URI[queue.sha256sum] = "0a15f844f129ac585d751534e4eb1498fcbb890ed9cd08f5041573495b46a4b1"
SRC_URI[xxhash.sha256sum] = "716fbe4fc85ecd36488afbbc635b59b5ab6aba5ed3b69d4a32a46eae5a453d38"
SRC_URI[eigen.sha256sum] = "0c8c490764f9c2a793133491adca0cd073b73e0bde965c68cbe58d91b5ed4261"
SRC_URI[cli11.sha256sum] = "12e815f9fa9fd21c9743af2280a5b77d20713ea36095da0e76f12a32f02bf92b"
SRC_URI[json.sha256sum] = "614ffcc9812aa2d2cbe0d602e258c2fe7d06eddd68dec0c51039f3f210a33ac6"
SRC_URI[dotwriter.sha256sum] = "911e1eeb20485d3563d54215ec8cc9ac5e529a1773adbdbf5aed3d7dfd1f8052"

inherit cmake

DEPENDS = "hailo-protobuf-native"
PACKAGECONFIG ??= "cli"
PACKAGECONFIG[cli] = "-DHAILO_BUILD_CLI=ON,-DHAILO_BUILD_CLI=OFF"

# Eigen's MPL-only guard prevents accidental inclusion of LGPL extensions.
CXXFLAGS:append = " -DEIGEN_MPL2_ONLY"
EXTRA_OECMAKE = " \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DCMAKE_POLICY_DEFAULT_CMP0169=OLD \
    -DFETCHCONTENT_FULLY_DISCONNECTED=ON \
    -DFETCHCONTENT_UPDATES_DISCONNECTED=ON \
    -DFETCHCONTENT_SOURCE_DIR_PROTOBUF=${HAILO_PROTOBUF_SOURCE} \
    -DFETCHCONTENT_SOURCE_DIR_SPDLOG=${UNPACKDIR}/spdlog-${HAILO_SPDLOG_REV} \
    -DFETCHCONTENT_SOURCE_DIR_READERWRITERQUEUE=${UNPACKDIR}/readerwriterqueue-${HAILO_QUEUE_REV} \
    -DFETCHCONTENT_SOURCE_DIR_XXHASH=${UNPACKDIR}/xxHash-${HAILO_XXHASH_REV} \
    -DFETCHCONTENT_SOURCE_DIR_EIGEN=${UNPACKDIR}/eigen-${HAILO_EIGEN_REV} \
    -DFETCHCONTENT_SOURCE_DIR_CLI11=${UNPACKDIR}/CLI11-${HAILO_CLI11_REV} \
    -DFETCHCONTENT_SOURCE_DIR_JSON=${UNPACKDIR}/nlohmann_json_cmake_fetchcontent-${HAILO_JSON_REV} \
    -DFETCHCONTENT_SOURCE_DIR_DOTWRITER=${UNPACKDIR}/DotWriter-${HAILO_DOTWRITER_REV} \
    -DProtobuf_PROTOC_EXECUTABLE=${STAGING_BINDIR_NATIVE}/hailo-protoc \
    -DHAILO_BUILD_SERVICE=OFF \
    -DHAILO_BUILD_GSTREAMER=OFF \
    -DHAILO_BUILD_EXAMPLES=OFF \
    -DHAILO_BUILD_UT=OFF \
    -DHAILO_BUILD_DOC=OFF \
    -DHAILO_BUILD_PYHAILORT_INTERNAL=OFF \
    -DHAILO_BUILD_RAW_CONNECTION=OFF \
    -DBUILD_TESTING=OFF \
    -DEIGEN_BUILD_DOC=OFF \
    -DEIGEN_BUILD_PKGCONFIG=OFF \
    -DCLI11_BUILD_TESTS=OFF \
    -DCLI11_BUILD_EXAMPLES=OFF \
    -DCLI11_INSTALL=OFF \
"

PACKAGES =+ "${PN}-cli"
FILES:${PN}-cli = "${bindir}/hailortcli ${datadir}/bash-completion"
RDEPENDS:${PN}-cli = "${PN} (= ${EXTENDPKGV})"
