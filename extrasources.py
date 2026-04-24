from __future__ import annotations

import html
import logging
import re
import urllib.error
import urllib.request
from typing import List
from urllib.parse import urljoin

from fetcher import Article, parse_datetime
from httpclient import urlopen as _urlopen

GOOGLE_NEWS_RECENCY_DAYS = 3  # Google Newsの検索対象期間（日数）

logger = logging.getLogger(__name__)


def fetch_medicaltech(timeout: int = 10) -> List[Article]:
    """医療テックニュースのトップページから記事を取得する。"""
    url = "https://medicaltech-news.com/"
    text = _get(url, timeout)
    if text is None:
        return []

    articles: list[Article] = []
    
    # 方法1: 正規表現で抽出（修正版）
    # H3 タイトルとリンクを抜く（トップページの最新一覧）
    # 正規表現のバグ修正: \\s* -> \s*
    pattern = r'<h3[^>]*class="[^"]*item-ttl[^"]*"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
    for m in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
        link = m.group(1).strip()
        title = _clean_html(m.group(2))
        if not link or not title:
            continue
        
        # 相対URLを絶対URLに変換
        if not link.startswith("http"):
            link = urljoin(url, link)
        
        # time datetime を拾う（h3タグの後、より広い範囲で検索）
        # articleタグ全体を探す
        article_start = text.rfind('<article', 0, m.start())
        if article_start == -1:
            article_start = m.start()
        article_end = text.find('</article>', m.end())
        if article_end == -1:
            article_end = m.end() + 2000  # フォールバック: 2000文字まで
        
        article_section = text[article_start:article_end]
        tm = re.search(r'<time[^>]*datetime="([^"]+)"', article_section, re.IGNORECASE)
        published = tm.group(1) if tm else None
        
        # 概要（description）を取得（記事ページから取得を試みる）
        summary = _fetch_summary_from_page(link, timeout)
        
        # published文字列からpublished_atを設定
        published_at = parse_datetime(published) if published else None
        
        articles.append(Article(title=title, link=link, published=published, summary=summary, published_at=published_at))
    
    # 方法2: より柔軟なパターンでフォールバック
    if not articles:
        # より広範囲なパターンで検索
        pattern2 = r'<h[23][^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</h[23]>'
        for m in re.finditer(pattern2, text, flags=re.IGNORECASE | re.DOTALL):
            link = m.group(1).strip()
            title = _clean_html(m.group(2))
            if not link or not title or len(title) < 5:  # 短すぎるタイトルは除外
                continue
            if not link.startswith("http"):
                link = urljoin(url, link)
            # 概要を取得
            summary = _fetch_summary_from_page(link, timeout)
            articles.append(Article(title=title, link=link, published=None, summary=summary, published_at=None))
    
    logger.info("medicaltech-news: parsed %d articles", len(articles))
    return articles


def fetch_htwatch(timeout: int = 10) -> List[Article]:
    """ヘルステックウォッチのトップページから記事を取得する。"""
    url = "https://ht-watch.com/"
    text = _get(url, timeout)
    if text is None:
        return []

    articles: list[Article] = []
    
    # 方法1: 正規表現で抽出（修正版）
    # 正規表現のバグ修正: \\s* -> \s*
    pattern = r'<article[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>.*?<h2>(.*?)</h2>.*?(?:<p[^>]*class="[^"]*date[^"]*"[^>]*>(.*?)</p>)?'
    for m in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
        link = m.group(1).strip()
        title = _clean_html(m.group(2))
        if not link or not title:
            continue
        
        # 相対URLを絶対URLに変換
        if not link.startswith("http"):
            link = urljoin(url, link)
        
        published = _clean_html(m.group(3)) if m.group(3) else None
        
        # 概要（description）を取得（記事ページから取得を試みる）
        summary = _fetch_summary_from_page(link, timeout)
        
        # published文字列からpublished_atを設定
        published_at = parse_datetime(published) if published else None
        
        articles.append(Article(title=title, link=link, published=published, summary=summary, published_at=published_at))
    
    # 方法2: より柔軟なパターンでフォールバック
    if not articles:
        # articleタグ内のリンクとh2を探す
        pattern2 = r'<article[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>.*?<h2[^>]*>(.*?)</h2>'
        for m in re.finditer(pattern2, text, flags=re.IGNORECASE | re.DOTALL):
            link = m.group(1).strip()
            title = _clean_html(m.group(2))
            if not link or not title or len(title) < 5:
                continue
            if not link.startswith("http"):
                link = urljoin(url, link)
            # 概要を取得
            summary = _fetch_summary_from_page(link, timeout)
            articles.append(Article(title=title, link=link, published=None, summary=summary, published_at=None))
    
    logger.info("ht-watch: parsed %d articles", len(articles))
    return articles


