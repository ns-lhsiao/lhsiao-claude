#!/usr/bin/env python3
"""Escalation-risk design gate — Claude Code PostToolUse hook.

Fires when an SDD tool writes a *substantial* design artifact (OpenSpec proposal/
design, wb spec/dtc plan/design/spec, or a generic design.md / plan.md). It runs a
cheap deterministic keyword pre-scan for the escalation-risk categories and injects
a mandatory-review instruction (additionalContext) so Claude evaluates the design
against escalation-risk-checklist.md before implementation proceeds.

Design principles:
- Never break the developer's flow: any error/parse failure exits 0, silent.
- Fire on the first substantial version of a design and again only when its content
  materially changes (dedup by content hash), so it does not spam on tiny edits.
- The deterministic scan only produces *hints*; the actual judgment is the LLM's,
  against the full checklist.

Configuration via env vars (all optional):
  ESCALATION_CHECKLIST   path to the checklist md (default: ../escalation-risk-checklist.md)
  ESCALATION_MIN_WORDS   min word count to treat a doc as a "first version" (default: 150)
  ESCALATION_DESIGN_GLOBS  extra ':'-separated fnmatch globs counted as design artifacts
  ESCALATION_MARKER_DIR  where per-file review markers live (default: <cwd>/.escalation-hook)
"""
import os
import sys
import json
import re
import hashlib
import fnmatch

