---
slug: policy-analyzer
title: Policy Analyzer (Analyze side panel)
nav: Policies > Real-time Protection > ANALYZE POLICIES
route: "#/inline-policy-page"
session: lrs-analyzer
kind: trigger-panel
renderer_matrix:
  - renderer: angular-shell + react-mf-cfw side panel
    when: "FF nplan6460_policy_analyzer_enabled AND CF NPLAN6460_POLICY_ANALYZER_ENABLED"
    present: ["ANALYZE POLICIES dropdown (Run Analyze, View Last Result)"]
    absent: []
flags:
  globals_regex: "nplan6460|policy_analyzer"
  balkan_keys: []
ff: [nplan6460_policy_analyzer_enabled]
cf: [NPLAN6460_POLICY_ANALYZER_ENABLED]
rbac_group: policy_analyzer
rbac_mock:
  readonly: "GET /api/v2/rbac/roles/me with apiGroup policy_analyzer = r"
  none: "GET /api/v2/rbac/roles/me -> {apiGroups: []} (group absent)"
probes:
  - /api/v2/policyanalyzer/analyze/last
  - path: /api/v2/policyanalyzer/analyze/history
    expect: {status: 404}
  - /api/v2/policyanalyzer/simulate/history
critical_probes:
  - /api/v2/policyanalyzer/analyze/last
side_effects:
  - {action: "Run Analyze (POST /analyze)", reversible: false, effect: "overwrites the tenant's last analysis result"}
blocked_cases:
  NM-03: "needs injected fixture F12 (page.route mock)"
  NM-05: "needs injected fixture F11 (page.route mock)"
  NM-06: "needs injected fixture F1 (page.route mock)"
  NM-07: "needs injected fixture F9 (page.route mock)"
  NM-10: "needs injected fixture F2/F4 (page.route mock)"
  NM-12: "needs injected fixture F5 (page.route mock)"
  NM-13: "needs injected fixture F5 (page.route mock)"
  NM-14: "needs injected fixture F7 (page.route mock)"
  NM-18: "needs injected fixture F6 (page.route mock)"
  RL-02: "needs injected fixture F3 (page.route mock)"
  RL-03: "needs injected fixture F1/F4 (page.route mock)"
  RL-04: "needs injected fixture F8 (page.route mock)"
  RL-07: "needs injected fixture F2 (page.route mock)"
  RL-08: "needs injected fixture F3 (page.route mock)"
  RL-09: "needs injected fixture F8 (page.route mock)"
  RL-10: "needs injected fixture F7 (page.route mock)"
  RL-15: "needs injected fixture F2 (page.route mock)"
  RL-17: "needs injected fixture F13 (page.route mock)"
  RL-18: "needs injected fixture F10 (page.route mock)"
  UI-04: "needs fault injection (DB insert failure)"
needs_design: {}
case_roles:
  UI-06: none
object_prefix: "(none: analysis results are not named objects)"
mutation:
  creates: true
  cleanup: "Run Analyze replaces the tenant's last result and cannot be reverted; run it once and record the new id."
apply_policy: none
open_questions:
  - "Runnability of NM-/RL- cases not in the fixture map was not audited case by case; treated RUNNABLE."
  - "legend counts vs API counts: invariant I3 says legend = per-category array lengths; 2026-10-14 probe saw OP 2 / Shadowed 3 vs API 4 / 4"
  - "policy_group_name/order empty in live API (RL-10, NM-14)"
last_verified: 2026-10-14
---

# Policy Analyzer (Analyze side panel)

Source: webui `inline-policy-page-v2.component.ts` mounts mf-cfw `AnalyzeSidePanel`. API family
`/api/v2/policyanalyzer/*`. Cases come from `all-html/nplan6460-traffic-simulator/qe-analyze-ui-testcases-zh.md`
(2026-10-14 rewrite: normalize + shadow relations); `qe_ref` is the QE plan case id. First live probe:
`all-html/nplan6460-traffic-simulator/analyze-live-probe-lhsiao-qa.html`.

