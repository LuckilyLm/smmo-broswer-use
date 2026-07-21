from __future__ import annotations

import html
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .content_metadata import (
    detect_content_type_from_url,
    fallback_content_preview,
    is_meaningful_content_preview,
)
from .diagnostics import write_json
from .intent import LeadIntentClassifier
from .intent_models import ContentLeadSummary, LeadCandidate, LeadScanReport
from .labels import content_type_label, intent_category_label, intent_level_label
from .llm_review import build_llm_review_summary


def build_lead_report(scan_payload: dict[str, Any]) -> LeadScanReport:
    started = time.perf_counter()
    classifier = LeadIntentClassifier()
    content_metadata = _content_metadata(scan_payload)
    content_order = list(content_metadata)
    comments = scan_payload.get("comments", [])
    grouped_comments: dict[str, list[dict[str, Any]]] = {url: [] for url in content_order}
    for comment in comments:
        source_url = comment.get("source_content_url") or "unknown"
        if source_url not in grouped_comments:
            detected_type = detect_content_type_from_url(source_url)
            content_order.append(source_url)
            content_metadata[source_url] = {
                "source_content_url": source_url,
                "discovered_url": source_url,
                "final_url": source_url,
                "content_type": detected_type,
                "text_preview": None,
                "author_name": None,
            }
            grouped_comments[source_url] = []
        grouped_comments[source_url].append(comment)

    contents: list[ContentLeadSummary] = []
    for source_url in content_order:
        metadata = content_metadata[source_url]
        source_comments = grouped_comments.get(source_url, [])
        leads: list[LeadCandidate] = []
        for comment_dict in source_comments:
            comment = _comment_from_dict(comment_dict)
            lead = classifier.classify_comment(comment, metadata)
            if lead is not None:
                leads.append(lead)
        contents.append(
            ContentLeadSummary(
                source_content_url=source_url,
                discovered_url=metadata.get("discovered_url"),
                final_url=metadata.get("final_url"),
                content_type=metadata.get("content_type"),
                text_preview=_clean_content_preview(
                    metadata.get("text_preview"),
                    metadata.get("content_type"),
                ),
                author_name=metadata.get("author_name"),
                scanned_comment_count=len(source_comments),
                text_comment_count=sum(1 for comment in source_comments if (comment.get("text") or "").strip()),
                lead_candidate_count=len(leads),
                high_intent_count=sum(1 for lead in leads if lead.intent_level == "high"),
                medium_intent_count=sum(1 for lead in leads if lead.intent_level == "medium"),
                low_intent_count=sum(1 for lead in leads if lead.intent_level == "low"),
                leads=sorted(leads, key=lambda lead: lead.intent_score, reverse=True),
            )
        )

    timing = dict(scan_payload.get("timing") or {})
    timing["intent_classification_ms"] = int((time.perf_counter() - started) * 1000)
    report = LeadScanReport(
        keyword=scan_payload.get("keyword"),
        generated_at=datetime.now(timezone.utc).isoformat(),
        scanned_content_count=len(contents),
        scanned_comment_count=sum(item.scanned_comment_count for item in contents),
        text_comment_count=sum(item.text_comment_count for item in contents),
        lead_candidate_count=sum(item.lead_candidate_count for item in contents),
        high_intent_count=sum(item.high_intent_count for item in contents),
        medium_intent_count=sum(item.medium_intent_count for item in contents),
        low_intent_count=sum(item.low_intent_count for item in contents),
        contents=contents,
        timing=timing,
        diagnostics={
            "scan_success": scan_payload.get("success"),
            "scan_stage": scan_payload.get("stage"),
            "read_only": True,
            "source_result_path": (scan_payload.get("diagnostics") or {}).get("result_path"),
        },
        llm_review=build_llm_review_summary(
            enabled=False,
            model=None,
            candidate_count=sum(item.lead_candidate_count for item in contents),
            batches=[],
            batch_size=None,
            concurrency=None,
            elapsed_ms=0,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
        ),
    )
    return report


def write_lead_report_files(report: LeadScanReport, output_dir: str | Path) -> dict[str, str]:
    started = time.perf_counter()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "lead_report.json"
    html_path = output_path / "lead_report.html"
    report_dict = report.to_dict()
    write_json(json_path, report_dict)
    html_path.write_text(render_lead_report_html(report), encoding="utf-8")
    report.timing["report_generation_ms"] = int((time.perf_counter() - started) * 1000)
    write_json(json_path, report.to_dict())
    return {"lead_report_json": str(json_path), "lead_report_html": str(html_path)}


