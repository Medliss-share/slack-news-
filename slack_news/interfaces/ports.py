"""ユースケースが依存するポート（抽象）。具象は infrastructure に置く。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class SlackNotifier(Protocol):
    def post(self, webhook_url: str, message: str, *, timeout: int) -> bool:
        """Slack Incoming Webhook へ投稿する。成功時 True。"""


class SentUrlRepository(Protocol):
    def load(self, path: Path) -> dict[str, str]:
        """送信済み URL のマップを読み込む。"""

    def save(self, path: Path, urls: dict[str, str]) -> None:
        """送信済み URL のマップを保存する。"""
