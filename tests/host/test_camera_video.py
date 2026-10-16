from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "real media verification requires ffmpeg and ffprobe")
class CameraVideoMediaTest(unittest.TestCase):
    def test_timestamped_mp4_passes_and_raw_h264_without_timestamps_fails(self) -> None:
        """Catches validators accepting fabricated timing or rejecting actual MP4 metadata."""
        with tempfile.TemporaryDirectory(prefix="camera-media-") as temporary:
            directory = Path(temporary)
            mp4 = directory / "video.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "color=size=1920x1080:rate=30", "-t", "10", "-c:v", "libx264",
                "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(mp4),
            ], check=True, capture_output=True)
            raw = directory / "video.h264"
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-c:v", "copy",
                            "-f", "h264", str(raw)], check=True, capture_output=True)
            for media, expected in ((mp4, 0), (raw, 1)):
                with self.subTest(media=media.suffix):
                    probe = subprocess.run([
                        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                        "-show_entries", "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_read_frames,duration:format=format_name,duration",
                        "-of", "json", str(media),
                    ], check=True, text=True, capture_output=True)
                    metadata = directory / "metadata.json"
                    metadata.write_text(probe.stdout, encoding="utf-8")
                    result = subprocess.run([
                        "python3", str(REPO_ROOT / "scripts/lib/camera_video.py"), str(metadata),
                    ], text=True, capture_output=True, check=False)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    if expected == 0:
                        measured = json.loads(result.stdout)
                        self.assertEqual(measured["decoded_frames"], 300)
                        self.assertEqual(measured["duration_seconds"], 10.0)
                        self.assertEqual(measured["average_frame_rate"], 30.0)
                    else:
                        self.assertIn("invalid camera video metadata", result.stderr)


if __name__ == "__main__":
    unittest.main()