# --- Escalation-risk categories: trigger keywords + mitigation keywords ------
# If a category's triggers appear but none of its mitigations do, it is flagged
# ATTENTION. If both appear, it is NOTED (relevant and seemingly considered).
CATEGORIES = [
    ("C1", "Destructive op w/o guardrail / restore",
     ["delete", "remove", "purge", "reset", "overwrite", "revert", "switch mode",
      "change mode", "disable", "wipe", "drop", "刪除", "清除", "切換", "還原", "覆寫"],
     ["confirm", "confirmation", "type delete", "typed confirm", "soft delete",
      "undo", "restore", "backup", "recover", "二次驗證", "還原", "備份", "軟刪除", "blast radius"]),
    ("C2", "Unbounded bulk input / overload",
     ["csv", "upload", "import", "bulk", "batch", "file size", "上傳", "匯入", "批次"],
     ["max record", "record limit", "row limit", "max rows", "count limit", "max count",
      "pagination", "streaming", "chunk", "server-side limit", "筆數上限", "最大筆數", "分頁"]),
    ("C3", "Frontend validation gap -> 500",
     ["url", "email", "regex", "free text", "free-text", "input field", "form field",
      "hostname", "格式", "校驗", "表單欄位"],
     ["strict validation", "rfc", "field-level error", "field validation", "catch exception",
      "graceful", "structured error", "validate", "嚴格校驗", "欄位錯誤", "例外捕獲"]),
    ("C4", "Legacy schema / malformed response",
     ["legacy", "schema", "version", "migration", "backward", "empty array", "null",
      "activities", "parse json", "舊版", "相容", "遷移", "空陣列"],
     ["defensive default", "default value", "empty check", "null check", "single json",
      "well-formed", "fallback message", "handle empty", "防禦性", "容錯", "預設值"]),
    ("C5", "Cross-environment artifact bleed",
     ["banner", "announcement", "release note banner", "fedramp", "govcloud", "commercial",
      "environment", "compliance", "region", "橫幅", "公告", "環境", "合規"],
     ["environment gate", "env gate", "compliance gate", "gated by environment",
      "filter by environment", "環境判定", "環境過濾", "compliance attribute"]),
    ("C6", "Policy precedence / overlap",
     ["policy", "rule", "precedence", "priority", "evaluation order", "match", "predefined",
      "custom rule", "優先", "規則", "順序", "命中"],
     ["shadow", "shadowing", "conflict detection", "overlap detection", "visual order",
      "precedence indicator", "warning", "衝突偵測", "重疊", "優先權顯示"]),
    ("FF1", "Flag dependency deadlock",
     ["feature flag", "flag", "toggle", "phase", "旗標", "開關"],
     ["flag dependency", "co-required", "dependency set", "required flag", "explanatory error",
      "names the flag", "相依", "相依旗標", "依賴清單"]),
    ("FF2", "Release-notes GA vs flag reality",
     ["release note", "ga", "general availability", "announce", "marketed", "發布", "公告"],
     ["default enable", "default state", "default off", "default on", "per-tenant",
      "auto-enable", "lifecycle", "預設啟用", "預設狀態"]),
    ("FF3", "Multi-service / multi-flag coupling",
     ["ui flag", "backend flag", "two flags", "paired", "cross-service flag", "前後端旗標"],
     ["enabled together", "paired flag", "in pairs", "both flags", "sync toggle",
      "成對", "同步開啟", "一起啟用"]),
    ("WAD1", "UI exposes unsupported capability",
     ["unsupported", "not implemented", "not supported", "capability", "notification template",
      "user alert", "不支援", "未實作"],
     ["capability check", "gate on backend", "backend capability", "block combination",
      "compatibility check", "能力連動", "阻擋非法組合"]),
    ("WAD2", "Orphaned refs / split data source",
     ["autocomplete", "search users", "inventory", "deleted user", "scim", "group rename",
      "displayname", "搜尋", "群組改名", "離職"],
     ["single source", "source of truth", "referenced-but-inactive", "sync rename",
      "cross-service sync", "資料源一致", "同步改名"]),
    ("WAD3", "Data volume / memory / pagination",
     ["export", "download", "blob", "large", "csv export", "dropdown", "list", "limit 100",
      "匯出", "下載", "大量", "分頁"],
     ["stream", "streaming", "chunk", "pagination", "server-side search", "no hardcoded limit",
      "分頁", "串流", "伺服器端搜尋", "scale"]),
    ("WAD4", "Audit gaps / security-UX",
     ["token", "secret", "sensitive", "copy", "view token", "tooltip", "help text",
      "令牌", "敏感", "審計", "提示"],
     ["audit log", "audit event", "emit audit", "modify_time", "last edit", "accurate tooltip",
      "審計事件", "更新時間", "回寫"]),
    ("M1", "Cross-repo / cross-version release coordination",
     ["repo", "mf-client", "classic", "deploy", "release", "freeze", "依賴", "部署"],
     ["dependency map", "effective default", "deploy order", "timeline", "cross-repo",
      "跨 repo", "部署順序", "依賴分析"]),
    ("M2", "State desync / phantom pending changes",
     ["pending changes", "state machine", "apply changes", "diff", "sync state",
      "狀態機", "待部署", "同步"],
     ["reconcile", "reconciliation", "on read failure", "avoid phantom", "real diff",
      "狀態一致", "對帳", "避免假性"]),
    ("FE1", "Async state race / edit-time hydration failure",
     ["search", "typeahead", "autocomplete", "filter", "edit form", "edit mode", "rehydrat",
      "hydrat", "dropdown", "async", "搜尋", "編輯模式", "下拉", "非同步"],
     ["abort", "cancel", "latest-wins", "request id", "stale response", "debounce",
      "round-trip", "wait for options", "after options load", "取消請求", "過期回應", "競態"]),
    ("FE2", "Input sanitization / cross-DB case mismatch",
     ["domain", "hostname", "username", "user name", "group name", "trailing space",
      "whitespace", "case-sensitive", "case sensitive", "lowercase", "網域", "群組名稱",
      "使用者名稱", "大小寫", "空白"],
     ["trim", "sanitize", "sanitise", "normalize", "normalise", "case-insensitive",
      "case insensitive", "strip", "修剪", "清理", "正規化", "不分大小寫"]),
    ("FE3", "Silent drop / error swallowing / fake 200 OK",
     ["truncate", "silently", "max entries", "entry limit", "paste", "success message",
      "saved successfully", "toast", "status code", "200", "截斷", "靜默", "成功提示"],
     ["explicit error", "surface error", "show error", "reject with", "over-limit",
      "limit message", "http status", "4xx", "check payload", "顯示錯誤", "明確錯誤", "超出上限"]),
    ("FE4", "Type coercion / serialization / dedup / rendering",
     ["nan", "undefined", "tostring", "object object", "serialize", "query param", "limit=",
      "duplicate", "dedup", "tag", "chip", "badge", "重複", "序列化", "標籤"],
     ["isnan", "number.isfinite", "guard", "key-based merge", "dedupe", "deduplicate",
      "unique key", "virtual scroll", "virtualized", "collapse", "去重", "虛擬滾動", "折疊"]),
    ("RBAC1", "Custom-role undefined props / over-broad API permission",
     ["rbac", "custom role", "role", "permission", "privilege", "approval", "apply changes",
      "deploy endpoint", "admin scope", "角色", "權限", "審批", "自訂角色"],
     ["optional chaining", "permission check", "authorize", "authorization", "least privilege",
      "deploy permission", "apply permission", "approval flow", "default deny", "權限校驗",
      "最小權限", "審批流程"]),
    ("R1", "Downstream latency / cache miss -> whole-page timeout",
     ["microservice", "downstream", "redis", "cache", "feature flag matrix", "timeout", "504",
      "synchronous call", "swg-profile", "微服務", "快取", "逾時", "下游"],
     ["circuit breaker", "graceful degradation", "fallback", "timeout handling", "retry with backoff",
      "cache warm", "stampede", "partial page", "熔斷", "降級", "快取回填", "容錯"]),
]

