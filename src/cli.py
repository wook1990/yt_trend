"""src/cli.py — 커맨드라인 인터페이스"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from dotenv import load_dotenv

load_dotenv(ROOT / "config" / ".env")


def load_settings() -> dict:
    cfg_path = ROOT / "config" / "settings.yaml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def cmd_fetch(args: argparse.Namespace, cfg: dict) -> None:
    fetch_cfg = cfg.get("fetch", {})
    region   = args.region   or fetch_cfg.get("default_region", "KR")
    category = args.category if args.category is not None else fetch_cfg.get("default_category", 0)
    limit    = args.limit    or fetch_cfg.get("default_limit", 50)
    provider = args.provider or fetch_cfg.get("default_provider", "ytdlp")

    print(f"[fetch] region={region} category={category} limit={limit} provider={provider}")

    if provider in ("ytdlp", "innertube"):
        from src.fetcher.ytdlp import fetch
    elif provider == "yt_api":
        from src.fetcher.yt_api import fetch
    else:
        print(f"[fetch] 알 수 없는 provider: {provider}", file=sys.stderr)
        sys.exit(1)

    videos = fetch(region=region, category=category, limit=limit)
    print(f"[fetch] 수집 완료: {len(videos)}개")

    # 필터 적용
    if args.min_views or args.max_duration or args.keyword:
        from src.filter import apply
        before = len(videos)
        videos = apply(
            videos,
            min_views=args.min_views,
            max_duration=args.max_duration,
            keyword=args.keyword,
        )
        print(f"[filter] {before} → {len(videos)}개")

    # 출력
    if args.output:
        from src.exporter import save
        out_fmt = cfg.get("output", {}).get("format", "json")
        saved = save(videos, args.output, fmt=out_fmt)
        print(f"[export] 저장: {saved}")
    else:
        # 터미널 출력 (상위 10개 요약)
        print()
        for i, v in enumerate(videos[:10], 1):
            views = f"{v.get('view_count', 0):,}" if v.get("view_count") else "-"
            print(f"  {i:2}. [{views}회] {v['title'][:60]}  —  {v['channel']}")
        if len(videos) > 10:
            print(f"  ... 외 {len(videos) - 10}개")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt_trending",
        description="YouTube 인기 급상승 동영상 수집",
    )
    sub = parser.add_subparsers(dest="command")

    # fetch 서브커맨드
    p_fetch = sub.add_parser("fetch", help="인기 급상승 영상 수집")
    p_fetch.add_argument("--region",   default=None, help="국가 코드 (기본: KR)")
    p_fetch.add_argument("--category", default=None, type=int, help="카테고리 ID (기본: 0=전체)")
    p_fetch.add_argument("--limit",    default=None, type=int, help="수집 수 (기본: 50)")
    p_fetch.add_argument("--provider", default=None, choices=["innertube", "yt_api"], help="데이터 소스 (기본: innertube)")
    p_fetch.add_argument("--output",   default=None, help="저장 경로 (미지정 시 터미널 출력)")
    p_fetch.add_argument("--min-views",    dest="min_views",    default=None, type=int)
    p_fetch.add_argument("--max-duration", dest="max_duration", default=None, type=int, help="초 단위")
    p_fetch.add_argument("--keyword",      default=None, help="제목/설명 키워드 필터")

    return parser


def main() -> None:
    cfg = load_settings()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch":
        cmd_fetch(args, cfg)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
