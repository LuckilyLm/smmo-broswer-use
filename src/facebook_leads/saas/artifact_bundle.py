from __future__ import annotations

import html
import json
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import atomic_write_json, load_json_safe


@dataclass(frozen=True)
class ArtifactObjectConfig:
    enabled: bool
    endpoint: str | None
    access_key: str | None
    secret_key: str | None
    bucket: str | None
    region: str
    prefix: str
    public_base_url: str | None
    secure: bool

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.endpoint and self.access_key and self.secret_key and self.bucket)


def write_execution_bundle(
    root: Path,
    *,
    tenant_id: str,
    execution: dict[str, Any],
    keywords: list[dict[str, Any]],
    leads: list[dict[str, Any]],
) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    runs = _run_summaries(root)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "execution": execution,
        "keywords": keywords,
        "summary": _summary(execution, keywords, leads, runs),
        "leads": leads,
        "runs": runs,
        "raw_artifacts": _artifact_index(root),
    }
    json_path = root / "execution_report.json"
    html_path = root / "execution_report.html"
    atomic_write_json(json_path, payload)
    html_path.write_text(_render_html(payload), encoding="utf-8")
    return {"execution_report_json": json_path, "execution_report_html": html_path}


def upload_execution_artifacts(root: Path, *, tenant_id: str, execution_id: str, config: ArtifactObjectConfig) -> dict[str, Any]:
    if not config.configured:
        return {"enabled": bool(config.enabled), "uploaded": 0, "items": [], "error": "object_storage_not_configured" if config.enabled else None}
    report_path = root / "execution_report.html"
    if not report_path.is_file():
        return {"enabled": True, "uploaded": 0, "items": [], "error": "execution_report_missing"}
    try:
        import boto3
        from botocore.client import Config as BotoConfig
    except Exception as exc:  # pragma: no cover - exercised only when optional dependency missing
        return {"enabled": True, "uploaded": 0, "items": [], "error": f"boto3_unavailable:{type(exc).__name__}"}

    endpoint = str(config.endpoint or "").rstrip("/")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        region_name=config.region,
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        use_ssl=config.secure,
    )
    prefix = "/".join(part.strip("/") for part in [config.prefix, "tenants", tenant_id, "executions", execution_id] if part.strip("/"))
    uploaded: list[dict[str, Any]] = []
    rel = report_path.relative_to(root).as_posix()
    key = f"{prefix}/{rel}"
    content_type = mimetypes.guess_type(report_path.name)[0] or "text/html"
    client.upload_file(str(report_path), config.bucket, key, ExtraArgs={"ContentType": content_type})
    uploaded.append({"name": report_path.name, "path": rel, "key": key, "url": _public_url(config, key), "content_type": content_type, "size": report_path.stat().st_size})
    manifest = {"enabled": True, "bucket": config.bucket, "prefix": prefix, "uploaded": len(uploaded), "items": uploaded, "error": None}
    atomic_write_json(root / "artifact_manifest.json", manifest)
    return manifest


def _public_url(config: ArtifactObjectConfig, key: str) -> str:
    if config.public_base_url:
        return f"{config.public_base_url}/{key}"
    endpoint = str(config.endpoint or "").rstrip("/")
    return f"{endpoint}/{config.bucket}/{key}"


def _run_summaries(root: Path) -> list[dict[str, Any]]:
    runs_root = root / "runs"
    summaries: list[dict[str, Any]] = []
    if not runs_root.exists():
        return summaries
    for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        scan = load_json_safe(run_dir / "scan_result.json", default={})
        lead_report = load_json_safe(run_dir / "lead_report.json", default={})
        reply_plan = load_json_safe(run_dir / "batch_reply_plan.json", default={})
        plan_summary = reply_plan.get("summary") or {}
        blockage_reasons = _blockage_reasons(reply_plan)
        summaries.append(
            {
                "run_id": run_dir.name,
                "keyword": scan.get("keyword") or lead_report.get("keyword"),
                "status": scan.get("status"),
                "login_state": scan.get("login_state"),
                "active_page_url": scan.get("active_page_url"),
                "scanned_contents": len(scan.get("contents") or []),
                "scanned_comments": len(scan.get("comments") or []),
                "lead_candidates": _lead_count(lead_report),
                "eligible_count": plan_summary.get("eligible_count"),
                "selected_count": plan_summary.get("selected_count"),
                "reply_plan_summary": plan_summary,
                "reply_outcome": _reply_outcome(reply_plan, blockage_reasons),
                "blockage_reasons": blockage_reasons,
                "first_content_url": _first_content_url(scan),
            }
        )
    return summaries


