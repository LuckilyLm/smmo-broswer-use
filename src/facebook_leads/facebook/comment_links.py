from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse, urlunparse


COMMENT_ID_QUERY_KEYS = ("comment_id", "reply_comment_id", "comment_id_to_reply", "story_fbid")
FACEBOOK_HOST_SUFFIX = ".facebook.com"
FACEBOOK_REDIRECT_PATHS = {"/l.php", "/flx/warn/"}


@dataclass(frozen=True)
class CommentLinkResolution:
    comment_id: str | None
    comment_url: str | None
    direct_comment_url: str | None
    comment_id_source: str


def extract_comment_id_from_url(url: str | None) -> str | None:
    normalized = normalize_comment_permalink(url)
    if not normalized:
        return None
    try:
        parsed = urlparse(normalized)
    except Exception:
        return None
    query = parse_qs(parsed.query)
    for key in COMMENT_ID_QUERY_KEYS:
        values = query.get(key) or []
        for value in values:
            value = value.strip()
            if value:
                return value
    return None


def normalize_comment_permalink(url: str | None, *, base_url: str | None = None) -> str | None:
    if not url:
        return None
    candidate = unescape(str(url).strip())
    if not candidate or candidate.startswith(("#", "javascript:", "mailto:")):
        return None
    if base_url:
        candidate = urljoin(base_url, candidate)
    elif candidate.startswith("/"):
        candidate = urljoin("https://www.facebook.com", candidate)
    try:
        parsed = urlparse(candidate)
    except Exception:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None

    host = (parsed.hostname or "").lower()
    if host == "facebook.com" or host.endswith(FACEBOOK_HOST_SUFFIX):
        if parsed.path.lower() in FACEBOOK_REDIRECT_PATHS:
            redirect = (parse_qs(parsed.query).get("u") or [None])[0]
            if redirect:
                return normalize_comment_permalink(unquote(redirect))
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))
    return None


def is_comment_permalink(url: str | None) -> bool:
    normalized = normalize_comment_permalink(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    query = parse_qs(parsed.query)
    if parsed.path.lower().endswith("/permalink.php"):
        return True
    return any(query.get(key) for key in COMMENT_ID_QUERY_KEYS)


def extract_comment_permalink_from_node(node: Any) -> str | None:
    links = getattr(node, "links", None)
    if links is None and isinstance(node, dict):
        links = node.get("links")
    if not links:
        return None

    base_url = _node_base_url(node)
    normalized = [
        url
        for link in links
        if (url := normalize_comment_permalink(_link_url(link), base_url=base_url)) is not None
    ]
    candidates = [url for url in normalized if is_comment_permalink(url)]
    if not candidates:
        return None

    with_comment_id = [
        url
        for url in candidates
        if any((parse_qs(urlparse(url).query).get(key) or []) for key in COMMENT_ID_QUERY_KEYS[:3])
    ]
    return (with_comment_id or candidates)[0]


def build_direct_comment_url(
    source_content_url: str | None,
    comment_id: str | None,
    comment_url: str | None = None,
) -> str | None:
    normalized_comment_url = normalize_comment_permalink(comment_url)
    if is_comment_permalink(normalized_comment_url):
        return normalized_comment_url
    if not source_content_url or not comment_id:
        return None
    try:
        parsed = urlparse(source_content_url)
    except Exception:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    query = parse_qs(parsed.query)
    query["comment_id"] = [comment_id]
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query, doseq=True),
            "",
        )
    )


def resolve_comment_links(
    *,
    source_content_url: str | None,
    node_comment_id: str | None = None,
    comment_url: str | None = None,
    author_url: str | None = None,
    direct_comment_url: str | None = None,
    comment_id_source: str | None = None,
) -> CommentLinkResolution:
    clean_comment_url = normalize_comment_permalink(comment_url)
    if not is_comment_permalink(clean_comment_url):
        clean_comment_url = None
    permalink_comment_id = extract_comment_id_from_url(clean_comment_url)
    node_id = _clean_id(node_comment_id)
    author_comment_id = extract_comment_id_from_url(author_url)

    if permalink_comment_id:
        resolved_id = permalink_comment_id
        resolved_source = "comment_link"
    elif clean_comment_url and "permalink.php" in clean_comment_url.lower():
        resolved_id = node_id
        resolved_source = "permalink"
    elif node_id:
        resolved_id = node_id
        resolved_source = "generated"
    elif author_comment_id:
        resolved_id = author_comment_id
        resolved_source = "author_url"
    else:
        resolved_id = None
        resolved_source = "unknown"

    resolved_direct = normalize_comment_permalink(direct_comment_url)
    if not is_comment_permalink(resolved_direct):
        resolved_direct = None
    if resolved_direct is None:
        resolved_direct = build_direct_comment_url(
            source_content_url,
            resolved_id,
            clean_comment_url,
        )

    if comment_id_source in {"permalink", "comment_link", "author_url", "generated", "unknown"}:
        resolved_source = comment_id_source

    return CommentLinkResolution(
        comment_id=resolved_id,
        comment_url=clean_comment_url,
        direct_comment_url=resolved_direct,
        comment_id_source=resolved_source,
    )


def _link_url(link: Any) -> str | None:
    if isinstance(link, str):
        return link
    if isinstance(link, dict):
        value = link.get("href") or link.get("url")
        return str(value) if value else None
    value = getattr(link, "href", None) or getattr(link, "url", None)
    return str(value) if value else None


def _node_base_url(node: Any) -> str | None:
    if isinstance(node, dict):
        value = node.get("base_url") or node.get("page_url") or node.get("source_content_url")
    else:
        value = (
            getattr(node, "base_url", None)
            or getattr(node, "page_url", None)
            or getattr(node, "source_content_url", None)
        )
    return str(value) if value else None


def _clean_id(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip()
    return cleaned or None
