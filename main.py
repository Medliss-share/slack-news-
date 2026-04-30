"""CLI エントリ。処理本体は `slack_news.application.news_delivery`（skills.md 参照）。"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import config
from slack_news.application.news_delivery import NewsDeliveryUseCase
from slack_news.infrastructure.adapters import FileSentUrlRepository, SlackWebhookNotifier


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s %(levelname)s %(name)s - %(message)s"
    if config.LOG_FILE:
        handlers = [
            logging.StreamHandler(),
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        ]
        logging.basicConfig(level=level, format=log_format, handlers=handlers)
    else:
        logging.basicConfig(level=level, format=log_format)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="医療×ITニュースをフィルタしてSlackに投稿します。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Slack に送らず標準出力にメッセージを表示する",
    )
    parser.add_argument(
        "--storage-path",
        type=Path,
        help=f"配信済みURL保存先 (デフォルト: {config.SENT_URLS_PATH})",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        help=f"1回の投稿件数上限 (デフォルト: {config.MAX_ARTICLES_PER_POST})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="詳細ログを有効にする",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="手動実行モード（送信済みURLチェックをスキップし、5件に制限）",
    )
    parser.add_argument(
        "--category",
        default="all",
        help=(
            "配信カテゴリ（カンマ区切り複数指定可）: "
            "healthtech=ヘルステック技術動向, general_tech=一般IT技術動向, "
            "competitor=競合動向, conference=カンファレンス/イベント, "
            "all=全件ソース別まとめ "
            "(tech は healthtech のエイリアス) "
            "(例: --category competitor,healthtech,conference) (default: all)"
        ),
    )
    parser.add_argument(
        "--webhook",
        choices=["default", "a", "b"],
        default="default",
        help=(
            "配信先 Slack Webhook を選択: "
            "a=SLACK_WEBHOOK_URL_A（ヘルステック＝競合/ヘルステック技術動向/ヘルステックカンファレンス, 朝）, "
            "b=SLACK_WEBHOOK_URL_B（一般IT技術動向+カンファレンス/イベント, 夜）, "
            "default=SLACK_WEBHOOK_URL (default: default)"
        ),
    )
    return parser.parse_args()


def run(
    dry_run: bool = False,
    storage_path: Path | None = None,
    max_items: int | None = None,
    manual: bool = False,
    category: str = "all",
    webhook: str = "default",
) -> int:
    """後方互換用。ユースケースへ委譲する。"""
    use_case = NewsDeliveryUseCase(
        slack=SlackWebhookNotifier(),
        sent_urls=FileSentUrlRepository(),
    )
    return use_case.run(
        dry_run=dry_run,
        storage_path=storage_path,
        max_items=max_items,
        manual=manual,
        category=category,
        webhook=webhook,
    )


if __name__ == "__main__":
    args = parse_args()
    configure_logging(args.verbose)
    exit_code = run(
        dry_run=args.dry_run,
        storage_path=args.storage_path,
        max_items=args.max_items,
        manual=args.manual,
        category=args.category,
        webhook=args.webhook,
    )
    raise SystemExit(exit_code)
