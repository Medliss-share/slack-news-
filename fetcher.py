from __future__ import annotations

import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, List

from httpclient import urlopen as _urlopen

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    link: str
    published: str | None = None
    summary: str | None = None
    published_at: datetime | None = None
    matched_keywords: list[str] | None = None  # マッチしたキーワードのリスト
    categories: list[str] | None = None  # 分類されたカテゴリ（tech/competitor/conference）
    is_event: bool = False  # connpass 等の開催予定イベント（医療×ITフィルタと time_range をバイパス）
    event_start_at: datetime | None = None  # 開催日時（イベントの場合）
    event_location: str | None = None  # 開催場所文字列（表示用）
    is_general_tech: bool = False  # 一般IT ソース由来の記事（医療×IT フィルタをバイパス）
    is_healthtech_priority: bool = False  # ヘルステック優先ソース由来（Channel A の医療DXゲートをバイパス）


def _fetch_description_from_page(link: str, timeout: int) -> str | None:
    """記事ページからdescriptionを取得する。"""
    import re
    import html
    
    try:
        # Google NewsのリダイレクトURLの場合は、リダイレクト先を取得
        if "news.google.com/rss/articles" in link:
            # リダイレクト先のURLを取得
            req = urllib.request.Request(link)
            req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
            with _urlopen(link, timeout=timeout, request=req) as response:
                actual_url = response.geturl()
                link = actual_url

        with _urlopen(link, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            text = response.read().decode(charset, errors="replace")
        
        # meta description を探す
        desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', text, re.IGNORECASE)
        if not desc_match:
            # og:description を探す
            desc_match = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', text, re.IGNORECASE)
        
        if desc_match:
            description = desc_match.group(1)
            # HTMLエンティティをデコード
            description = html.unescape(description)
            # HTMLタグを除去
            description = re.sub(r'<[^>]+>', '', description)
            description = description.strip()
            
            # サイト全体の説明文でないかチェック
            if len(description) > 20 and "クリッピングサイト" not in description:
                return description
    except Exception:
        pass
    
    return None


def fetch_all_feeds(feed_urls: Iterable[str], timeout: int = 10) -> List[Article]:
    """複数の RSS/Atom フィードをまとめて取得する。"""
    articles: list[Article] = []
    for url in feed_urls:
        try:
            fetched = fetch_feed(url, timeout=timeout)
            logger.info("Fetched %d articles from %s", len(fetched), url)
            
            # summaryが空または短い場合、記事ページからdescriptionを取得
            for article in fetched:
                if not article.summary or len(article.summary.strip()) < 50:
                    page_description = _fetch_description_from_page(article.link, timeout)
                    if page_description:
                        article.summary = page_description
                        logger.debug("Fetched description from page for: %s", article.title[:50])
            
            articles.extend(fetched)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to fetch %s: %s", url, exc)
    return articles


def fetch_feed(feed_url: str, timeout: int = 10) -> List[Article]:
    """単一フィードを取得し、Article のリストに変換する。"""
    with _urlopen(feed_url, timeout=timeout) as response:
        content_type = response.headers.get_content_charset() or "utf-8"
        raw = response.read()
        text = raw.decode(content_type, errors="replace")

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        logger.warning("XML parse error on %s: %s", feed_url, exc)
        return []

    # RSS 2.0: <item> / RSS 1.0 (RDF): <item> に名前空間が付くケースがある
    entries = root.findall(".//item") or root.findall(".//{*}item")
    if not entries:
        # Atom 形式対応
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    articles = []
    for entry in entries:
        article = _element_to_article(entry)
        # タイトルとリンクが有効な記事のみを追加
        if article.title and article.title != "(no title)" and article.link:
            articles.append(article)
    
    return articles


def _element_to_article(elem: ET.Element) -> Article:
    import html
    import re
    
    title = _text(elem, "title")
    link = _link(elem)
    
    # 公開日の取得（複数の形式に対応）
    published = (
        _text(elem, "pubDate")
        or _text(elem, "published")
        or _text(elem, "updated")
        or _text(elem, "date")  # RSS 1.0形式
        or _text(elem, "{http://purl.org/dc/elements/1.1/}date")  # Dublin Core date
        or None
    )
    
    # 概要の取得（複数の形式に対応）
    summary = (
        _text(elem, "description")
        or _text(elem, "summary")
        or _text(elem, "{http://www.w3.org/2005/Atom}summary")
        or None
    )
    
    # summaryからHTMLタグを除去（RSSフィードにHTMLが含まれている場合がある）
    if summary:
        # HTMLタグを除去
        summary = re.sub(r'<[^>]+>', '', summary)
        # HTMLエンティティをデコード
        summary = html.unescape(summary)
        summary = summary.strip()
        # 空になった場合はNoneにする
        if not summary:
            summary = None
    
    published_at = parse_datetime(published) if published else None
    return Article(
        title=title or "(no title)",
        link=link,
        published=published,
        summary=summary,
        published_at=published_at,
    )


def _text(elem: ET.Element, tag: str) -> str:
    # 通常のタグを探す
    child = elem.find(tag)
    if child is not None and child.text is not None:
        return child.text.strip()
    
    # 名前空間付きタグも探す（RSS 1.0/RDF形式対応）
    # すべての子要素を検索して、タグ名が一致するものを探す
    tag_name = tag.split('}')[-1] if '}' in tag else tag
    for child in elem.iter():
        # タグ名が一致するかチェック（名前空間を無視）
        if child.tag.endswith(f'}}{tag_name}') or child.tag == tag_name:
            if child.text is not None:
                return child.text.strip()
    
    return ""


def _link(elem: ET.Element) -> str:
    # RSS: <link>URL</link>
    link_text = _text(elem, "link")
    if link_text:
        return link_text
    
    # 名前空間付きlinkタグも探す（RSS 1.0/RDF形式対応）
    # すべての子要素を検索して、linkタグを探す
    for child in elem.iter():
        tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag_name == "link":
            # RSS 1.0ではlinkタグのtextがURL
            if child.text and child.text.strip():
                return child.text.strip()
            # Atom形式: <link href="..."/>
            href = child.attrib.get("href")
            if href:
                return href
    
    return ""


def parse_datetime(value: str) -> datetime | None:
    """日時文字列をdatetimeに変換する（RFC2822 / ISO8601対応）。

    タイムゾーンが付いていない場合はJST(+09:00)として扱う。
    """

    if not value:
        return None

    value = value.strip()

    # まずRFC2822形式を試す
    try:
        dt = parsedate_to_datetime(value)
    except Exception:  # noqa: BLE001
        dt = None

    # ISO8601形式をフォールバックで試す
    if dt is None:
        iso_value = value.replace("Z", "+00:00")
        # +0900 のような形式を +09:00 に整形
        if re.match(r".*[+-]\d{4}$", iso_value):
            iso_value = iso_value[:-5] + iso_value[-5:-2] + ":" + iso_value[-2:]
        try:
            dt = datetime.fromisoformat(iso_value)
        except Exception:  # noqa: BLE001
            dt = None

    if dt is None:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone(timedelta(hours=9)))
    return dt


# 後方互換用（既存の参照を保持）
_parse_datetime = parse_datetime
