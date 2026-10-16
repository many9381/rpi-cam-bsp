# 10.48 fixes CVE-2026-86145; 10.49 also fixes CVE-2026-103111.
# https://github.com/PCRE2Project/pcre2/releases/tag/pcre2-10.49
# Drop this append when the pinned OE-Core recipe includes these fixes.
PV = "10.49"
SRC_URI[sha256sum] = "53c156e1ba416a20da8e65395daa132da0d80e76910424caca3fcdae7831d384"
