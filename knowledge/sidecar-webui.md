# Sidecar 特例：webui（PHP + Angular neo）

最後更新：2026-11-17。通則：[sidecar.md](sidecar.md)。

---

## 1. webui 本身不走 ngweb-v2 sidecar

webui（PHP BFF + Angular neo）不是 `ngweb-v2` 的 Helm release，沒有 `webui-npe-<suffix>`。測 webui PR 的方式是 **qa01 parallel namespace `rtp-XX`**：
- 部署：`/qa01-parallel-namespace-deploy`（`bot-deploy-pns-rtp-XX` 分支 → Jenkins）。`pns_deploy.py verify` 要帶補零的 `--namespace 05`。
- 路由：**依 tenant hostname 綁定**（ngssl `webui_proxy_rtpXX.nginx.conf` 的 `server_name` regex），不是 header。`/qa01-parallel-namespace-routing`。改的是服務全 qa01 的共用 nginx。
- `x-pns-env` header gate（rtp05）目前只是 proposal（`pr-deployment-exp/openspec/changes/rtp05-x-pns-env-gate`），不要當現況。

所以 `x-npe-env` 對 webui 自己的 PHP/Angular 程式碼**沒有作用**。

## 2. webui 在別人 sidecar 裡扮演的角色

| webui 元件 | 對 sidecar 的影響 |
|---|---|
| Angular neo 載入 mf（`remoteEntry.js`） | 瀏覽器經 ngssl `~ .*remoteEntry.js$` → path rewrite → **一般 mf sidecar 都 ✅**。webui2 `/mf/shell/remoteEntry.js` 也是（情境 ①），除非 `balkan_s3_cloudfront_url` 是 CloudFront |
| Angular 呼叫 `/api/v2/*` | 經 api-gateway → Kong host rewrite → **ms sidecar ✅** |
| Angular 呼叫 PHP API（`/ns/.+` 等） | 打 webui PHP，沒有 sidecar 概念 |
| `Ns::index()` 產生 `/ns`（非 cutover 租戶） | **特例**：flag 開時 server 端 curl webui2 frame `index.html` → 見下節 |

## 3. `Ns.php` 的 `/ns`（webui#19476，2026-11-17 merged）

非 cutover 租戶，`NG_BALKAN_SHELL_ENABLED` && `isLoginComplete()` && `ngBalkanShellEnabled()` 時，`getBalkanShellHtml()` curl `REACT_SHELL_SERVICE/REACT_SHELL_INDEX_PATH`（`http://webui2.ngweb-v2/mf/frame/index.html`），換 session nonce 後回給瀏覽器。抓失敗回 503，**不退回 Angular**（避免 reload 迴圈）。其他狀況（未登入、MFA、TOS、flag 關）→ `neo_view` Angular。Angular 登入後 `LoginService.loadPostAuthConfigs()` 看到 flag → `replaceState('/ns#<target>')` + `reload()`，第二次 `/ns` 才變 React（Angular → frame handoff）。

修正前 server 不看 header → 永遠 main。修正後三個條件都成立才先抓 sidecar：
1. `$_SERVER['HTTP_HOST']`（去 port、不分大小寫）等於或以 `.<domain>` 結尾，domain ∈ `NPE_SIDECAR_TENANT_DOMAINS`（`['qa.boomskope.com']`；開 stg 就加 `stg.boomskope.com`）。
2. `x-npe-env` 符合 `NPE_ENV_HEADER_PATTERN`（同 edge regex），且 `webui2-<env>` 是合法 RFC 1123 label。
3. 原本判斷已決定用 React。

sidecar URL：`REACT_SHELL_SERVICE` host 第一段加 `-<env>` → `http://webui2-npe-pr-3893.ngweb-v2`。sidecar 200 且非空才用，否則照原流程抓 main；main 也失敗才 503。nonce 檢查、metrics 不變。

**⚠️ 還不能端到端用**：server 拿到 sidecar HTML 後，瀏覽器要的 sidecar frame 資產在非 crane 路徑會打到 main → 白頁。要等 webui2#4282（MP sidecar 的 `/mf/frame/<suffix>` Ingress）。詳見 [sidecar-webui2.md](sidecar-webui2.md) §2。

## 4. 相關檔案

- `controllers/Ns.php`：`index()`、`getBalkanShellHtml()`、`fetchBalkanShell()`、`applySessionNonce()`
- `config/constants.php`：`REACT_SHELL_SERVICE`、`REACT_SHELL_INDEX_PATH`、`NPE_SIDECAR_TENANT_DOMAINS`、`NPE_ENV_HEADER_PATTERN`
- 測試：`tests/controllers_no_db/ns/nsTest.php`
- OpenSpec：webui `openspec/specs/balkan-shell-npe-sidecar/`

## 5. 坑

- webui PHP 改動想用 header 測 → 沒用，去 rtp-XX。
- 在 ngssl `/ns/.+` 加 npe rewrite 會弄壞 post-auth API。
- 本地 devbox 測不到 sidecar 路由（沒有 ngssl / Kong）；sidecar 只能在 qa01 真租戶驗。
