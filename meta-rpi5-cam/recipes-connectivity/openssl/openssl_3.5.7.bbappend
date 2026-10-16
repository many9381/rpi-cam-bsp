# Keep the pinned OE-Core recipe and its integration patches, but consume the
# maintained 3.5 LTS security release. Drop this append when OE-Core catches up.
# https://openssl-library.org/news/openssl-3.5-notes/
PV = "3.5.9"
SRC_URI[sha256sum] = "603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a"

SRC_URI:remove = "http://www.openssl.org/source/openssl-${PV}.tar.gz"
SRC_URI:prepend = "https://www.openssl.org/source/openssl-${PV}.tar.gz "
