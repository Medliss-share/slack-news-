"""
HTTP 取得の共通ユーティリティ。

特定ドメインは証明書が hostname mismatch 等でサーバ側設定不備のため、
それらに限って SSL 検証を緩めた urlopen を提供する。
他モジュールはこの関数経由でアクセスすることで、ドメイン個別事情を1か所で管理できる。
"""
from __future__ import annotations

import logging
import os
import ssl
import urllib.request
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# SSL 証明書の hostname が一致しないことが既知のドメイン。
# 例: ht-watch.com は MovableType.io のワイルドカード証明書(*.movabletype.io)で
# サーブされているため hostname mismatch が発生する（サーバ側の設定の問題で修正不可）。
DEFAULT_SSL_UNVERIFIED_DOMAINS: tuple[str, ...] = ("ht-watch.com",)


def _ssl_unverified_domains() -> tuple[str, ...]:
    env_val = os.environ.get("SSL_UNVERIFIED_DOMAINS", "").strip()
    if not env_val:
        return DEFAULT_SSL_UNVERIFIED_DOMAINS
    return tuple(d.strip().lower() for d in env_val.split(",") if d.strip())


def needs_unverified_ssl(url: str) -> bool:
    """URL が SSL 検証緩和が必要なドメインかを判定する。"""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return False
    if not host:
        return False
    for domain in _ssl_unverified_domains():
        if host == domain or host.endswith("." + domain):
            return True
    return False


_UNVERIFIED_SSL_CONTEXT = ssl._create_unverified_context()


def urlopen(url, timeout: int = 10, request: urllib.request.Request | None = None):
    """通常は標準の SSL 検証、問題ドメインのみ unverified context で urlopen する。

    url か request のいずれかを渡す。Request オブジェクトの場合は、その full_url を
    ドメイン判定に使う。
    """
    target = request if request is not None else url
    check_url = request.full_url if request is not None else url

    if needs_unverified_ssl(check_url):
        logger.debug("Opening %s with unverified SSL context", check_url)
        return urllib.request.urlopen(target, timeout=timeout, context=_UNVERIFIED_SSL_CONTEXT)
    return urllib.request.urlopen(target, timeout=timeout)