def _parse_connpass_event_metadata(summary: str | None) -> tuple["datetime | None", str | None]:
    """connpass の summary から 開催日時 と 開催場所 を抽出する。

    summary の形式例:
        "開催日時: 2026/05/19 19:00 ～ 21:30\n開催場所: 東京都港区六本木..."
    """
    from datetime import datetime, timezone, timedelta

    if not summary:
        return None, None

    # 開催日時を抽出
    # 例: "開催日時: 2026/05/19 19:00 ～ 21:30" や "開催日時: 2026/05/19 19:00"
    event_dt: "datetime | None" = None
    dt_match = re.search(
        r"開催日時[:：]\s*(\d{4})/(\d{1,2})/(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?",
        summary,
    )
    if dt_match:
        year, month, day = int(dt_match.group(1)), int(dt_match.group(2)), int(dt_match.group(3))
        hour = int(dt_match.group(4)) if dt_match.group(4) else 0
        minute = int(dt_match.group(5)) if dt_match.group(5) else 0
        try:
            event_dt = datetime(
                year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=9))
            )
        except ValueError:
            event_dt = None

    # 開催場所を抽出
    loc: str | None = None
    loc_match = re.search(r"開催場所[:：]\s*([^\n<]+)", summary)
    if loc_match:
        loc = loc_match.group(1).strip()

    return event_dt, loc


