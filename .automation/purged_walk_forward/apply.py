from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    if new in content:
        return
    if old not in content:
        raise RuntimeError(f"patch anchor missing in {path}: {old!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> None:
    replace_once(
        "config/strategy.json",
        '  "global_model_research": {\n    "embargo_sessions": 0\n  },\n',
        '  "global_model_research": {\n'
        '    "version": "global-model-research-v0.2.0-purged-walk-forward",\n'
        '    "embargo_sessions": 0,\n'
        '    "walk_forward_folds": 4,\n'
        '    "walk_forward_test_sessions": 20,\n'
        '    "walk_forward_min_train_sessions": 150\n'
        '  },\n',
    )
    replace_once(
        "backend/app/services/global_model_research_service.py",
        '                "backend": backend,\n                "split": {\n',
        '                "backend": backend,\n'
        '                "research_version": research_cfg.get("version", "global-model-research-v0.2.0-purged-walk-forward"),\n'
        '                "split": {\n',
    )


if __name__ == "__main__":
    main()
