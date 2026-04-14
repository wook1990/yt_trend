"""src/exporter.py — 수집 결과 저장"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def save(videos: list[dict[str, Any]], output_path: Path | str, fmt: str = "json") -> Path:
    """
    영상 목록을 파일로 저장.

    Args:
        videos:      저장할 영상 목록
        output_path: 저장 경로 (확장자 없으면 fmt에 따라 자동 추가)
        fmt:         "json" | "csv"

    Returns:
        실제 저장된 파일 경로
    """
    path = Path(output_path)
    if path.suffix == "":
        path = path.with_suffix(f".{fmt}")

    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        _save_json(videos, path)
    elif fmt == "csv":
        _save_csv(videos, path)
    else:
        raise ValueError(f"지원하지 않는 포맷: {fmt}")

    return path


def _save_json(videos: list[dict], path: Path) -> None:
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(videos),
        "videos": videos,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_csv(videos: list[dict], path: Path) -> None:
    if not videos:
        path.write_text("", encoding="utf-8")
        return

    fields = ["id", "title", "channel", "view_count", "like_count",
              "duration", "upload_date", "region", "fetched_at", "url"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(videos)
