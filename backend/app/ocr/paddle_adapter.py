from __future__ import annotations

import importlib
import json
import multiprocessing
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from app.ocr.contracts import OCRLine, OCRResult, OCRUnavailable
from app.ocr.image_validation import ValidatedImage, validate_image_artifact


def _manifest_relative(value: object, component: str) -> str | None:
    if not isinstance(value, str) or "\\" in value or not value or len(value) > 128:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or path.parts[0:1] != (component,) or len(path.parts) != 2:
        return None
    if path.name not in {"inference.pdmodel", "inference.pdiparams", "inference.pdparams"}:
        return None
    return value


def _safe_box(value: object) -> tuple[tuple[float, float], ...] | None:
    """Convert Paddle rectangle/polygon boxes to bounded four-point boxes."""
    try:
        if hasattr(value, "tolist"):
            value = value.tolist()
        points = list(value)  # type: ignore[arg-type]
        if len(points) == 4 and all(isinstance(point, (list, tuple)) and len(point) == 2 for point in points):
            result = tuple((float(point[0]), float(point[1])) for point in points)
        elif len(points) == 4 and all(isinstance(point, (int, float)) for point in points):
            left, top, right, bottom = (float(item) for item in points)
            result = ((left, top), (right, top), (right, bottom), (left, bottom))
        else:
            return None
        if any(not (0 <= x <= 1_000_000 and 0 <= y <= 1_000_000) for x, y in result):
            return None
        return result
    except (TypeError, ValueError, OverflowError):
        return None


def _paddle_worker(conn: Any, model_dir: str, payload: bytes) -> None:
    """Spawn-safe worker. Only bounded primitive result data crosses IPC."""
    try:
        adapter = PaddleOCRAdapter(model_dir=model_dir)
        engine = adapter._load_engine()
        if isinstance(engine, OCRUnavailable):
            conn.send({"status": "unavailable", "reason": engine.reason.value})
            return
        result = engine.predict(payload)
        lines: list[dict[str, Any]] = []
        total_chars = 0
        page_count = 0
        raw_count = 0
        for page in result or ():
            page_count += 1
            if page_count > 64:
                conn.send({"status": "unavailable", "reason": "output_limit_exceeded"})
                return
            page_payload = page if isinstance(page, dict) else getattr(page, "json", lambda: {})()
            texts = page_payload.get("rec_texts", ()) if isinstance(page_payload, dict) else ()
            scores = page_payload.get("rec_scores", ()) if isinstance(page_payload, dict) else ()
            boxes = page_payload.get("rec_boxes", page_payload.get("rec_polys", ())) if isinstance(page_payload, dict) else ()
            for index, text in enumerate(texts):
                raw_count += 1
                if raw_count > 4096:
                    conn.send({"status": "unavailable", "reason": "output_limit_exceeded"})
                    return
                if not isinstance(text, str) or not text.strip():
                    continue
                cleaned = text.strip()
                total_chars += len(cleaned)
                if len(lines) >= 512 or total_chars > 100_000:
                    conn.send({"status": "unavailable", "reason": "output_limit_exceeded"})
                    return
                score = scores[index] if index < len(scores) else 0.0
                line = {"text": cleaned[:2000], "confidence": float(score)}
                if index < len(boxes):
                    points = _safe_box(boxes[index])
                    if points is not None:
                        line["box"] = {"points": points}
                lines.append(line)
        conn.send({"status": "completed", "lines": lines})
    except Exception:
        conn.send({"status": "unavailable", "reason": "engine_unavailable"})
    finally:
        conn.close()