def fetch_connpass(
    timeout: int = 10,
    allowed_locations: list[str] | None = None,
    lookahead_days: int = 7,
) -> List[Article]:
    """connpass の新着イベント Atom フィードから取得し、以下の条件で絞り込む:

    - 開催日時が 今 〜 +`lookahead_days` 日以内
    - 開催場所が `allowed_locations` のいずれかを含む（例: "オンライン" または "広島"）

    返される Article は is_event=True で categories=['conference'] が付与されるため、
    医療×IT 一次フィルタおよび published_at ベースの時間範囲フィルタはバイパスされる。
    """
    from datetime import datetime, timezone, timedelta
    from fetcher import fetch_feed

    url = "https://connpass.com/explore/ja.atom"
    allowed_locations = allowed_locations or []

    try:
        raw_articles = fetch_feed(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch connpass Atom: %s", exc)
        return []

    now = datetime.now(timezone(timedelta(hours=9)))
    horizon = now + timedelta(days=lookahead_days)

    filtered: list[Article] = []
    skipped_no_date = 0
    skipped_outside_window = 0
    skipped_location = 0

    for article in raw_articles:
        event_dt, location = _parse_connpass_event_metadata(article.summary)

        # 開催日時が解析できなければ除外
        if event_dt is None:
            skipped_no_date += 1
            continue

        # 開催日が now〜horizon の範囲外ならスキップ
        if not (now <= event_dt <= horizon):
            skipped_outside_window += 1
            continue

        # 開催場所フィルタ（指定キーワードのいずれかを含む必要あり）
        if allowed_locations:
            loc_text = (location or "") + " " + (article.summary or "")
            if not any(loc_kw in loc_text for loc_kw in allowed_locations):
                skipped_location += 1
                continue

        # イベントとしてマーク
        article.is_event = True
        article.event_start_at = event_dt
        article.event_location = location
        article.categories = ["conference"]
        filtered.append(article)

    logger.info(
        "connpass: fetched=%d kept=%d (skipped no-date=%d, outside=%d, location=%d, window=%dd, locations=%s)",
        len(raw_articles),
        len(filtered),
        skipped_no_date,
        skipped_outside_window,
        skipped_location,
        lookahead_days,
        ",".join(allowed_locations) if allowed_locations else "(none)",
    )
    return filtered


def fetch_google_news(timeout: int = 10) -> List[Article]:
    """Googleニュースから医療×IT関連の記事を取得する（RSSフィードを使用）。"""
    # GoogleニュースのRSSフィードを使用（医療×ITで検索）
    import urllib.parse
    from fetcher import fetch_feed

    query = f"医療 IT when:{GOOGLE_NEWS_RECENCY_DAYS}d"
    rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ja&gl=JP&ceid=JP:ja&scoring=n"

    try:
        articles = fetch_feed(rss_url, timeout=timeout)
        logger.info("google-news: fetched %d articles from RSS", len(articles))
        return articles
    except Exception as exc:
        logger.exception("Failed to fetch Google News RSS: %s", exc)
        return []


# =============================================================================
# 一般IT (Channel B) 用のソース取得関数
# =============================================================================
def fetch_general_tech_google_news(
    queries: List[str],
    timeout: int = 10,
    recency_days: int = 2,
) -> List[Article]:
    """Google News の日本語検索を複数クエリ回して一般IT記事を収集する。

    取得した記事には `is_general_tech=True` を付与し、main 側で医療×IT フィルタを
    バイパスさせる。
    """
    import urllib.parse
    from fetcher import fetch_feed

    all_articles: list[Article] = []
    seen_links: set[str] = set()

    for q in queries:
        query_str = f"{q} when:{recency_days}d"
        rss_url = (
            "https://news.google.com/rss/search"
            f"?q={urllib.parse.quote(query_str)}&hl=ja&gl=JP&ceid=JP:ja&scoring=n"
        )
        try:
            articles = fetch_feed(rss_url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to fetch Google News RSS for query=%s: %s", q, exc)
            continue

        kept = 0
        for a in articles:
            if a.link in seen_links:
                continue
            seen_links.add(a.link)
            a.is_general_tech = True
            all_articles.append(a)
            kept += 1
        logger.info(
            "google-news (general tech, query='%s'): fetched=%d new=%d",
            q,
            len(articles),
            kept,
        )

    logger.info(
        "google-news (general tech total): %d unique articles from %d queries",
        len(all_articles),
        len(queries),
    )
    return all_articles


def fetch_healthtech_priority_google_news(
    queries: List[str],
    timeout: int = 10,
    recency_days: int = 3,
) -> List[Article]:
    """Channel A 用に、ヘルステック/医療DX の資金調達・提携系 Google News を複数クエリ取得する。

    取得記事には `is_healthtech_priority=True` を付与し、filter 側で
    医療×IT / 医療DX ゲートをバイパスさせる（= 漏らさず Channel A に流す）。
    """
    import urllib.parse
    from fetcher import fetch_feed

    all_articles: list[Article] = []
    seen_links: set[str] = set()

    for q in queries:
        query_str = f"{q} when:{recency_days}d"
        rss_url = (
            "https://news.google.com/rss/search"
            f"?q={urllib.parse.quote(query_str)}&hl=ja&gl=JP&ceid=JP:ja&scoring=n"
        )
        try:
            articles = fetch_feed(rss_url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to fetch healthtech-priority Google News (query=%s): %s", q, exc
            )
            continue

        kept = 0
        for a in articles:
            if a.link in seen_links:
                continue
            seen_links.add(a.link)
            a.is_healthtech_priority = True
            all_articles.append(a)
            kept += 1
        logger.info(
            "google-news (healthtech priority, query='%s'): fetched=%d new=%d",
            q,
            len(articles),
            kept,
        )

    logger.info(
        "google-news (healthtech priority total): %d unique articles from %d queries",
        len(all_articles),
        len(queries),
    )
    return all_articles


def fetch_general_tech_rss(
    urls: List[str],
    timeout: int = 10,
) -> List[Article]:
    """一般IT向けRSS/Atomフィードを複数取得する。

    Publickey / ITmedia AI+ / ZDNet Japan 等の一般IT ニュースフィードを想定。
    取得した記事には `is_general_tech=True` を付与する。
    """
    from fetcher import fetch_feed

    all_articles: list[Article] = []
    seen_links: set[str] = set()

    for url in urls:
        try:
            articles = fetch_feed(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to fetch general-tech RSS %s: %s", url, exc)
            continue

        kept = 0
        for a in articles:
            if a.link in seen_links:
                continue
            seen_links.add(a.link)
            a.is_general_tech = True
            all_articles.append(a)
            kept += 1
        logger.info(
            "general-tech RSS (%s): fetched=%d new=%d",
            url,
            len(articles),
            kept,
        )

    logger.info(
        "general-tech RSS total: %d unique articles from %d feeds",
        len(all_articles),
        len(urls),
    )
    return all_articles


def _get(url: str, timeout: int) -> str | None:
    try:
        with _urlopen(url, timeout=timeout) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            return r.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        logger.error("HTTP error fetching %s: %s", url, exc)
    except urllib.error.URLError as exc:
        logger.error("URL error fetching %s: %s", url, exc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error fetching %s: %s", url, exc)
    return None


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _fetch_summary_from_page(link: str, timeout: int) -> str | None:
    """記事ページからsummary（description）を取得する共通関数。"""
    try:
        article_text = _get(link, timeout)
        if not article_text:
            return None
        
        # まずmeta description を探す
        desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', article_text, re.IGNORECASE)
        if not desc_match:
            # og:description を探す
            desc_match = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', article_text, re.IGNORECASE)
        
        if desc_match:
            meta_desc = _clean_html(desc_match.group(1))
            # サイト全体の説明文でないかチェック
            if len(meta_desc) > 20 and "クリッピングサイト" not in meta_desc and "HealthTechWatchサイトは" not in meta_desc:
                return meta_desc
        
        # meta descriptionが取得できない、またはサイト全体の説明の場合は、記事本文から抽出を試みる
        # entryクラス内の本文を探す
        entry_match = re.search(r'<article[^>]*class=["\']entry["\'][^>]*>(.*?)</article>', article_text, re.DOTALL | re.IGNORECASE)
        if entry_match:
            entry_content = entry_match.group(1)
            # 最初の数個の<p>タグから本文を抽出
            paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', entry_content, re.DOTALL)
            # 長い段落を探す（meta情報は短い）
            for p in paragraphs:
                clean_p = _clean_html(p).strip()
                if len(clean_p) > 50:  # 50文字以上の段落を本文とみなす
                    return clean_p
        
        # entryクラスがない場合、一般的な本文領域を探す
        # main、content、post-contentなどのクラスを探す
        for class_name in ['main', 'content', 'post-content', 'article-body', 'entry-content']:
            content_match = re.search(
                rf'<div[^>]*class=["\'][^"]*{class_name}[^"]*["\'][^>]*>(.*?)</div>',
                article_text,
                re.DOTALL | re.IGNORECASE
            )
            if content_match:
                content = content_match.group(1)
                paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
                for p in paragraphs:
                    clean_p = _clean_html(p).strip()
                    if len(clean_p) > 50:
                        return clean_p
        
        # 最後の手段: 最初の長い<p>タグを探す
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', article_text, re.DOTALL)
        for p in paragraphs:
            clean_p = _clean_html(p).strip()
            if len(clean_p) > 50:
                return clean_p
                
    except Exception:
        pass  # 概要の取得に失敗しても続行
    
    return None