def render_lead_report_html(report: LeadScanReport) -> str:
    content_sections = "\n".join(_render_content_section(content) for content in report.contents)
    rows = "\n".join(_render_followup_row(index, lead) for index, lead in enumerate(_all_leads(report), start=1))
    content_rows = "\n".join(_render_content_index_row(content) for content in report.contents)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Facebook 购买意向线索筛选报告</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: #f4f6f8; color: #1f2933; }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    .hero {{ background: #1f2933; color: white; padding: 28px; border-radius: 8px; }}
    .hero h1 {{ margin: 0 0 12px; font-size: 28px; }}
    .meta {{ color: #d9e2ec; line-height: 1.7; }}
    .grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin: 18px 0; }}
    .metric, .section, .lead-card {{ background: white; border: 1px solid #d9e2ec; border-radius: 8px; }}
    .metric {{ padding: 16px; }}
    .metric strong {{ display: block; font-size: 26px; margin-bottom: 4px; }}
    .section {{ margin-top: 18px; padding: 18px; }}
    .section h2 {{ margin: 0 0 12px; font-size: 20px; }}
    .content-head {{ display: grid; grid-template-columns: 1fr auto; gap: 14px; align-items: start; }}
    .badge {{ display: inline-block; padding: 4px 8px; border-radius: 6px; background: #e0f2fe; color: #075985; font-weight: 700; font-size: 12px; }}
    .score-high {{ background: #fee2e2; color: #991b1b; }}
    .score-medium {{ background: #fef3c7; color: #92400e; }}
    .score-low {{ background: #dcfce7; color: #166534; }}
    .lead-card {{ padding: 14px; margin-top: 12px; }}
    .lead-top {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; }}
    .comment {{ white-space: pre-wrap; background: #f8fafc; border-left: 4px solid #94a3b8; padding: 10px; margin: 10px 0; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e5e7eb; padding: 10px; vertical-align: top; }}
    th {{ background: #f8fafc; }}
    a {{ color: #0f62fe; text-decoration: none; }}
    .muted {{ color: #64748b; }}
    .chips span {{ display: inline-block; background: #eef2ff; color: #3730a3; padding: 3px 7px; border-radius: 6px; margin: 2px; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>Facebook 购买意向线索筛选报告</h1>
      <div class="meta">
        搜索关键词：{_e(report.keyword or "当前页面")}<br>
        生成时间：{_e(format_generated_at(report.generated_at))}<br>
        本次扫描：{report.scanned_content_count} 个内容<br>
        扫描评论：{report.scanned_comment_count} 条<br>
        候选线索：{report.lead_candidate_count} 条<br>
        高意向：{report.high_intent_count} 条　中等意向：{report.medium_intent_count} 条<br>
        {_e(_llm_review_summary_text(report))}
      </div>
    </div>
    <div class="grid">
      {_metric("扫描内容", report.scanned_content_count)}
      {_metric("扫描评论", report.scanned_comment_count)}
      {_metric("有文字评论", report.text_comment_count)}
      {_metric("候选线索", report.lead_candidate_count)}
      {_metric("高意向线索", report.high_intent_count)}
    </div>
    <div class="section">
      <h2>扫描内容列表</h2>
      <table><thead><tr><th>类型</th><th>内容预览</th><th>评论数</th><th>线索数</th><th>高意向</th><th>链接</th></tr></thead><tbody>{content_rows}</tbody></table>
    </div>
    {content_sections}
    <div class="section">
      <h2>最终建议跟进清单</h2>
      <table><thead><tr><th>优先级</th><th>用户</th><th>评论内容</th><th>规则判断</th><th>AI 是否确认</th><th>AI 意向等级</th><th>AI 置信度</th><th>建议回复</th><th>来源类型</th><th>原帖链接</th><th>评论链接</th></tr></thead><tbody>{rows}</tbody></table>
    </div>
    <div class="section">
      <h2>筛选方法说明</h2>
      <p>{_e(_method_note(report))}</p>
    </div>
  </div>
  <script>
    function copySuggestedReply(button) {{
      const text = button.getAttribute('data-reply') || '';
      if (!text) return;
      navigator.clipboard.writeText(text);
      button.innerText = '已复制';
      setTimeout(() => button.innerText = '复制建议回复', 1200);
    }}
  </script>
</body>
</html>
"""


def _content_metadata(scan_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    contents = scan_payload.get("contents") or []
    per_content = (scan_payload.get("diagnostics") or {}).get("per_content") or []
    by_discovered = {item.get("discovered_url"): item for item in per_content if isinstance(item, dict)}
    metadata = {}
    for item in contents:
        url = item.get("url")
        diag = by_discovered.get(url, {})
        final_url = diag.get("final_url") or url
        source_url = final_url or url
        content_type = _best_content_type(
            diag.get("content_type"),
            item.get("content_type"),
            final_url,
            url,
        )
        preview = diag.get("text_preview") or item.get("text_preview")
        metadata[source_url] = {
            "source_content_url": source_url,
            "discovered_url": url,
            "final_url": final_url,
            "content_type": content_type,
            "text_preview": _clean_content_preview(preview, content_type),
            "author_name": diag.get("author_name") or item.get("author_name"),
        }
    return metadata


def _comment_from_dict(data: dict[str, Any]):
    from .models import FacebookComment

    return FacebookComment(
        comment_id=data.get("comment_id"),
        author_name=data.get("author_name"),
        author_url=data.get("author_url"),
        author_extract_strategy=data.get("author_extract_strategy"),
        text=clean_comment_text(data.get("text"), data.get("author_name"), data.get("timestamp_text")),
        timestamp_text=data.get("timestamp_text"),
        comment_url=data.get("comment_url"),
        is_reply=bool(data.get("is_reply")),
        parent_comment_id=data.get("parent_comment_id"),
        source_content_url=data.get("source_content_url"),
        fingerprint=data.get("fingerprint"),
        direct_comment_url=data.get("direct_comment_url"),
        comment_id_source=data.get("comment_id_source"),
    )


def _all_leads(report: LeadScanReport) -> list[LeadCandidate]:
    leads = [lead for content in report.contents for lead in content.leads]
    level_rank = {"high": 3, "medium": 2, "low": 1, "none": 0}
    ranked = sorted(
        enumerate(leads),
        key=lambda item: (
            0 if item[1].final_is_lead is True else 1,
            -level_rank.get(item[1].final_intent_level or item[1].intent_level, 0),
            -_llm_confidence(item[1]),
            -item[1].intent_score,
            item[0],
        ),
    )
    return [lead for _, lead in ranked]


def _render_content_section(content: ContentLeadSummary) -> str:
    leads = "\n".join(_render_lead_card(lead) for lead in content.leads)
    if not leads:
        leads = '<p class="muted">该内容未发现购买意向候选。</p>'
    content_label = content_type_label(content.content_type)
    return f"""<div class="section">
      <div class="content-head">
        <div>
          <h2>{_e(content_label)}</h2>
          <p>内容类型：{_e(content_label)}</p>
          <p>内容预览：{_e(content.text_preview or fallback_content_preview(content.content_type))}</p>
          <p>发布者：{_e(content.author_name or "未获取")}</p>
          <p>原帖地址：<span class="muted">{_e(content.source_content_url)}</span></p>
          <p><a href="{_attr(content.source_content_url)}" target="_blank" rel="noopener">打开 Facebook 原帖</a></p>
        </div>
        <div>
          <span class="badge">评论 {content.scanned_comment_count}</span>
          <span class="badge">线索 {content.lead_candidate_count}</span>
          <span class="badge score-high">高意向 {content.high_intent_count}</span>
        </div>
      </div>
      {leads}
    </div>"""


def _render_lead_card(lead: LeadCandidate) -> str:
    author = _author_html(lead)
    matches = " ".join(f"<span>{_e(match.keyword)}</span>" for match in lead.matched_keywords)
    categories = " ".join(
        f"<span>{_e(intent_category_label(category))}</span>"
        for category in lead.matched_categories
    )
    level_label = intent_level_label(lead.intent_level)
    source_type_label = content_type_label(lead.source_content_type)
    evidence = _lead_evidence_text(lead)
    comment_link = _comment_link_html(lead)
    return f"""<div class="lead-card">
      <div class="lead-top"><strong>{author}</strong><span class="badge score-{_attr(lead.intent_level)}">{_e(level_label)} · {lead.intent_score}分</span></div>
      <div class="muted">{_e(lead.timestamp_text or "")}</div>
      <div class="comment">{_e(lead.comment_text or "")}</div>
      <div class="chips">匹配关键词：{matches}</div>
      <div class="chips">意向类型：{categories}</div>
      <p>规则判断：{_e(intent_level_label(lead.rule_intent_level or lead.intent_level))} · {lead.rule_intent_score if lead.rule_intent_score is not None else lead.intent_score}分</p>
      <p>判断依据：{_e(evidence)}</p>
      {_ai_review_html(lead)}
      <p>来源内容：{_e(source_type_label)}</p>
      <p>来源帖子：<a href="{_attr(lead.source_content_url)}" target="_blank" rel="noopener">打开原帖</a></p>
      <p>精准定位评论：{comment_link}</p>
    </div>"""


def _render_followup_row(index: int, lead: LeadCandidate) -> str:
    rule_text = f"{intent_level_label(lead.rule_intent_level or lead.intent_level)} · {lead.rule_intent_score if lead.rule_intent_score is not None else lead.intent_score}分"
    ai_confirmed = _ai_confirmed_label(lead)
    ai_level = intent_level_label(lead.final_intent_level or lead.intent_level)
    confidence = _format_confidence(_llm_confidence(lead))
    reply = lead.final_suggested_reply or ((lead.llm_review or {}).get("suggested_reply") if lead.llm_review else "")
    reply_html = _suggested_reply_html(reply)
    return f"<tr><td>{index}</td><td>{_author_html(lead)}</td><td>{_e(_short(lead.comment_text, 120))}</td><td>{_e(rule_text)}</td><td>{_e(ai_confirmed)}</td><td>{_e(ai_level)}</td><td>{_e(confidence)}</td><td>{reply_html}</td><td>{_e(content_type_label(lead.source_content_type))}</td><td><a href=\"{_attr(lead.source_content_url)}\" target=\"_blank\" rel=\"noopener\">打开原帖</a></td><td>{_comment_link_html(lead)}</td></tr>"


def _render_content_index_row(content: ContentLeadSummary) -> str:
    preview = content.text_preview or fallback_content_preview(content.content_type)
    return f"<tr><td>{_e(content_type_label(content.content_type))}</td><td>{_e(_short(preview, 120))}</td><td>{content.scanned_comment_count}</td><td>{content.lead_candidate_count}</td><td>{content.high_intent_count}</td><td><a href=\"{_attr(content.source_content_url)}\" target=\"_blank\" rel=\"noopener\">查看原帖</a></td></tr>"


def _metric(label: str, value: int) -> str:
    return f'<div class="metric"><strong>{value}</strong><span>{_e(label)}</span></div>'


def _author_html(lead: LeadCandidate) -> str:
    name = _e(lead.author_name or "未知用户")
    if lead.author_url:
        return f'<a href="{_attr(lead.author_url)}" target="_blank" rel="noopener">{name}</a>'
    return name


def _comment_link_html(lead: LeadCandidate) -> str:
    if lead.direct_comment_url:
        return f'<a href="{_attr(lead.direct_comment_url)}" target="_blank" rel="noopener">查看该评论</a>'
    return '<span class="muted">暂无法精准定位</span>'


def _ai_review_html(lead: LeadCandidate) -> str:
    review = lead.llm_review or {}
    if not review:
        return "<p>AI 复核：未启用</p>"
    status = review.get("status")
    if status != "success":
        return f"<p>AI 复核：{_e(_llm_item_status_label(status))}，已回退规则判断。{_e(review.get('error') or '')}</p>"
    reply = lead.final_suggested_reply or review.get("suggested_reply") or ""
    return f"""
      <div>
        <p>AI 复核：真实潜客：{_e(_ai_confirmed_label(lead))}</p>
        <p>AI 意向等级：{_e(intent_level_label(review.get("intent_level")))} · 置信度：{_e(_format_confidence(float(review.get("confidence") or 0)))}</p>
        <p>AI 判断：{_e(review.get("reason_zh") or "")}</p>
        <p>建议回复：{_e(reply)}</p>
        {_suggested_reply_button(reply)}
      </div>
    """


def _suggested_reply_html(reply: str | None) -> str:
    if not reply:
        return '<span class="muted">无</span>'
    return f"{_e(_short(reply, 120))}<br>{_suggested_reply_button(reply)}"


def _suggested_reply_button(reply: str | None) -> str:
    if not reply:
        return ""
    return (
        f'<button type="button" class="badge" data-reply="{_attr(reply)}" '
        'onclick="copySuggestedReply(this)">复制建议回复</button>'
    )


def _ai_confirmed_label(lead: LeadCandidate) -> str:
    review = lead.llm_review or {}
    if review.get("status") != "success":
        return "未复核"
    return "是" if bool(review.get("is_lead")) else "否"


def _llm_item_status_label(status: str | None) -> str:
    return {
        "disabled": "未启用",
        "failed": "失败",
        "timeout": "超时",
        "missing": "缺失",
    }.get(status or "disabled", "未复核")


def _llm_review_summary_text(report: LeadScanReport) -> str:
    summary = report.llm_review or {}
    if not summary.get("enabled"):
        return "LLM 复核：未启用"
    status = summary.get("status")
    model = summary.get("model") or "未记录"
    candidate_count = int(summary.get("candidate_count") or 0)
    success_count = int(summary.get("success_count") or 0)
    fallback_count = int(summary.get("fallback_count") or 0)
    if status == "success":
        return f"LLM 复核：已完成 {success_count} / {candidate_count}　模型：{model}"
    if status == "partial":
        return f"LLM 复核：部分完成　成功：{success_count}　Fallback：{fallback_count}　模型：{model}"
    return f"LLM 复核：失败，已全部回退规则判断　模型：{model}"


def _method_note(report: LeadScanReport) -> str:
    summary = report.llm_review or {}
    if not summary.get("enabled"):
        return "本报告使用本地规则筛选候选线索，本次未启用大语言模型复核。本报告未执行任何 Facebook 回复、点赞、私信或其他写操作。"
    status = summary.get("status")
    if status == "success":
        return "本报告先使用本地规则筛选候选线索，再使用大语言模型进行语义复核和建议回复生成。本报告未执行任何 Facebook 回复、点赞、私信或其他写操作。"
    if status == "partial":
        return "本报告先使用本地规则筛选候选线索，并对部分候选完成大语言模型复核。未成功复核的候选已保留规则判断结果。本报告未执行任何 Facebook 回复、点赞、私信或其他写操作。"
    return "本次已尝试执行大语言模型复核，但调用失败或超时，所有候选均保留规则判断结果。本报告未执行任何 Facebook 回复、点赞、私信或其他写操作。"


def _llm_confidence(lead: LeadCandidate) -> float:
    review = lead.llm_review or {}
    if review.get("status") != "success":
        return 0.0
    try:
        return float(review.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _format_confidence(value: float) -> str:
    return f"{round(value * 100)}%"


def clean_comment_text(
    text: str | None,
    author_name: str | None = None,
    timestamp_text: str | None = None,
) -> str | None:
    if not text:
        return None
    lines = [" ".join(line.split()) for line in text.splitlines()]
    cleaned: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if author_name and line == author_name.strip():
            continue
        if timestamp_text and line == timestamp_text.strip():
            continue
        if _is_ui_noise_line(line):
            continue
        cleaned.append(line)
    if not cleaned:
        return None
    return "\n".join(cleaned)


def format_generated_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
        local_time = parsed.astimezone()
        return local_time.strftime("%Y年%m月%d日 %H:%M:%S")
    except Exception:
        return value.replace("T", " ").split(".")[0]


def _clean_content_preview(value: str | None, content_type: str | None) -> str:
    if is_meaningful_content_preview(value, content_type):
        return " ".join((value or "").split())
    return fallback_content_preview(content_type)


def _best_content_type(
    diag_type: str | None,
    candidate_type: str | None,
    final_url: str | None,
    discovered_url: str | None,
) -> str:
    final_type = detect_content_type_from_url(final_url)
    if final_type != "unknown":
        return final_type
    if diag_type and diag_type != "unknown":
        return diag_type
    if candidate_type and candidate_type != "unknown":
        return candidate_type
    discovered_type = detect_content_type_from_url(discovered_url)
    if discovered_type != "unknown":
        return discovered_type
    return "unknown"


def _is_ui_noise_line(line: str) -> bool:
    normalized = line.strip().lower()
    exact_noise = {
        "·",
        "作者",
        "author",
        "查看翻译",
        "see translation",
        "已编辑",
        "edited",
        "like",
        "reply",
        "share",
        "赞",
        "回复",
        "分享",
    }
    if normalized in exact_noise:
        return True
    if re.fullmatch(r"\d+", normalized):
        return True
    if re.fullmatch(r"\d+\s*(秒|分钟|小时|天|周|月|年)", normalized):
        return True
    if re.fullmatch(r"\d+\s*(s|m|h|d|w|mo|y)", normalized, re.I):
        return True
    return False


def _lead_evidence_text(lead: LeadCandidate) -> str:
    category_labels = [intent_category_label(category) for category in lead.matched_categories]
    keywords = "、".join(match.keyword for match in lead.matched_keywords[:4])
    if category_labels and keywords:
        return f"命中{'、'.join(category_labels)}相关关键词：{keywords}"
    if keywords:
        return f"命中关键词：{keywords}"
    return "命中购买意向规则"


def _short(value: str | None, limit: int) -> str:
    if not value:
        return ""
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "..."


def _e(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _attr(value: Any) -> str:
    return html.escape(str(value), quote=True)
