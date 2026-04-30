"""Ports の具象実装（既存の notifier / storage を薄くラップ）。"""

from __future__ import annotations

from pathlib import Path

from notifier import post_message
from storage import load_sent_urls, save_sent_urls


class SlackWebhookNotifier:
    """Slack Incoming Webhook 経由の通知。"""

    def post(self, webhook_url: str, message: str, *, timeout: int) -> bool:
        return post_message(webhook_url, message, timeout=timeout)


class FileSentUrlRepository:
    """送信済み URL を JSON ファイルに保存するリポジトリ。"""

    def load(self, path: Path) -> dict[str, str]:
        return load_sent_urls(path)

    def save(self, path: Path, urls: dict[str, str]) -> None:
        save_sent_urls(urls, path)
