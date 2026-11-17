# Sidecar 特例：ms-bootstrap（crane `/ns` 產生者）

最後更新：2026-11-17。通則：[sidecar.md](sidecar.md)。webui2 側：[sidecar-webui2.md](sidecar-webui2.md)。

---

## 1. 角色

crane cutover 租戶（`/etc/nginx/crane_tenants.map`）的 `/ns` 不經 webui PHP：ngssl `$crane_webui_proxy_pass` → `aws_nlb` → ms-bootstrap `AppController.root()`。它**取代** `Ns.php`，不是接在 webui 後面。

| 條件 | 結果 |
|---|---|
| `globals.ng_balkan_shell_enabled` 開（**不檢查登入狀態**，跟 Ns.php 不同） | `getReactShellHtml()` 抓 `${REACT_SHELL_SERVICE}/${REACT_SHELL_INDEX_PATH}`（`mf/frame/index.html`），換 nonce → React；失敗 503 |
| flag 關 | `getAngularIndexScripts()` 抓 `${ANGULAR_UI_SERVICE}/ng/dist/prod-lazy/angular_view.txt` 套 `index` template → Angular |

`/ns` 的 HTML 由 server 決定 → 跟 Ns.php 一樣是 `x-npe-env` 的例外（server 端 fetch 不帶 header）。

## 2. 修正（ms-bootstrap#433，ENG-1419882，2026-11-17 merged）

跟 webui#19476 同一套規則，只有 tenant 來源不同：
1. `req.tenantUrl`（`tenant-info.middleware.ts` 從 core DB `uiHostname` 填）後綴比對 `NPE_SIDECAR_TENANT_DOMAINS`（`['qa.boomskope.com']`）。
2. `x-npe-env` 符合 `NPE_ENV_HEADER_PATTERN`。
3. 已決定走 React。

sidecar URL：`REACT_SHELL_SERVICE` host 第一段加 `-<env>`。200 且非空才用，否則 main。

**crane 路徑可以端到端**：瀏覽器後續 `/mf/frame/assets/<sidecar hash>.js` 經 `aws_nlb` → AWS ALB → **webui2 AWS leg** 的 `/mf/frame/<suffix>` rule → 200。前提是該 PR 的 **AWS leg 有部署**（webui2 `cicd-pr.yaml` 的 `publish_manifest_sidecar_aws`）；只有 MP leg 時 crane 租戶看不到 sidecar。

flag 關（Angular）時帶 header 仍是 Angular —— 這正是不用 nginx bypass 的理由。

## 3. 為什麼不用 nginx 繞過（service#111366，open，**不 merge**）

#111366 讓 edge 對帶 header 的 crane `/ns` 直接拿 `/mf/frame/<env>/index.html`，跳過 ms-bootstrap：
- nginx 讀不到 tenant DB 的 `ng_balkan_shell_enabled` → flag 關的租戶帶 header 會被強制變 React。
- #433 的程式永遠跑不到；沒有 domain 限制。
- 在 `/ns` location 宣告 `error_page` 會讓它**不再繼承** server 層的 `error_page`（maintenance、507、404），影響所有租戶。

## 4. qa01 ngssl 狀態備忘

- 2026-11-12 的 `/ns` hotfix 已還原；`aws_crane/webui_route_mappings.conf` = service `develop`。殘留備份 `.broken-20261112101409`、`.hotfix-v1-20261112103605` 可在 #433 live 驗證後清。
- `aws_crane/upstream_map_definition.conf` 另有 ENG-1421154 reporting cutover 的 map（備份 `.erased-202611131357`），不是我們的。
- 這台 VM（`ngsslwebui01`）服務**所有** qa01 租戶：先備份 → `sudo nginx -t -c /etc/nginx/nginx-sslwebui.conf`（要帶 `-c`）→ 協調後 `sudo supervisorctl signal HUP nginx`。`tsh ssh` profile 過期會無聲 hang，先 `timeout 20 tsh status`。

## 5. 開發坑

- `.env.test` 的 `REACT_SHELL_SERVICE="localhost"` 不是合法 URL；spec 要在 `beforeEach` 覆寫成真 URL、`afterEach` 還原。
- flag cache 是 request-scoped（`TenantDbFactory` `Scope.REQUEST`，scope 往上傳染）→ 改 flag 不用重啟 pod。
- 相關檔案：`src/app.controller.ts`、`src/common/npe-sidecar.ts`、`src/constants/general.constants.ts`、`src/.../tenant-info.middleware.ts`。
- OpenSpec：`pr-deployment-exp/openspec/specs/ms-bootstrap-react-shell-npe-sidecar/`；`changes/ns-npe-sidecar-crane-routing/` 待 live 驗證後以 superseded archive。
- **未確認**：ms-bootstrap 自己的 PR 能不能用 sidecar 測（`/ns` 不經 api-gateway，Kong host rewrite 不適用）。需要時先查它的 deploy 方式，不要假設。