def _artifact_index(root: Path) -> list[dict[str, Any]]:
    items = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            items.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size})
    return items


def _summary(execution: dict[str, Any], keywords: list[dict[str, Any]], leads: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_count = _sum_available(runs, "eligible_count", fallback=execution.get("eligible_count"))
    selected_count = _sum_available(runs, "selected_count", fallback=execution.get("selected_count"))
    blockage_reasons = _merge_reason_counts(runs)
    reply_outcome = _execution_reply_outcome(runs, eligible_count, selected_count, blockage_reasons)
    return {
        "status": execution.get("status"),
        "send_disabled": bool(execution.get("send_disabled")),
        "total_keywords": len(keywords),
        "completed_keywords": sum(1 for row in keywords if row.get("status") == "completed"),
        "failed_keywords": sum(1 for row in keywords if row.get("status") == "failed"),
        "scanned_contents": sum(int(row.get("discovered_contents") or 0) for row in keywords),
        "scanned_comments": sum(int(row.get("scanned_comments") or 0) for row in keywords),
        "lead_candidates": sum(int(row.get("lead_candidates") or 0) for row in keywords),
        "eligible_count": eligible_count,
        "selected_count": selected_count,
        "reply_outcome": reply_outcome,
        "blockage_reasons": blockage_reasons,
        "persisted_leads": len(leads),
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in keywords),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in keywords),
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in keywords),
        "run_count": len(runs),
    }


def _sum_available(runs: list[dict[str, Any]], key: str, *, fallback: Any = None) -> int | None:
    values = [row.get(key) for row in runs if row.get(key) is not None]
    if values:
        return sum(int(value or 0) for value in values)
    return int(fallback) if fallback is not None else None


