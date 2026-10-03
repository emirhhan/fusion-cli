"""`evals/kabul/areas/remotion.py` denetçisinin testleri.

Gerçek Remotion render'ı yoktur; video `ffmpeg -f lavfi` ile üretilir. ffmpeg/ffprobe
yoksa ilgili testler atlanır.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from evals.kabul.areas import _pixels, remotion
from evals.kabul.model import Inspection
from PIL import Image

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe yok")

GOOD_SOURCE = """import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
export const Intro = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 30], [0, 1]);
  return <AbsoluteFill style={{opacity}}>Merhaba</AbsoluteFill>;
};
"""

LAVFI_ANIMATED = "testsrc=duration=10:size=1920x1080:rate=30,hue=h=t*36"
LAVFI_BLACK = "color=c=black:s=1920x1080:r=30:d=10"
LAVFI_WRONG_SPEC = "testsrc=duration=2:size=320x240:rate=24"


def _png(color: tuple[int, int, int], size: tuple[int, int] = (64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _render(destination: Path, lavfi: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            lavfi,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(destination),
        ],
        check=True,
        capture_output=True,
    )


def _write_source(workdir: Path, text: str = GOOD_SOURCE) -> None:
    source = workdir / "src" / "Intro.tsx"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(text, encoding="utf-8")


def _by_name(inspection: Inspection) -> dict[str, bool]:
    return {check.name: check.passed for check in inspection.checks}


@pytest.fixture(scope="module")
def animated_video(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("remotion_good") / "out" / "video.mp4"
    _render(path, LAVFI_ANIMATED)
    return path


@pytest.fixture(scope="module")
def black_video(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("remotion_black") / "out" / "video.mp4"
    _render(path, LAVFI_BLACK)
    return path


def _workdir_with(video: Path, tmp_path: Path) -> Path:
    target = tmp_path / "out" / "video.mp4"
    target.parent.mkdir(parents=True)
    shutil.copy(video, target)
    _write_source(tmp_path)
    return tmp_path


# --- Saf kısımlar -----------------------------------------------------------


def test_parse_probe_reads_duration_size_and_fractional_fps():
    output = json.dumps(
        {
            "streams": [
                {"width": 1920, "height": 1080, "r_frame_rate": "30000/1001", "duration": "10.0"}
            ],
            "format": {"duration": "10.05"},
        }
    )
    probe = remotion.parse_probe(output)
    assert (probe.width, probe.height) == (1920, 1080)
    assert probe.fps == pytest.approx(29.97, abs=0.01)
    assert probe.duration_s == pytest.approx(10.0)


def test_parse_probe_falls_back_to_container_duration():
    output = json.dumps(
        {
            "streams": [{"width": 640, "height": 360, "r_frame_rate": "30/1"}],
            "format": {"duration": "4.5"},
        }
    )
    assert remotion.parse_probe(output).duration_s == pytest.approx(4.5)


def test_parse_probe_rejects_output_without_video_stream():
    with pytest.raises(ValueError, match="video akışı yok"):
        remotion.parse_probe(json.dumps({"streams": []}))


def test_luminance_variance_is_zero_for_single_color_frame():
    assert _pixels.luminance_variance(_png((0, 0, 0))) == 0.0


def test_luminance_variance_is_positive_for_two_tone_frame():
    buffer = io.BytesIO()
    image = Image.new("RGB", (64, 64), (0, 0, 0))
    image.paste((255, 255, 255), (0, 0, 32, 64))
    image.save(buffer, format="PNG")
    assert _pixels.luminance_variance(buffer.getvalue()) > 1000


def test_changed_pixel_ratio_separates_identical_and_different_frames():
    black = _png((0, 0, 0))
    assert _pixels.changed_pixel_ratio(black, black) == 0.0
    assert _pixels.changed_pixel_ratio(black, _png((255, 0, 0))) == 1.0
    assert _pixels.changed_pixel_ratio(black, _png((0, 0, 0), (32, 32))) == 1.0


def test_css_motion_usage_detects_transition_animation_and_tailwind():
    assert "transition:" in remotion.find_css_motion_usage("style={{transition: 'all 1s'}}")
    assert "animation:" in remotion.find_css_motion_usage("const s = `animation: spin 1s`")
    assert "tailwind animate-" in remotion.find_css_motion_usage('className="animate-spin"')
    assert "tailwind transition-*" in remotion.find_css_motion_usage('className="transition-all"')
    assert "@keyframes" in remotion.find_css_motion_usage("`@keyframes x {}`")


def test_css_motion_usage_ignores_comments_and_frame_based_code():
    assert remotion.find_css_motion_usage("// transition: yok\n" + GOOD_SOURCE) == ()
    assert remotion.find_css_motion_usage("/* animation: x */ const a = 1;") == ()


def test_area_declares_required_executables_and_timeout():
    assert remotion.AREA.name == "remotion"
    assert remotion.AREA.timeout_s == 5400
    assert remotion.AREA.required_executables == ("node", "npx", "ffprobe", "ffmpeg")


# --- Çıktı yok --------------------------------------------------------------


def test_missing_video_fails_video_checks_without_invalid_reason(tmp_path):
    _write_source(tmp_path)
    inspection = remotion.inspect(tmp_path, {})
    assert inspection.invalid_reason == ""
    results = _by_name(inspection)
    assert not results["out/video.mp4 var"]
    assert not results["fps 30"]
    assert results["useCurrentFrame kullanılıyor"]
    assert not inspection.all_passed


def test_missing_source_fails_source_checks(tmp_path):
    inspection = remotion.inspect(tmp_path, {})
    results = _by_name(inspection)
    assert not results["useCurrentFrame kullanılıyor"]
    assert not results["src'de CSS transition/animation kullanımı yok"]


# --- Gerçek video (ffmpeg) --------------------------------------------------


@needs_ffmpeg
def test_good_video_and_source_pass_all_checks(animated_video, tmp_path):
    workdir = _workdir_with(animated_video, tmp_path)
    inspection = remotion.inspect(workdir, {})
    failed = [f"{c.name}: {c.detail}" for c in inspection.checks if not c.passed]
    assert failed == []
    assert inspection.all_passed


@needs_ffmpeg
def test_black_video_fails_blank_and_distinct_frame_checks(black_video, tmp_path):
    workdir = _workdir_with(black_video, tmp_path)
    results = _by_name(remotion.inspect(workdir, {}))
    assert results["süre 10±0.5 sn"]
    assert not results["örnek kareler boş değil"]
    assert not results["örnek kareler birbirinden farklı"]


@needs_ffmpeg
def test_wrong_spec_video_fails_duration_size_and_fps(tmp_path):
    _render(tmp_path / "out" / "video.mp4", LAVFI_WRONG_SPEC)
    _write_source(tmp_path)
    results = _by_name(remotion.inspect(tmp_path, {}))
    assert not results["süre 10±0.5 sn"]
    assert not results["1920x1080"]
    assert not results["fps 30"]


@needs_ffmpeg
def test_corrupt_video_fails_checks_instead_of_invalid(tmp_path):
    target = tmp_path / "out" / "video.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"bu bir video degil")
    _write_source(tmp_path)
    inspection = remotion.inspect(tmp_path, {})
    assert inspection.invalid_reason == ""
    assert not _by_name(inspection)["fps 30"]


@needs_ffmpeg
def test_css_animation_in_source_fails_lint_check(animated_video, tmp_path):
    workdir = _workdir_with(animated_video, tmp_path)
    _write_source(workdir, GOOD_SOURCE + "\nconst bad = {transition: 'opacity 1s'};\n")
    results = _by_name(remotion.inspect(workdir, {}))
    assert not results["src'de CSS transition/animation kullanımı yok"]
    assert results["useCurrentFrame kullanılıyor"]


@needs_ffmpeg
def test_source_without_use_current_frame_fails_check(animated_video, tmp_path):
    workdir = _workdir_with(animated_video, tmp_path)
    _write_source(workdir, "export const Intro = () => <div>Merhaba</div>;\n")
    assert not _by_name(remotion.inspect(workdir, {}))["useCurrentFrame kullanılıyor"]
