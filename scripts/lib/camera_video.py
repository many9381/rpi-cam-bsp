#!/usr/bin/env python3
"""Validate measured ffprobe metadata for the ten-second camera sample."""

from __future__ import annotations

import json
import math
import sys
from fractions import Fraction
from pathlib import Path


def validate_video(metadata: object) -> dict[str, object]:
    if not isinstance(metadata, dict):
        raise ValueError("expected ffprobe JSON object")
    streams = metadata.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        raise ValueError("expected one video stream")
    stream = streams[0]
    if not isinstance(stream, dict):
        raise ValueError("invalid video stream")
    if (stream.get("codec_name"), stream.get("width"), stream.get("height")) != (
        "h264", 1920, 1080
    ):
        raise ValueError("expected H.264 at 1920x1080")
    container = metadata.get("format")
    if not isinstance(container, dict) or "mp4" not in str(
        container.get("format_name", "")
    ).split(","):
        raise ValueError("expected MP4 container")
    duration = float(stream["duration"])
    container_duration = float(container["duration"])
    for value in (duration, container_duration):
        if not math.isfinite(value) or not 9.5 <= value <= 10.5:
            raise ValueError("expected measured duration of 9.5 to 10.5 seconds")
    if abs(duration - container_duration) > 0.1:
        raise ValueError("stream and container durations disagree")
    rates = [float(Fraction(stream[name])) for name in ("r_frame_rate", "avg_frame_rate")]
    if any(not math.isfinite(rate) or abs(rate - 30) > 0.5 for rate in rates):
        raise ValueError("expected measured frame rate near 30 fps")
    count_text = stream["nb_read_frames"]
    if not isinstance(count_text, str) or not count_text.isdecimal():
        raise ValueError("missing decoded frame count")
    frames = int(count_text)
    if not 285 <= frames <= 315 or abs(frames / duration - rates[1]) > 0.5:
        raise ValueError("frame count does not match duration and average rate")
    return {"codec": "h264", "width": 1920, "height": 1080, "container": "mp4",
            "decoded_frames": frames, "duration_seconds": duration,
            "frame_rate": rates[0], "average_frame_rate": rates[1]}


def main() -> int:
    try:
        metadata = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = validate_video(metadata)
    except (IndexError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as error:
        print(f"invalid camera video metadata: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
