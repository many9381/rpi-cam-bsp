# HailoRT 4.24.0 requires this protobuf compiler/runtime pair (upstream v21.12).
HAILO_PROTOBUF_REV = "f0dc78d7e6e331b8c6bb2d5283e06aa26883ca7c"
HAILO_PROTOBUF_SOURCE = "${UNPACKDIR}/protobuf-${HAILO_PROTOBUF_REV}"
SRC_URI += "git://github.com/protocolbuffers/protobuf.git;protocol=https;nobranch=1;name=protobuf;destsuffix=protobuf-${HAILO_PROTOBUF_REV}"
SRCREV_protobuf = "${HAILO_PROTOBUF_REV}"
