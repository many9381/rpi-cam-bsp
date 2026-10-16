"""Resolve the latest stable Codex release once per BitBake invocation."""

import hashlib
import json
import re
import urllib.request


LATEST_URL = "https://api.github.com/repos/openai/codex/releases/latest"
ASSET_NAME = "codex-package-aarch64-unknown-linux-musl.tar.gz"


def resolve_latest(read_url):
    """Return concrete release inputs; never fall back to a previous release."""
    release = json.loads(read_url(LATEST_URL))
    tag = release.get("tag_name", "")
    match = re.fullmatch(r"rust-v(\d+\.\d+\.\d+)", tag)
    if not match or release.get("draft") is not False or release.get("prerelease") is not False:
        raise ValueError("Codex latest release must be a published stable rust-vX.Y.Z tag")

    assets = [asset for asset in release.get("assets", []) if asset.get("name") == ASSET_NAME]
    if len(assets) != 1:
        raise ValueError(f"Codex latest release must contain exactly one {ASSET_NAME}")
    asset = assets[0]
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Codex ARM64 release asset is missing a valid SHA-256 digest")
    binary_url = f"https://github.com/openai/codex/releases/download/{tag}/{ASSET_NAME}"
    if asset.get("browser_download_url") != binary_url:
        raise ValueError("Codex ARM64 asset URL does not match the selected official release")

    # target_commitish can be 'main'; resolve the actual release tag instead.
    commit = json.loads(read_url(f"https://api.github.com/repos/openai/codex/commits/{tag}"))
    source_rev = commit.get("sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", source_rev):
        raise ValueError("Codex release tag did not resolve to a source commit")
    result = {
        "version": match.group(1),
        "source_rev": source_rev,
        "binary_url": binary_url,
        "binary_sha256": digest.removeprefix("sha256:"),
    }
    for name, path in (
        ("license", "LICENSE"),
        ("notice", "NOTICE"),
        ("wezterm", "third_party/wezterm/LICENSE"),
        ("bubblewrap", "codex-rs/vendor/bubblewrap/COPYING"),
    ):
        contents = read_url(f"https://raw.githubusercontent.com/openai/codex/{source_rev}/{path}")
        if not contents:
            raise ValueError(f"Codex release {path} is empty")
        result[f"{name}_sha256"] = hashlib.sha256(contents).hexdigest()
    return result


def configure_latest(d):
    """Populate config before recipes/signatures are parsed, including workers.

    Use BitBake's revision cache just like AUTOREV: the cooker clears it on a
    new invocation, while parsing workers and task workers reuse that build's
    selected release. This prevents a release arriving mid-build from changing
    PV, source URLs or task hashes between the cooker and a task worker.
    """
    import bb
    import bb.fetch2

    if d.getVar("BB_SRCREV_POLICY") not in (None, "", "clear"):
        bb.fatal("Latest Codex requires BB_SRCREV_POLICY = 'clear'; cached revisions cannot select latest")

    def read_url(url):
        bb.fetch2.check_network_access(d, "resolve latest Codex release", url)
        request = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "yocto-rpi5-cam-firmware",
        })
        with urllib.request.urlopen(request, timeout=30) as response:
            contents = response.read(8 * 1024 * 1024 + 1)
        if len(contents) > 8 * 1024 * 1024:
            raise ValueError("Codex release metadata exceeds 8 MiB")
        return contents

    class LatestRelease(bb.fetch2.FetchMethod):
        def _revision_key(self, ud, data, name):
            return "rpi5cam:codex-latest-release-v2"

        def _latest_revision(self, ud, data, name):
            return json.dumps(resolve_latest(read_url), sort_keys=True)

    try:
        metadata = json.loads(LatestRelease().latest_revision(None, d, "codex"))
    except (OSError, ValueError, TypeError, AttributeError, bb.fetch2.BBFetchException) as error:
        bb.fatal(f"Cannot resolve latest Codex release: {error}")
    for name, value in metadata.items():
        d.setVar("CODEX_RELEASE_" + name.upper(), value)