# Paths (case-insensitive, posix) that count as SDD design artifacts.
DEFAULT_GLOBS = [
    # OpenSpec
    "*/openspec/changes/*/proposal.md",
    "*/openspec/changes/*/design.md",
    "*/openspec/*/design.md",
    # wb spec / dtc
    "*/specs/*/spec.md",
    "*/specs/*/design.md",
    "*/specs/*/plan.md",
    "*/design/*design*.md",
    # generic
    "*design.md",
    "*plan.md",
    "*hld.md",
    "*high-level-design.md",
    "*/design.md",
    "*/plan.md",
]
SKIP_DIR_PARTS = ("/node_modules/", "/.git/", "/dist/", "/build/", "/.next/", "/vendor/")


def log(msg):
    if os.environ.get("ESCALATION_HOOK_DEBUG"):
        sys.stderr.write("[escalation-hook] %s\n" % msg)


def is_design_artifact(path):
    p = path.replace("\\", "/")
    lp = p.lower()
    if not lp.endswith(".md"):
        return False
    if any(part in lp for part in SKIP_DIR_PARTS):
        return False
    globs = list(DEFAULT_GLOBS)
    extra = os.environ.get("ESCALATION_DESIGN_GLOBS", "")
    if extra:
        globs += [g for g in extra.split(":") if g]
    return any(fnmatch.fnmatch(lp, g.lower()) for g in globs)


def read_content(tool_input, path):
    # Write provides full content; Edit/MultiEdit may not — read from disk.
    content = tool_input.get("content")
    if isinstance(content, str) and content.strip():
        return content
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def prescan(text):
    low = text.lower()
    attention, noted = [], []
    for cid, name, triggers, mitigations in CATEGORIES:
        if not any(t.lower() in low for t in triggers):
            continue
        if any(m.lower() in low for m in mitigations):
            noted.append((cid, name))
        else:
            attention.append((cid, name))
    return attention, noted


def marker_path(path):
    d = os.environ.get("ESCALATION_MARKER_DIR") or os.path.join(os.getcwd(), ".escalation-hook")
    key = hashlib.sha1(path.encode("utf-8")).hexdigest()[:16]
    return d, os.path.join(d, "reviewed-%s.txt" % key)


def already_reviewed(path, content_hash):
    _, mp = marker_path(path)
    try:
        with open(mp, "r") as fh:
            return fh.read().strip() == content_hash
    except OSError:
        return False


def record_reviewed(path, content_hash):
    d, mp = marker_path(path)
    try:
        os.makedirs(d, exist_ok=True)
        with open(mp, "w") as fh:
            fh.write(content_hash)
    except OSError:
        pass


def checklist_path():
    env = os.environ.get("ESCALATION_CHECKLIST")
    if env and os.path.exists(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    guess = os.path.normpath(os.path.join(here, "..", "escalation-risk-checklist.md"))
    return guess


def build_context(path, attention, noted):
    lines = []
    lines.append("🛡️ ESCALATION-RISK DESIGN GATE — mandatory before implementation")
    lines.append("")
    lines.append("A first-draft design artifact was just written:")
    lines.append("  " + path)
    lines.append("")
    lines.append("Before proceeding, evaluate this design against the escalation-risk")
    lines.append("checklist (patterns distilled from real customer escalations):")
    lines.append("  " + checklist_path())
    lines.append("")
    if attention:
        lines.append("Deterministic pre-scan — categories that appear RELEVANT but whose")
        lines.append("safeguard is NOT mentioned in the design text (verify each):")
        for cid, name in attention:
            lines.append("  ⚠ %-5s %s" % (cid, name))
    if noted:
        lines.append("")
        lines.append("Pre-scan — relevant and seemingly considered (confirm depth):")
        for cid, name in noted:
            lines.append("  • %-5s %s" % (cid, name))
    if not attention and not noted:
        lines.append("Pre-scan found no obvious keyword signals — still do a judgment pass;")
        lines.append("the scan is heuristic and misses nuance.")
    lines.append("")
    lines.append("REQUIRED ACTION: Read the checklist, then output a verdict table with one")
    lines.append("row per topically-relevant category: category · ADDRESSED / GAP / N/A ·")
    lines.append("evidence or the missing requirement. Fold every GAP back into the design as")
    lines.append("an explicit requirement or open question. Do not silently pass the gate.")
    return "\n".join(lines)


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return 0

    if data.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return 0

    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("filePath") or ""
    if not path or not is_design_artifact(path):
        return 0

    text = read_content(tool_input, path)
    words = len(re.findall(r"\w+", text))
    min_words = int(os.environ.get("ESCALATION_MIN_WORDS", "150") or "150")
    if words < min_words:
        log("skip: only %d words (< %d), not a first version yet" % (words, min_words))
        return 0

    content_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()
    if already_reviewed(path, content_hash):
        log("skip: content unchanged since last review")
        return 0

    attention, noted = prescan(text)
    context = build_context(path, attention, noted)
    record_reviewed(path, content_hash)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never break the developer's flow
        log("unexpected error: %r" % exc)
        sys.exit(0)
