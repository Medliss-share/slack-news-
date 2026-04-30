from __future__ import annotations

import logging
import re
from typing import Iterable, List

from slack_news.domain.article import Article

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def _strip_urls(s: str) -> str:
    """画像CDN等のURLに誤ってキーワードがマッチするのを防ぐ（例: freetls → TLS）。"""
    return _URL_RE.sub(" ", s)


def _match_allowlist(text: str, allowlist: Iterable[str]) -> list[str]:
    """企業ホワイトリストのマッチング。

    - ASCII 英数字のエントリは単語境界 `\\b` で判定（"Ro" が "Ground" に誤マッチするのを防ぐ）
    - 日本語を含むエントリは単純な部分一致
    """
    matched: list[str] = []
    for kw in allowlist:
        if not kw:
            continue
        if kw.isascii():
            if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE):
                matched.append(kw)
        else:
            if kw in text:
                matched.append(kw)
    return matched


def filter_articles(
    articles: Iterable[Article],
    medical_keywords: Iterable[str],
    it_keywords: Iterable[str],
    exclude_keywords: Iterable[str] | None = None,
    exclude_domains: Iterable[str] | None = None,
    general_tech_keywords: Iterable[str] | None = None,
    medical_dx_keywords: Iterable[str] | None = None,
    company_allowlist: Iterable[str] | None = None,
) -> List[Article]:
    """記事を絞り込む。

    分岐:
    - is_event=True → 医療×IT フィルタをバイパスしてそのまま通す（ソース側でイベント条件絞り込み済み）
    - is_general_tech=True → 医療×IT フィルタをバイパスし、代わりに general_tech_keywords のいずれかを含む記事のみ通す。
      EXCLUDE はタイトルのみに適用（PR TIMES 本文の定型文で誤除外されないようにする）
    - is_healthtech_priority=True → Channel A 用の優先クエリ由来。医療×IT / 医療DX を
                                    バイパスし、EXCLUDE のみ適用して通す
    - company_allowlist マッチ → 医療DX 系企業名が含まれる記事は無条件で通す（EXCLUDE は適用）
    - それ以外 → 医療×IT キーワード両方を含む記事のみ通す
                  加えて medical_dx_keywords が指定されていれば、そのいずれかを含む記事のみ通す
                  （Channel A 用の第3ゲート: 医療DX らしさを要求する）
    """
    articles_list = list(articles)
    med_kw = [kw.lower() for kw in medical_keywords]
    it_kw = [kw.lower() for kw in it_keywords]
    ng_kw = [kw.lower() for kw in (exclude_keywords or [])]
    ng_domains = [dom.lower() for dom in (exclude_domains or [])]
    gt_kw = [kw.lower() for kw in (general_tech_keywords or [])]
    dx_kw = [kw.lower() for kw in (medical_dx_keywords or [])]
    allowlist_raw = list(company_allowlist or [])

    filtered: list[Article] = []
    skipped_general_tech_no_match = 0
    skipped_medical_dx_no_match = 0
    passed_by_allowlist = 0
    passed_by_priority = 0
    for article in articles_list:
        # ドメインで除外
        if ng_domains and article.link:
            link_lower = article.link.lower()
            if any(dom in link_lower for dom in ng_domains):
                continue

        raw_text = f"{article.title} {article.summary or ''}"
        text = raw_text.lower()
        # 一般ITキーワード判定は URL を除く（PR TIMES の画像URLに tls 等が含まれるのを防ぐ）
        text_no_urls = _strip_urls(raw_text).lower()

        # イベント（connpass等）は医療×ITフィルタをバイパスして通過させる
        if article.is_event:
            filtered.append(article)
            continue

        # Channel A 優先ソース由来: EXCLUDE 適用 + 医療系キーワードを最低1つ必須
        # （Google News 検索のずれで医療と無関係な記事が混入するのを防ぐ）
        if article.is_healthtech_priority:
            if ng_kw and any(kw in text for kw in ng_kw):
                continue
            if med_kw and not any(kw in text for kw in med_kw):
                # ヘルステック企業名がハッキリ含まれている場合は許容（Ubie 等）
                orig_text_for_allow = f"{article.title} {article.summary or ''}"
                if not (allowlist_raw and _match_allowlist(orig_text_for_allow, allowlist_raw)):
                    continue
            # ベースカテゴリとして healthtech を付与（categorizer 側で competitor 等の追加分類される）
            base_cats = list(article.categories or [])
            if "healthtech" not in base_cats:
                base_cats.append("healthtech")
            article.categories = base_cats
            passed_by_priority += 1
            filtered.append(article)
            continue

        # 企業ホワイトリスト: 医療DX 系企業名を含む記事は全ゲートをバイパス
        # 英字エントリは単語境界判定（大文字小文字無視）。記事の元文字列（大小保存）で判定する。
        orig_text = f"{article.title} {article.summary or ''}"
        matched_company = (
            _match_allowlist(orig_text, allowlist_raw) if allowlist_raw else []
        )
        if matched_company:
            if ng_kw and any(kw in text for kw in ng_kw):
                continue
            base_cats = list(article.categories or [])
            if "healthtech" not in base_cats:
                base_cats.append("healthtech")
            passed_by_allowlist += 1
            filtered.append(
                Article(
                    title=article.title,
                    link=article.link,
                    published=article.published,
                    summary=article.summary,
                    published_at=article.published_at,
                    matched_keywords=matched_company,
                    categories=base_cats,
                    is_event=article.is_event,
                    event_start_at=article.event_start_at,
                    event_location=article.event_location,
                    is_general_tech=article.is_general_tech,
                    is_healthtech_priority=article.is_healthtech_priority,
                )
            )
            continue

        # 一般IT 記事: 医療×IT をバイパスし、general_tech_keywords マッチのみ通す
        if article.is_general_tech:
            title_lower = article.title.lower()
            if ng_kw and any(kw in title_lower for kw in ng_kw):
                continue
            if gt_kw and not any(kw in text_no_urls for kw in gt_kw):
                skipped_general_tech_no_match += 1
                continue
            matched_gt = [
                kw for kw in (general_tech_keywords or []) if kw.lower() in text_no_urls
            ]
            filtered.append(
                Article(
                    title=article.title,
                    link=article.link,
                    published=article.published,
                    summary=article.summary,
                    published_at=article.published_at,
                    matched_keywords=matched_gt,
                    categories=article.categories,
                    is_event=article.is_event,
                    event_start_at=article.event_start_at,
                    event_location=article.event_location,
                    is_general_tech=article.is_general_tech,
                    is_healthtech_priority=article.is_healthtech_priority,
                )
            )
            continue

        # 通常記事: 医療×IT 両方を要求
        if ng_kw and any(kw in text for kw in ng_kw):
            continue

        matched_med = [kw for kw in med_kw if kw in text]
        if not matched_med:
            continue

        matched_it = [kw for kw in it_kw if kw in text]
        if not matched_it:
            continue

        # 医療DX 必須ゲート（Channel A 用）
        if dx_kw and not any(kw in text for kw in dx_kw):
            skipped_medical_dx_no_match += 1
            continue

        matched_keywords = []
        for kw in medical_keywords:
            if kw.lower() in matched_med:
                matched_keywords.append(kw)
        for kw in it_keywords:
            if kw.lower() in matched_it:
                matched_keywords.append(kw)

        filtered.append(
            Article(
                title=article.title,
                link=article.link,
                published=article.published,
                summary=article.summary,
                published_at=article.published_at,
                matched_keywords=matched_keywords,
                categories=article.categories,
                is_event=article.is_event,
                event_start_at=article.event_start_at,
                event_location=article.event_location,
                is_general_tech=article.is_general_tech,
                is_healthtech_priority=article.is_healthtech_priority,
            )
        )

    if passed_by_priority:
        logger.info("Passed %d articles via healthtech-priority flag", passed_by_priority)
    if passed_by_allowlist:
        logger.info("Passed %d articles via company allowlist", passed_by_allowlist)
    if skipped_general_tech_no_match:
        logger.info(
            "Skipped %d general-tech articles (no GENERAL_TECH keyword match)",
            skipped_general_tech_no_match,
        )
    if skipped_medical_dx_no_match:
        logger.info(
            "Skipped %d healthtech articles (no MEDICAL_DX keyword match)",
            skipped_medical_dx_no_match,
        )
    logger.info("Filtered %d articles -> %d", len(articles_list), len(filtered))
    return filtered