def _blockage_reasons(reply_plan: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in reply_plan.get("items") or []:
        if item.get("eligible") is True:
            continue
        for reason in item.get("blocking_reasons") or []:
            key = str(reason or "unknown").strip() or "unknown"
            counts[key] = counts.get(key, 0) + 1
    return counts


def _merge_reason_counts(runs: list[dict[str, Any]]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for run in runs:
        for reason, count in (run.get("blockage_reasons") or {}).items():
            merged[reason] = merged.get(reason, 0) + int(count or 0)
    return merged


def _reply_outcome(reply_plan: dict[str, Any], blockage_reasons: dict[str, int]) -> dict[str, Any]:
    summary = reply_plan.get("summary") or {}
    if not reply_plan:
        return {"status": "plan_unavailable", "reason": "batch_reply_plan_missing"}
    eligible = int(summary.get("eligible_count") or 0)
    selected = int(summary.get("selected_count") or 0)
    if selected:
        return {"status": "candidates_selected", "eligible_count": eligible, "selected_count": selected}
    if eligible:
        return {"status": "eligible_not_selected", "eligible_count": eligible, "selected_count": 0}
    return {
        "status": "no_eligible_candidates",
        "eligible_count": 0,
        "selected_count": 0,
        "blocked_count": int(summary.get("blocked_count") or 0),
        "blockage_reasons": blockage_reasons,
    }


def _execution_reply_outcome(
    runs: list[dict[str, Any]],
    eligible_count: int | None,
    selected_count: int | None,
    blockage_reasons: dict[str, int],
) -> dict[str, Any]:
    if not runs or all(run.get("reply_outcome", {}).get("status") == "plan_unavailable" for run in runs):
        return {"status": "plan_unavailable", "reason": "batch_reply_plan_missing"}
    if selected_count:
        return {"status": "candidates_selected", "eligible_count": eligible_count, "selected_count": selected_count}
    if eligible_count:
        return {"status": "eligible_not_selected", "eligible_count": eligible_count, "selected_count": 0}
    return {
        "status": "no_eligible_candidates",
        "eligible_count": eligible_count,
        "selected_count": selected_count,
        "blockage_reasons": blockage_reasons,
    }


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    keywords = payload["keywords"]
    runs = payload["runs"]
    leads = payload["leads"]
    execution = payload["execution"]
    execution_id = html.escape(str(execution.get("id") or ""))
    campaign_id = html.escape(str(execution.get("campaign_id") or ""))
    campaign_name = html.escape(str(execution.get("campaign_name") or execution.get("campaign_id") or ""))
    account_name = html.escape(str(execution.get("platform_account_name") or ""))
    generated_at = html.escape(_format_datetime(payload.get("generated_at")))
    status = html.escape(_zh_value(summary.get("status") or "unknown"))
    send_mode = "安全模式：仅生成计划，未真实发送" if summary.get("send_disabled") else "允许发送"
    reply_outcome = summary.get("reply_outcome") or {}
    summary_text = html.escape(_summary_text(summary, keywords))
    reason_chips = _reason_chips(summary.get("blockage_reasons") or {})
    outcome_status = html.escape(_zh_value(str(reply_outcome.get("status") or "unknown")))
    primary_cards = [
        ("扫描内容", summary.get("scanned_contents")),
        ("扫描评论", summary.get("scanned_comments")),
        ("候选线索", summary.get("lead_candidates")),
        ("可回复候选", summary.get("eligible_count")),
    ]
    secondary_cards = [
        ("关键词", summary.get("total_keywords")),
        ("已完成", summary.get("completed_keywords")),
        ("失败关键词", summary.get("failed_keywords")),
        ("已选回复", summary.get("selected_count")),
        ("入库线索", summary.get("persisted_leads")),
        ("Token 合计", summary.get("total_tokens")),
    ]
    first_keyword = keywords[0] if keywords else {}
    config_cards = [
        ("目标策略", first_keyword.get("target_policy")),
        ("回复模式", first_keyword.get("reply_mode")),
        ("识别模式", first_keyword.get("lead_detection_mode")),
    ]
    config_section = ""
    if any(value not in (None, "") for _, value in config_cards):
        config_section = f"<section><h2>执行配置</h2><div class=\"compact-grid\">{''.join(_metric(label, value) for label, value in config_cards)}</div></section>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>营销活动执行报告 {execution_id}</title>
<style>
:root{{color-scheme:light;--ink:#132238;--muted:#637189;--line:#dbe5f1;--paper:#ffffff;--page:#f3f6fa;--brand:#285f9f;--brand-ink:#174374;--ok:#0f8a5f;--ok-bg:#e8f7ef;--warn:#9a5b00;--warn-bg:#fff4d8;--bad:#b42318;--bad-bg:#ffe9e7}}
*{{box-sizing:border-box}}body{{font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;margin:0;color:var(--ink);background:var(--page);line-height:1.58}}
.page{{max-width:1120px;margin:0 auto;padding:30px 20px 44px}}
.hero{{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:28px 30px;margin-bottom:16px;box-shadow:0 18px 42px rgba(31,57,89,.08)}}
.hero-top{{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:18px}}.eyebrow{{font-size:13px;color:var(--brand);font-weight:700;margin-bottom:8px}}h1{{font-size:30px;margin:0;letter-spacing:0}}h2{{font-size:18px;margin:0;color:#101f35}}p{{margin:0}}
.report-meta{{display:grid;gap:5px;color:var(--muted);font-size:13px;text-align:right;max-width:360px}}.summary{{color:#2d3e56;font-size:15px;margin-top:14px;max-width:860px}}
.pills{{display:flex;gap:9px;flex-wrap:wrap;margin-top:14px}}.pill{{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;padding:5px 11px;background:#fff;color:#4e6078;font-size:13px;white-space:nowrap}}.pill.status{{color:#fff;background:var(--brand);border-color:var(--brand)}}.pill.safe{{color:var(--warn);background:var(--warn-bg);border-color:#f2c56e}}
.outcome{{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:center;border-top:1px solid #e6edf5;margin-top:20px;padding-top:20px}}.outcome-title{{font-size:20px;font-weight:800;color:#101f35}}.outcome-note{{color:var(--muted);font-size:14px;margin-top:4px}}.outcome-badge{{border-radius:8px;padding:12px 16px;background:#eff6ff;color:var(--brand-ink);font-weight:800;text-align:center;min-width:150px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}}.metric{{border:1px solid #e0e8f2;border-radius:8px;padding:14px 15px;background:#fbfdff;min-height:86px}}.metric.primary{{background:#fff;border-color:#cfe0f3}}.metric-label{{color:var(--muted);font-size:13px}}.value{{font-size:26px;font-weight:800;margin-top:6px;word-break:break-word}}.value.small{{font-size:15px;font-weight:700;line-height:1.45}}
section{{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:20px;margin:0 0 16px;box-shadow:0 10px 24px rgba(31,57,89,.045)}}.section-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}}.section-note{{color:var(--muted);font-size:13px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.compact-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.empty{{color:var(--muted);padding:12px 0}}.comment{{max-width:560px;white-space:pre-wrap;word-break:break-word}}a{{color:var(--brand);text-decoration:none;font-weight:700}}a:hover{{text-decoration:underline}}
.table-wrap{{overflow:auto;border:1px solid #e3ebf5;border-radius:8px}}table{{border-collapse:collapse;width:100%;font-size:14px;background:#fff}}td,th{{border-bottom:1px solid #e7edf5;padding:12px;text-align:left;vertical-align:top}}th{{color:#52627a;font-weight:700;background:#f8fbff;white-space:nowrap}}tr:last-child td{{border-bottom:0}}
.chips{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}.chip{{display:inline-flex;gap:4px;align-items:center;border-radius:999px;padding:4px 10px;background:#e9f2ff;color:#244f88;font-size:13px;font-weight:700}}.chip.warn{{background:var(--warn-bg);color:#7a4b00}}
.badge{{display:inline-flex;align-items:center;border-radius:999px;padding:3px 9px;font-size:13px;font-weight:700;background:#eef2f7;color:#475569;white-space:nowrap}}.badge.ok{{background:var(--ok-bg);color:var(--ok)}}.badge.warn{{background:var(--warn-bg);color:var(--warn)}}.badge.bad{{background:var(--bad-bg);color:var(--bad)}}.muted{{color:var(--muted)}}
@media(max-width:900px){{.hero-top,.outcome,.two{{grid-template-columns:1fr;display:grid}}.report-meta{{text-align:left;max-width:none}}.kpi-grid{{grid-template-columns:repeat(2,1fr)}}.compact-grid{{grid-template-columns:1fr 1fr}}}}
@media(max-width:560px){{.page{{padding:16px 10px 30px}}.hero,section{{padding:18px 16px}}h1{{font-size:25px}}.kpi-grid,.compact-grid{{grid-template-columns:1fr}}table{{font-size:13px}}td,th{{padding:9px}}}}
</style>
</head>
<body>
<main class="page">
<div class="hero">
  <div class="hero-top">
    <div>
      <div class="eyebrow">SMMO 社媒营销自动化平台</div>
      <h1>{campaign_name}</h1>
    </div>
    <div class="report-meta">
      <span>报告类型：营销活动执行报告</span>
      <span>生成时间：{generated_at}</span>
      <span>执行编号：{execution_id}</span>
      <span>活动编号：{campaign_id}</span>
    </div>
  </div>
  <div class="pills">
    <span class="pill status">执行状态：{status}</span>
    <span class="pill safe">{html.escape(send_mode)}</span>
    {f'<span class="pill">平台账号：{account_name}</span>' if account_name else ''}
  </div>
  <div class="outcome">
    <div>
      <div class="outcome-title">本次结论：{outcome_status}</div>
      <p class="summary">{summary_text}</p>
    </div>
    <div class="outcome-badge">{status}</div>
  </div>
  {reason_chips}
</div>
<section><div class="section-head"><h2>关键结果</h2><div class="section-note">优先展示业务结果，详细数据见下方明细</div></div><div class="kpi-grid">{''.join(_metric(label, value, primary=True) for label, value in primary_cards)}</div><div class="compact-grid">{''.join(_metric(label, value) for label, value in secondary_cards)}</div></section>
{config_section}
<div class="two">
  <section><h2>大模型用量</h2><div class="compact-grid">{''.join(_metric(label, value) for label, value in [('输入 Token', summary.get('prompt_tokens')), ('输出 Token', summary.get('completion_tokens')), ('Token 合计', summary.get('total_tokens'))])}</div></section>
  <section><h2>执行保护</h2><div class="compact-grid">{''.join(_metric(label, value) for label, value in [('发送开关', send_mode), ('运行次数', summary.get('run_count')), ('回复计划结果', reply_outcome.get('status'))])}</div></section>
</div>
<section><h2>关键词执行</h2>{_table(keywords, ['keyword','status','discovered_contents','scanned_comments','lead_candidates','prompt_tokens','completion_tokens','total_tokens','error_type'])}</section>
<section><h2>运行明细</h2>{_table(runs, ['keyword','status','login_state','scanned_contents','scanned_comments','lead_candidates','eligible_count','selected_count','reply_outcome','first_content_url'])}</section>
<section><h2>线索结果</h2>{_table(leads, ['author_name','final_intent_level','llm_confidence','comment_text','source_content_url']) if leads else '<div class="empty">本次没有入库线索。若候选线索大于 0 但入库为 0，请检查置信度阈值、去重规则和发送策略。</div>'}</section>
</main>
</body></html>"""


def _metric(key: str, value: Any, *, primary: bool = False) -> str:
    display = _display_value(value)
    is_numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    cls = "value" if is_numeric and len(display) <= 8 else "value small"
    metric_cls = "metric primary" if primary else "metric"
    return f"<div class='{metric_cls}'><div class='metric-label'>{html.escape(str(key))}</div><div class='{cls}'>{html.escape(display)}</div></div>"


def _table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "<div class=\"empty\">暂无数据。</div>"
    head = "".join(f"<th>{html.escape(_zh_label(column))}</th>" for column in columns)
    body = []
    for row in rows:
        cells = []
        for column in columns:
            value = _short(_display_value(row.get(column), column=column))
            if column.endswith("_url") and value:
                safe = html.escape(value, quote=True)
                cells.append(f"<td><a href=\"{safe}\" target=\"_blank\" rel=\"noreferrer\">打开链接</a></td>")
            elif column in {"status", "login_state", "final_intent_level"}:
                cells.append(f"<td>{_badge(value)}</td>")
            elif column == "comment_text":
                cells.append(f"<td class=\"comment\">{html.escape(value)}</td>")
            else:
                cells.append(f"<td>{html.escape(value)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<div class=\"table-wrap\"><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def _short(value: Any) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= 500 else text[:500] + "..."


def _zh_label(key: str) -> str:
    labels = {
        "keyword": "关键词",
        "status": "状态",
        "discovered_contents": "扫描内容数",
        "scanned_comments": "扫描评论数",
        "lead_candidates": "候选线索数",
        "eligible_count": "可回复候选数",
        "selected_count": "已选择数",
        "reply_outcome": "回复计划结果",
        "blockage_reasons": "阻塞原因",
        "prompt_tokens": "输入 Token",
        "completion_tokens": "输出 Token",
        "total_tokens": "Token 合计",
        "error_type": "错误类型",
        "run_id": "运行编号",
        "login_state": "登录状态",
        "scanned_contents": "扫描内容数",
        "first_content_url": "首条内容链接",
        "author_name": "作者",
        "final_intent_level": "意向等级",
        "llm_confidence": "大模型置信度",
        "comment_text": "评论内容",
        "source_content_url": "来源链接",
    }
    return labels.get(key, key)


def _display_value(value: Any, *, column: str | None = None) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return f"{value:,}" if isinstance(value, int) else f"{value:g}"
    if isinstance(value, dict):
        if column == "reply_outcome" or "status" in value:
            return _reply_outcome_text(value)
        if column == "blockage_reasons":
            return _reasons_text(value)
        return "；".join(f"{_zh_label(str(key))}：{_display_value(val)}" for key, val in value.items()) or "-"
    if isinstance(value, list):
        return "、".join(_display_value(item) for item in value) or "-"
    return _zh_value(str(value))


def _zh_value(value: str) -> str:
    if not isinstance(value, str):
        return str(value)
    values = {
        "completed": "已完成",
        "partial": "部分完成",
        "failed": "失败",
        "running": "运行中",
        "queued": "排队中",
        "cancelled": "已取消",
        "logged_in": "已登录",
        "logged_out": "未登录",
        "login_required": "需要重新登录",
        "facebook_not_logged_in": "Facebook 未登录",
        "platform_account_not_connected": "平台账号未连接",
        "cdp_unreachable": "浏览器连接不可达",
        "runtime_not_running": "浏览器运行时未启动",
        "checkpoint": "需要账号验证",
        "captcha": "需要验证码",
        "send_disabled": "安全模式",
        "not_attempted": "未尝试",
        "not_checked": "未检查",
        "not_checked_in_preflight": "预检模式未检查",
        "manual_approval": "人工审批",
        "automatic": "自动执行",
        "discovery_only": "仅发现公开线索",
        "rules_with_llm": "规则 + 大模型",
        "rules_only": "规则判断",
        "unknown": "未知",
        "high": "高意向",
        "medium": "中意向",
        "low": "低意向",
        "none": "无意向",
        "plan_unavailable": "未生成回复计划",
        "batch_reply_plan_missing": "回复计划文件缺失",
        "candidates_selected": "已选出可回复候选",
        "eligible_not_selected": "有可回复候选但未选中",
        "no_eligible_candidates": "暂无符合发送条件的候选",
        "source_not_allowed": "来源不在允许范围",
        "confidence_below_threshold": "置信度低于阈值",
        "llm_not_lead": "大模型判断非有效线索",
        "reply_disabled": "回复功能关闭",
        "duplicate": "重复线索",
        "already_replied": "已回复过",
        "missing_comment_text": "评论内容为空",
        "unknown": "未知",
    }
    return values.get(value, value)


def _reply_outcome_text(outcome: dict[str, Any]) -> str:
    status = _zh_value(str(outcome.get("status") or "unknown"))
    details = []
    if outcome.get("eligible_count") is not None:
        details.append(f"可回复 {int(outcome.get('eligible_count') or 0)}")
    if outcome.get("selected_count") is not None:
        details.append(f"已选择 {int(outcome.get('selected_count') or 0)}")
    if outcome.get("blocked_count") is not None:
        details.append(f"已阻塞 {int(outcome.get('blocked_count') or 0)}")
    reasons = _reasons_text(outcome.get("blockage_reasons") or {})
    if reasons != "-":
        details.append(reasons)
    return status if not details else f"{status}（{'；'.join(details)}）"


def _reasons_text(reasons: dict[str, Any]) -> str:
    if not reasons:
        return "-"
    return "；".join(f"{_zh_value(str(reason))} {int(count or 0)}" for reason, count in reasons.items())


def _reason_chips(reasons: dict[str, Any]) -> str:
    if not reasons:
        return ""
    chips = "".join(f"<span class=\"chip warn\">{html.escape(_zh_value(str(reason)))}：{int(count or 0)}</span>" for reason, count in reasons.items())
    return f"<div class=\"chips\">{chips}</div>"


def _summary_text(summary: dict[str, Any], keywords: list[dict[str, Any]]) -> str:
    keyword_text = "、".join(str(row.get("keyword") or "").strip() for row in keywords if row.get("keyword")) or "本次关键词"
    outcome = _reply_outcome_text(summary.get("reply_outcome") or {})
    send_text = "全程保持安全模式，未执行真实发送。" if summary.get("send_disabled") else "本次配置允许发送，请结合回复记录核对实际发送结果。"
    return (
        f"本次围绕「{keyword_text}」扫描 {int(summary.get('scanned_contents') or 0)} 条内容、"
        f"{int(summary.get('scanned_comments') or 0)} 条评论，识别 {int(summary.get('lead_candidates') or 0)} 条候选线索；"
        f"回复计划结果为：{outcome}。{send_text}"
    )


def _format_datetime(value: Any) -> str:
    if not value:
        return "-"
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _badge(value: str) -> str:
    cls = "badge"
    if value in {"已完成", "已登录", "高意向"}:
        cls += " ok"
    elif value in {"部分完成", "运行中", "排队中", "需要重新登录", "中意向", "低意向"}:
        cls += " warn"
    elif value in {"失败", "已取消"}:
        cls += " bad"
    return f"<span class=\"{cls}\">{html.escape(value)}</span>"


def _lead_count(report: dict[str, Any]) -> int:
    return sum(len(content.get("leads") or []) for content in report.get("contents") or [])


def _first_content_url(scan: dict[str, Any]) -> str | None:
    for item in scan.get("contents") or []:
        if item.get("url"):
            return str(item["url"])
    return None
