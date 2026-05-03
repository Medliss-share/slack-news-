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

    - ASCII のみのエントリ: 前後が ASCII の「単語構成文字」(英数字と _) でないときに一致。
      `\\b` は「Ubieが」のように直後に日本語が続くと境界にならないため使わない。
      英単語内の部分一致（"Ro" in "Ground"）は引き続き防ぐ。
    - 日本語を含むエントリは単純な部分一致
    """
    matched: list[str] = []
    # ASCII 単語文字の直後/直前にだけ「境界」があるとみなす（\b の代わり）
    _ascii_word_char = r"A-Za-z0-9_"
    for kw in allowlist:
        if not kw:
            continue
        if kw.isascii():
            pat = rf"(?<![{_ascii_word_char}]){re.escape(kw)}(?![{_ascii_word_char}])"
            if re.search(pat, text, re.IGNORECASE):
                matched.append(kw)
        else:
            if kw in text:
                matched.append(kw)
    return matched


def _stage1_noise_match(text_for_denylist: str, ng_kw: list[str]) -> bool:
    """Stage 1: 拒否キーワードのいずれかに該当するか（小文字化済みテキストに対して判定）。"""
    if not ng_kw:
        return False
    return any(kw in text_for_denylist for kw in ng_kw)


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
    """記事を絞り込む（段階的パイプライン、拾い上げ中心）。

    Stage 0: exclude_domains
    Stage 1: 任意の exclude_keywords（デフォルトは空。EXCLUDE_EXTRA のみ）でイベント以外を照合
    Stage 2: 包含ゲート
      - is_event → 通過（Stage 1 もバイパス）
      - is_healthtech_priority: 医療DX ゲート有効時は (医療 AND (IT OR 医療DX)) OR 企業WL。
        無効時は従来どおり 医療 OR 企業WL
      - company_allowlist → 企業名マッチで包含
      - is_general_tech → GENERAL_TECH キーワード
      - それ以外 → 医療×IT + 任意で医療DX ゲート
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
    skipped_stage1_noise = 0
    skipped_priority_no_inclusion = 0
    passed_by_priority = 0
    passed_by_allowlist = 0

    for article in articles_list:
        # --- Stage 0: ドメイン除外 ---
        if ng_domains and article.link:
            link_lower = article.link.lower()
            if any(dom in link_lower for dom in ng_domains):
                continue

        raw_text = f"{article.title} {article.summary or ''}"
        text = raw_text.lower()
        text_no_urls = _strip_urls(raw_text).lower()

        # --- Stage 1: 任意の拒否キーワード（イベントはバイパス）---
        if not article.is_event and ng_kw and _stage1_noise_match(text_no_urls, ng_kw):
            skipped_stage1_noise += 1
            continue

        # --- Stage 2: 包含ゲート ---

        if article.is_event:
            filtered.append(article)
            continue

        if article.is_healthtech_priority:
            orig_text_for_allow = f"{article.title} {article.summary or ''}"
            allow_match = bool(
                allowlist_raw and _match_allowlist(orig_text_for_allow, allowlist_raw)
            )
            if dx_kw:
                has_med = bool(med_kw) and any(kw in text for kw in med_kw)
                has_it = bool(it_kw) and any(kw in text for kw in it_kw)
                has_dx = any(kw in text for kw in dx_kw)
                if not (allow_match or (has_med and (has_it or has_dx))):
                    skipped_priority_no_inclusion += 1
                    continue
            else:
                if med_kw and not any(kw in text for kw in med_kw):
                    if not allow_match:
                        continue

            base_cats = list(article.categories or [])
            if "healthtech" not in base_cats:
                base_cats.append("healthtech")
            article.categories = base_cats
            passed_by_priority += 1
            filtered.append(article)
            continue

        orig_text = f"{article.title} {article.summary or ''}"
        matched_company = (
            _match_allowlist(orig_text, allowlist_raw) if allowlist_raw else []
        )
        if matched_company:
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

        if article.is_general_tech:
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

        matched_med = [kw for kw in med_kw if kw in text]
        if not matched_med:
            continue

        matched_it = [kw for kw in it_kw if kw in text]
        if not matched_it:
            continue

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

    if skipped_stage1_noise:
        logger.info(
            "Skipped %d articles at Stage 1 (exclude_keywords / EXCLUDE_EXTRA)",
            skipped_stage1_noise,
        )
    if skipped_priority_no_inclusion:
        logger.info(
            "Skipped %d healthtech-priority articles (no inclusion: need med AND (it OR dx), or company allowlist)",
            skipped_priority_no_inclusion,
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