## Cases

| ID | Title | Pri | Mutates | Baseline (last observed) | qe_ref |
|---|---|---|---|---|---|
| NM-01 | 成功 envelope | P0 | N | | E-07 |
| NM-02 | 錯誤方言 HTTP 200 | P0 | N | |  |
| NM-03 | 引擎 flat shape（目前 lhsiao.qa 真實回應） | P0 | N | | B-48 |
| NM-04 | `run_at` 型別 | P1 | N | |  |
| NM-05 | 計數欄位與陣列不一致 | P1 | N | | B-50 |
| NM-06 | Live 資料：OP + Shadowed 同一 policy | P0 | N | | B-50 |
| NM-07 | 三類別都有 | P1 | N | |  |
| NM-08 | 顯示欄位來源 | P1 | N | |  |
| NM-09 | 關係合併去重 | P0 | N | |  |
| NM-10 | `shadows` 與 `shadowed_by` 同時存在 | P0 | N | |  |
| NM-11 | 同 policy 在同類別重複出現 | P2 | N | |  |
| NM-12 | finding 缺 `policy_id` | P0 | N | |  |
| NM-13 | relation ref 缺 `policy_id` | P0 | N | |  |
| NM-14 | 空 `policy_group_name` / `group_order=0` | P1 | N | |  |
| NM-15 | 同名但不同 order 的群組 | P1 | N | |  |
| NM-16 | `policy_order` 重複或跨群組不連續 | P1 | N | |  |
| NM-17 | 欄位為 null / 缺漏 | P1 | N | |  |
| NM-18 | category 陣列整個缺席 | P0 | N | |  |
| NM-19 | 三個陣列都空 | P1 | N | |  |
| NM-20 | `enabled:false` | P1 | N | |  |
| RL-01 | 基本單向遮蔽 | P0 | N | | B-01 |
| RL-02 | 遮蔽者本身不是 finding | P0 | N | | B-01 |
| RL-03 | 多重遮蔽 | P0 | N | | B-06 |
| RL-04 | 對稱性（I5） | P0 | N | | B-48 |
| RL-05 | Over-permissive 的 `shadows` | P0 | N | | B-08 |
| RL-06 | Standalone OP 無關係 | P1 | N | | B-17 |
| RL-07 | 互相遮蔽（mutual） | P0 | N | |  |
| RL-08 | 指向不在 response 的 policy | P0 | N | |  |
| RL-09 | 關係不對稱的容忍 | P1 | N | |  |
| RL-10 | ref 身分欄位與 finding 本身不一致 | P1 | N | |  |
| RL-11 | 自我參照 | P1 | N | |  |
| RL-12 | 詳情面板 reason 方向對應 | P1 | N | |  |
| RL-13 | 卡片計數標籤 | P1 | N | |  |
| RL-14 | Focus 過濾 | P0 | N | |  |
| RL-15 | 連線箭頭方向與顏色 | P1 | N | |  |
| RL-16 | Legend 隨焦點重算 | P1 | N | |  |
| RL-17 | 20 張上限與關係 | P1 | N | |  |
| RL-18 | 單一 policy 遮蔽極多 | P1 | N | | B-52 |
| RL-19 | 搜尋與關係 | P2 | N | |  |
| UI-01 | 新分析重置焦點 | P1 | Y | |  |
| UI-02 | 連點 Run Analyze／latest-wins | P1 | Y | |  |
| UI-03 | View analysis（`GET /analyze/last`）與 Run 結果走同一條 normalize | P0 | N | | E-07 |
| UI-04 | 200 但未持久化 | P1 | N | | E-08 |
| UI-05 | 面板標題時間 | P2 | N | |  |
| UI-06 | 入口 gating（簡述） | P0 | N | | A-06, A-12 |
| UI-07 | Angular shell 內嵌 | P1 | N | |  |
