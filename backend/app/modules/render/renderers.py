"""Render backends (ADR-0017): the Remotion Node CLI, a deterministic stub for tests, or disabled."""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings

log = logging.getLogger("app.render")


class RenderError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(code)
        self.code = code[:80]
        self.message = message[:300]


@dataclass
class RenderResult:
    renderer: str
    poster: bytes
    video: bytes | None
    width: int
    height: int
    duration_s: float | None


ProgressFn = Callable[[float], None]


class StubRenderer:
    """Tests only: a real PNG poster (title text) and a placeholder (not playable) video file."""

    name = "stub"

    def render(
        self, composition: str, props: dict[str, Any], output: str, progress: ProgressFn
    ) -> RenderResult:
        from PIL import Image, ImageDraw

        im = Image.new("RGB", (1280, 720), (251, 246, 236))
        ImageDraw.Draw(im).text(
            (40, 40), f"{composition}: {props['branding']['title']}"[:120], fill=(31, 26, 23)
        )
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        progress(0.5)
        video = b"\x00\x00\x00\x18ftypisom" + b"stub-render" * 10 if output == "mp4" else None
        progress(1.0)
        return RenderResult("stub", buf.getvalue(), video, 1280, 720, 1.0 if video else None)


class RemotionRenderer:
    """Runs ``renderer/scripts/render.mjs`` (pre-built bundle) in a subprocess with a timeout."""

    def __init__(self) -> None:
        s = get_settings()
        self.dir = Path(s.renderer_dir).resolve()
        self.node = s.renderer_node
        self.timeout = s.render_timeout_seconds
        self.browser = s.renderer_browser_executable
        self.name = "remotion"
        pkg = self.dir / "package.json"
        if pkg.exists():
            deps = json.loads(pkg.read_text()).get("dependencies", {})
            self.name = f"remotion@{deps.get('remotion', '?')}"

    def render(
        self, composition: str, props: dict[str, Any], output: str, progress: ProgressFn
    ) -> RenderResult:
        script = self.dir / "scripts" / "render.mjs"
        if not script.exists() or not (self.dir / "build" / "bundle" / "index.html").exists():
            raise RenderError("renderer_not_installed", "The renderer bundle is not built on this worker")
        with tempfile.TemporaryDirectory(prefix="vsh-render-") as tmp:
            payload = Path(tmp) / "payload.json"
            # the payload holds family data: readable by this process only, removed with the directory
            fd = os.open(payload, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"composition": composition, "props": props}, f, ensure_ascii=False)
            env = {k: v for k, v in os.environ.items() if not k.startswith("VSH_")}  # no app secrets
            if self.browser:
                env["REMOTION_BROWSER_EXECUTABLE"] = self.browser
            cmd = [self.node, str(script), "--payload", str(payload), "--out-dir", tmp, "--output", output]
            proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                cmd, cwd=self.dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            result: dict[str, Any] | None = None
            try:
                assert proc.stdout is not None  # noqa: S101 - Popen with PIPE
                for line in proc.stdout:
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    if "progress" in msg:
                        progress(float(msg["progress"]))
                    elif "result" in msg:
                        result = msg["result"]
                proc.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise RenderError("render_timeout", "Rendering took too long")
            stderr = (proc.stderr.read() if proc.stderr else "").strip().splitlines()
            if proc.returncode != 0 or result is None:
                code = (
                    stderr[-1]
                    if stderr and len(stderr[-1]) < 60 and " " not in stderr[-1]
                    else "render_failed"
                )
                # never log the payload or the renderer's full output (it can quote names)
                log.warning("render failed: code=%s exit=%s", code, proc.returncode)
                raise RenderError(code, "The renderer could not produce the export")
            poster = Path(result["poster"]).read_bytes()
            video = Path(result["video"]).read_bytes() if result.get("video") else None
            frames, fps = int(result.get("durationInFrames") or 0), int(result.get("fps") or 30)
            return RenderResult(
                self.name,
                poster,
                video,
                int(result.get("width") or 1280),
                int(result.get("height") or 720),
                round(frames / fps, 2) if video and fps else None,
            )


def get_renderer() -> StubRenderer | RemotionRenderer:
    backend = get_settings().render_backend
    if backend == "stub":
        return StubRenderer()
    if backend == "remotion":
        return RemotionRenderer()
    raise RenderError("render_unavailable", "Animated exports are not enabled on this server")
