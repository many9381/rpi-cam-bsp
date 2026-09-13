# HailoRT 4.24.0 requires this protobuf compiler/runtime pair (upstream v21.12).
HAILO_PROTOBUF_REV = "f0dc78d7e6e331b8c6bb2d5283e06aa26883ca7c"
HAILO_PROTOBUF_SOURCE = "${UNPACKDIR}/protobuf-${HAILO_PROTOBUF_REV}"
SRC_URI += "https://codeload.github.com/protocolbuffers/protobuf/tar.gz/${HAILO_PROTOBUF_REV};name=protobuf;downloadfilename=protobuf-${HAILO_PROTOBUF_REV}.tar.gz"
SRC_URI[protobuf.sha256sum] = "d594b561fb41bf243233d8f411c7f2b7d913e5c9c1be4ca439baf7e48384c893"