class PaddleOCRAdapter:
    """Local-only PaddleOCR adapter.

    Paddle packages are deliberately imported only when ``recognize`` is used.
    A model directory is mandatory so this adapter can never fall back to a
    package-managed or network-downloaded model.
    """

    backend_name = "local_paddle"

    def __init__(
        self,
        model_dir: str | Path | None = None,
        *,
        settings: Any | None = None,
        model: str = "local",
        version: str = "qualified",
        timeout_seconds: float | None = None,
        max_bytes: int = 10 * 1024 * 1024,
        max_width: int = 12_000,
        max_height: int = 12_000,
        max_pixels: int = 40_000_000,
        worker_target: Any = _paddle_worker,
    ) -> None:
        # Accept Settings positionally as a convenience for future C2 wiring,
        # without importing the settings module (and its environment) here.
        if settings is not None:
            model_dir = settings.ocr_local_model_dir
            timeout_seconds = settings.ocr_timeout_seconds
            max_bytes = settings.ocr_max_bytes
            max_width = settings.ocr_max_width
            max_height = settings.ocr_max_height
            max_pixels = settings.ocr_max_pixels
        if model_dir is not None and hasattr(model_dir, "ocr_local_model_dir"):
            model_dir = model_dir.ocr_local_model_dir
        self.model_dir = Path(model_dir).expanduser() if model_dir is not None else None
        self.model = model
        self.version = version
        self._engine: Any | None = None
        self.timeout_seconds = timeout_seconds
        self.hard_timeout_supported = True
        self.worker_target = worker_target
        self.max_bytes = max_bytes
        self.max_width = max_width
        self.max_height = max_height
        self.max_pixels = max_pixels

    def _unavailable(self, reason: str) -> OCRUnavailable:
        # Reasons are fixed identifiers, not arbitrary exception messages.
        allowed = {
            "model_directory_missing",
            "model_directory_unqualified",
            "paddleocr_package_missing",
            "paddle_package_missing",
            "engine_unavailable",
            "output_limit_exceeded",
            "timeout",
            "invalid_image",
            "worker_cleanup_failed",
        }
        # Fixed metadata prevents caller-controlled model/version strings from
        # turning an unavailable result into a validation error or log payload.
        return OCRUnavailable(
            reason=reason if reason in allowed else "engine_unavailable",
            backend="local_paddle",
            model="unavailable",
            version="unavailable",
        )

    def _run_worker(self, payload: bytes) -> dict[str, Any]:
        parent_conn = None
        child_conn = None
        process = None
        started = False
        response: dict[str, Any] = {"status": "unavailable", "reason": "engine_unavailable"}
        try:
            ctx = multiprocessing.get_context("spawn")
            parent_conn, child_conn = ctx.Pipe(duplex=False)
            process = ctx.Process(
                target=self.worker_target,
                args=(child_conn, str(self.model_dir.resolve()), payload),
            )
            process.start()
            started = True
            child_conn.close()
            child_conn = None
            timeout = max(float(self.timeout_seconds if self.timeout_seconds is not None else 60.0), 0.001)
            if parent_conn.poll(timeout):
                value = parent_conn.recv()
                if isinstance(value, dict):
                    response = value
            else:
                response = {"status": "unavailable", "reason": "timeout"}
        except (ImportError, OSError, ValueError, TypeError, EOFError, AttributeError, AssertionError):
            response = {"status": "unavailable", "reason": "engine_unavailable"}
        finally:
            if child_conn is not None:
                try:
                    child_conn.close()
                except (OSError, ValueError):
                    pass
            if process is not None and started:
                try:
                    if process.is_alive():
                        process.join(timeout=0.05)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=0.25)
                    if process.is_alive() and hasattr(process, "kill"):
                        process.kill()
                        process.join(timeout=0.25)
                    if process.is_alive():
                        response = {"status": "unavailable", "reason": "worker_cleanup_failed"}
                except (OSError, ValueError, AssertionError):
                    response = {"status": "unavailable", "reason": "worker_cleanup_failed"}
                finally:
                    try:
                        if not process.is_alive():
                            process.close()
                    except (OSError, ValueError, AssertionError):
                        pass
            if parent_conn is not None:
                try:
                    parent_conn.close()
                except (OSError, ValueError):
                    pass
        return response

    def _qualified_model_dir(self) -> dict[str, Path] | None:
        if self.model_dir is None or not self.model_dir.is_dir() or self.model_dir.is_symlink():
            return None
        try:
            root = self.model_dir.resolve(strict=True)
        except OSError:
            return None
        manifest_path = next(
            (root / name for name in ("ocr_manifest.json", "manifest.json") if (root / name).is_file()),
            None,
        )
        if manifest_path is None or manifest_path.is_symlink():
            return None
        try:
            if manifest_path.stat().st_size > 64 * 1024:
                return None
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(manifest, dict) or set(manifest) - {"version", "det", "rec", "cls"}:
            return None
        if not isinstance(manifest.get("version"), str) or manifest["version"] != "paddle-local-v1":
            return None
        allowed_root_entries = {manifest_path.name, "det", "rec"}
        if "cls" in manifest:
            allowed_root_entries.add("cls")
        try:
            if any(entry.is_symlink() or entry.name not in allowed_root_entries for entry in root.iterdir()):
                return None
        except OSError:
            return None
        component_dirs: dict[str, Path] = {}
        for component in ("det", "rec"):
            item = manifest.get(component)
            if not isinstance(item, dict) or set(item) != {"files"} or not isinstance(item["files"], list) or not item["files"] or len(item["files"]) > 8:
                return None
            resolved_files: list[Path] = []
            total_size = 0
            for descriptor in item["files"]:
                if not isinstance(descriptor, dict) or set(descriptor) != {"path", "size", "sha256"}:
                    return None
                relative = descriptor["path"]
                relative = _manifest_relative(descriptor["path"], component)
                if relative is None:
                    return None
                if not isinstance(descriptor["size"], int) or descriptor["size"] <= 0 or descriptor["size"] > 256 * 1024 * 1024:
                    return None
                digest = descriptor["sha256"]
                if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
                    return None
                raw_candidate = root / relative
                if raw_candidate.is_symlink():
                    return None
                candidate = raw_candidate.resolve()
                if not candidate.is_relative_to(root) or candidate.is_symlink() or not candidate.is_file():
                    return None
                try:
                    stat_size = candidate.stat().st_size
                    if stat_size <= 0 or stat_size != descriptor["size"] or sha256(candidate.read_bytes()).hexdigest().lower() != digest.lower():
                        return None
                except OSError:
                    return None
                total_size += stat_size
                if total_size > 512 * 1024 * 1024:
                    return None
                resolved_files.append(candidate)
            suffixes = {path.suffix.lower() for path in resolved_files}
            if not ({".pdiparams", ".pdparams"} & suffixes) or not ({".pdmodel", ".json", ".yml", ".yaml"} & suffixes):
                return None
            if len({path.parent for path in resolved_files}) != 1 or len(set(resolved_files)) != len(resolved_files):
                return None
            component_dirs[component] = resolved_files[0].parent
            expected = set(resolved_files)
            for actual in component_dirs[component].rglob("*"):
                if actual.is_symlink() or actual.is_dir() or (actual.is_file() and actual.resolve() not in expected):
                    return None
        optional = manifest.get("cls")
        if optional is not None:
            if not isinstance(optional, dict) or set(optional) != {"files"} or not isinstance(optional["files"], list):
                return None
            if len(optional["files"]) > 8:
                return None
            resolved_cls: list[Path] = []
            for descriptor in optional["files"]:
                if not isinstance(descriptor, dict) or set(descriptor) != {"path", "size", "sha256"}:
                    return None
                relative = descriptor["path"]
                relative = _manifest_relative(descriptor["path"], "cls")
                if relative is None:
                    return None
                if not isinstance(descriptor["size"], int) or descriptor["size"] <= 0 or descriptor["size"] > 256 * 1024 * 1024:
                    return None
                digest = descriptor["sha256"]
                if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
                    return None
                raw_candidate = root / relative
                if raw_candidate.is_symlink():
                    return None
                candidate = raw_candidate.resolve()
                if not candidate.is_relative_to(root) or candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size != descriptor["size"] or candidate.stat().st_size <= 0 or sha256(candidate.read_bytes()).hexdigest().lower() != digest.lower():
                    return None
                resolved_cls.append(candidate)
            if len(set(resolved_cls)) != len(resolved_cls):
                return None
            if optional["files"]:
                component_dirs["cls"] = (root / optional["files"][0]["path"]).resolve().parent
                expected_cls = set(resolved_cls)
                for actual in component_dirs["cls"].rglob("*"):
                    if actual.is_symlink() or actual.is_dir() or (actual.is_file() and actual.resolve() not in expected_cls):
                        return None
        return component_dirs

    def _load_engine(self) -> Any | OCRUnavailable:
        try:
            component_dirs = self._qualified_model_dir()
        except (ImportError, OSError, ValueError, TypeError):
            return self._unavailable("model_directory_unqualified")
        if component_dirs is None:
            reason = "model_directory_missing" if self.model_dir is None or not self.model_dir.is_dir() else "model_directory_unqualified"
            return self._unavailable(reason)
        try:
            paddleocr = importlib.import_module("paddleocr")
        except (ImportError, ModuleNotFoundError, OSError):
            return self._unavailable("paddleocr_package_missing")
        try:
            importlib.import_module("paddle")
        except (ImportError, ModuleNotFoundError, OSError):
            return self._unavailable("paddle_package_missing")
        try:
            # Explicit local paths are essential: no model name/default path is
            # supplied that could trigger an implicit download.
            kwargs = {
                "text_detection_model_dir": str(component_dirs["det"]),
                "text_recognition_model_dir": str(component_dirs["rec"]),
                "device": "cpu",
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
            }
            if "cls" in component_dirs:
                kwargs["textline_orientation_model_dir"] = str(component_dirs["cls"])
            self._engine = paddleocr.PaddleOCR(**kwargs)
        except Exception:
            return self._unavailable("engine_unavailable")
        return self._engine

    def recognize(self, image: bytes | ValidatedImage) -> OCRResult | OCRUnavailable:
        if isinstance(image, bytes):
            try:
                image = validate_image_artifact(
                    image,
                    max_bytes=self.max_bytes,
                    max_width=self.max_width,
                    max_height=self.max_height,
                    max_pixels=self.max_pixels,
                )
            except (ValueError, TypeError):
                return self._unavailable("invalid_image")
        if not isinstance(image, ValidatedImage):
            return self._unavailable("invalid_image")
        try:
            actual = validate_image_artifact(
                image.payload,
                max_bytes=self.max_bytes,
                max_width=self.max_width,
                max_height=self.max_height,
                max_pixels=self.max_pixels,
            ).metadata
            if actual != image.metadata:
                return self._unavailable("invalid_image")
        except (ValueError, TypeError):
            return self._unavailable("invalid_image")
        if self.model_dir is None:
            return self._unavailable("model_directory_missing")
        try:
            qualified = self._qualified_model_dir()
        except (ImportError, OSError, ValueError, TypeError):
            return self._unavailable("model_directory_unqualified")
        if qualified is None:
            return self._unavailable("model_directory_unqualified")
        try:
            response = self._run_worker(image.payload)
            if not isinstance(response, dict) or response.get("status") != "completed":
                return self._unavailable(str(response.get("reason", "engine_unavailable")) if isinstance(response, dict) else "engine_unavailable")
            lines = tuple(OCRLine(**item) for item in response.get("lines", ()))
            return OCRResult(
                lines=lines,
                backend=self.backend_name,
                model=self.model,
                version=self.version,
                processed_at=datetime.now(UTC),
            )
        except Exception:
            return self._unavailable("engine_unavailable")

    run = recognize
