# Includes the 3.53.2 fix for CVE-2026-11822 and CVE-2026-11824 (the same issue).
# https://sqlite.org/cves.html
# https://sqlite.org/releaselog/3_53_4.html
# Drop this append when the pinned OE-Core recipe includes these fixes.
PV = "3.53.4"
SRC_URI[sha256sum] = "0e9483900e92cd5de8fd48d16bf9200145a61f7fd5be542a5ac81d8a9516eb9c"

SRC_URI:remove = "http://www.sqlite.org/2026/sqlite-autoconf-${SQLITE_PV}.tar.gz"
SRC_URI:prepend = "https://www.sqlite.org/2026/sqlite-autoconf-${SQLITE_PV}.tar.gz "
