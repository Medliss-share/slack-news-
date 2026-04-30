"""ソース表示名（ドメイン知識に近い定数・純関数）。"""

from __future__ import annotations


def source_display_name(link: str) -> str:
    """URL から人向けのソース名を返す（Slack 表示・ログ用）。"""
    if "prtimes.jp" in link:
        return "PR TIMES"
    if "news.google.com" in link:
        return "Google News"
    if "medicaltech-news.com" in link:
        return "医療テックニュース"
    if "ht-watch.com" in link:
        return "ヘルステックウォッチ"
    if "connpass.com" in link:
        return "connpass"
    if "publickey1.jp" in link or "publickey2.jp" in link:
        return "Publickey"
    if "itmedia.co.jp" in link:
        return "ITmedia"
    if "zdnet" in link:
        return "ZDNet Japan"
    if "codezine.jp" in link:
        return "CodeZine"
    return "その他"
