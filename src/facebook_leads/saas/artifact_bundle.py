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
                "reply_plan_summary": reply_plan.get("summary") or {},
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
    return {
        "status": execution.get("status"),
        "send_disabled": bool(execution.get("send_disabled")),
        "total_keywords": len(keywords),
        "completed_keywords": sum(1 for row in keywords if row.get("status") == "completed"),
        "failed_keywords": sum(1 for row in keywords if row.get("status") == "failed"),
        "scanned_contents": sum(int(row.get("discovered_contents") or 0) for row in keywords),
        "scanned_comments": sum(int(row.get("scanned_comments") or 0) for row in keywords),
        "lead_candidates": sum(int(row.get("lead_candidates") or 0) for row in keywords),
        "persisted_leads": len(leads),
        "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in keywords),
        "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in keywords),
        "total_tokens": sum(int(row.get("total_tokens") or 0) for row in keywords),
        "run_count": len(runs),
    }


def _render_html(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    keywords = payload["keywords"]
    runs = payload["runs"]
    leads = payload["leads"]
    execution = payload["execution"]
    execution_id = html.escape(str(execution.get("id") or ""))
    campaign_id = html.escape(str(execution.get("campaign_id") or ""))
    generated_at = html.escape(str(payload.get("generated_at") or ""))
    status = html.escape(_zh_value(summary.get("status") or "unknown"))
    send_mode = "仅生成计划，未真实发送" if summary.get("send_disabled") else "允许发送"
    cards = [
        ("关键词", summary.get("total_keywords")),
        ("已完成", summary.get("completed_keywords")),
        ("扫描内容", summary.get("scanned_contents")),
        ("扫描评论", summary.get("scanned_comments")),
        ("候选线索", summary.get("lead_candidates")),
        ("入库线索", summary.get("persisted_leads")),
        ("Token 合计", summary.get("total_tokens")),
        ("运行次数", summary.get("run_count")),
    ]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>关键词搜索回复任务报告 {execution_id}</title>
<style>
:root{{color-scheme:light;--ink:#10233f;--muted:#65758f;--line:#d8e1ee;--soft:#f6f8fb;--brand:#315c9f;--ok:#05865d;--warn:#b45309;--bad:#b42318}}
*{{box-sizing:border-box}}body{{font-family:Arial,"Microsoft YaHei",sans-serif;margin:0;color:var(--ink);background:var(--soft);line-height:1.5}}
.page{{max-width:1180px;margin:0 auto;padding:28px 24px 40px}}
.hero{{background:linear-gradient(135deg,#ffffff 0%,#eef5ff 100%);border:1px solid var(--line);border-radius:10px;padding:24px;margin-bottom:16px}}
.eyebrow{{font-size:13px;color:var(--muted);margin-bottom:6px}}h1{{font-size:28px;margin:0 0 10px}}h2{{font-size:18px;margin:0 0 12px}}
.meta{{display:flex;gap:10px;flex-wrap:wrap;color:var(--muted);font-size:13px}}.pill{{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;padding:4px 10px;background:#fff}}
.status{{color:#fff;background:var(--brand);border-color:var(--brand)}}.safe{{color:#fff;background:var(--warn);border-color:var(--warn)}}
section{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:18px;margin:0 0 16px;box-shadow:0 8px 20px rgba(16,35,63,.04)}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border-bottom:1px solid #e7edf5;padding:10px;text-align:left;vertical-align:top}}th{{color:var(--muted);font-weight:600;background:#fbfdff}}tr:last-child td{{border-bottom:0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}.metric{{border:1px solid #e1e8f2;border-radius:8px;padding:12px;background:#fbfdff}}.metric-label{{color:var(--muted);font-size:13px}}.value{{font-size:26px;font-weight:700;margin-top:4px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.empty{{color:var(--muted);padding:8px 0}}.comment{{max-width:520px;white-space:pre-wrap;word-break:break-word}}a{{color:var(--brand);text-decoration:none}}a:hover{{text-decoration:underline}}
@media(max-width:760px){{.page{{padding:18px 12px}}.two{{grid-template-columns:1fr}}table{{font-size:13px}}td,th{{padding:8px}}}}
</style>
</head>
<body>
<main class="page">
<div class="hero">
  <div class="eyebrow">SMMO 社媒营销自动化平台</div>
  <h1>关键词搜索回复任务报告</h1>
  <div class="meta">
    <span class="pill status">状态：{status}</span>
    <span class="pill safe">{html.escape(send_mode)}</span>
    <span class="pill">执行：{execution_id}</span>
    <span class="pill">活动：{campaign_id}</span>
    <span class="pill">生成：{generated_at}</span>
  </div>
</div>
<section><h2>执行概览</h2><div class="grid">{''.join(_metric(label, value) for label, value in cards)}</div></section>
<div class="two">
  <section><h2>LLM 用量</h2><div class="grid">{''.join(_metric(label, value) for label, value in [('Prompt Token', summary.get('prompt_tokens')), ('Completion Token', summary.get('completion_tokens')), ('Total Token', summary.get('total_tokens'))])}</div></section>
  <section><h2>发送策略</h2><div class="grid">{''.join(_metric(label, value) for label, value in [('发送开关', send_mode), ('失败关键词', summary.get('failed_keywords')), ('运行目录数', summary.get('run_count'))])}</div></section>
</div>
<section><h2>关键词执行</h2>{_table(keywords, ['keyword','status','discovered_contents','scanned_comments','lead_candidates','prompt_tokens','completion_tokens','total_tokens','error_type'])}</section>
<section><h2>运行明细</h2>{_table(runs, ['run_id','keyword','status','login_state','scanned_contents','scanned_comments','lead_candidates','first_content_url'])}</section>
<section><h2>线索结果</h2>{_table(leads, ['author_name','final_intent_level','llm_confidence','comment_text','source_content_url']) if leads else '<div class="empty">本次没有入库线索。若候选线索大于 0 但入库为 0，请检查置信度阈值、去重规则和发送策略。</div>'}</section>
</main>
</body></html>"""


def _metric(key: str, value: Any) -> str:
    return f"<div class='metric'><div class='metric-label'>{html.escape(str(key))}</div><div class='value'>{html.escape(str(value))}</div></div>"


def _table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "<div class=\"empty\">暂无数据。</div>"
    head = "".join(f"<th>{html.escape(_zh_label(column))}</th>" for column in columns)
    body = []
    for row in rows:
        cells = []
        for column in columns:
            value = _short(_zh_value(row.get(column)))
            if column.endswith("_url") and value:
                safe = html.escape(value, quote=True)
                cells.append(f"<td><a href=\"{safe}\" target=\"_blank\" rel=\"noreferrer\">打开链接</a></td>")
            elif column == "comment_text":
                cells.append(f"<td class=\"comment\">{html.escape(value)}</td>")
            else:
                cells.append(f"<td>{html.escape(value)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


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
        "prompt_tokens": "Prompt Token",
        "completion_tokens": "Completion Token",
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


def _zh_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    values = {
        "completed": "已完成",
        "failed": "失败",
        "running": "运行中",
        "queued": "排队中",
        "cancelled": "已取消",
        "logged_in": "已登录",
        "login_required": "需要重新登录",
        "unknown": "未知",
        "high": "高意向",
        "medium": "中意向",
        "low": "低意向",
        "none": "无意向",
    }
    return values.get(value, value)


def _lead_count(report: dict[str, Any]) -> int:
    return sum(len(content.get("leads") or []) for content in report.get("contents") or [])


def _first_content_url(scan: dict[str, Any]) -> str | None:
    for item in scan.get("contents") or []:
        if item.get("url"):
            return str(item["url"])
    return None
