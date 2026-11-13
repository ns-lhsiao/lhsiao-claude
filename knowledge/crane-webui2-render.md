# Crane / webui2 渲染與 x-npe-env sidecar 整理

最後更新：2026-11-14。對應 ticket：ENG-1419054、ENG-1419882、ENG-1419883。

本文整理 webui2 是怎麼被載入、渲染出來的，以及 PR sidecar（`x-npe-env`）在各條路徑上能不能生效、原因是什麼、修在哪裡。

---

## 1. 一句話結論

**決定跑哪個 webui2 build 的，是「第一個沒有 hash 的檔案」由誰提供。**

之後所有檔名都帶 hash，這些 hash 在 build 時就已經寫死，只會指向同一份 build 的其他檔案。`x-npe-env` 只會改變「去哪裡拿檔案」（edge 把路徑 rewrite 到 sidecar），不會改變「要拿哪個檔名」。

---

## 2. 三個獨立的層次（不要混在一起看）

| 層次 | 問題 | 答案 |
|---|---|---|
| Hosting | 流量送去哪裡？ | ngssl 依 `$crane_tenant` 分流（`map $host` ← `/etc/nginx/crane_tenants.map`）。crane=1 → AWS NLB；crane=0 → qa01（PHP / ngweb_mf） |
| HTML 產生者 | 誰產生 `/ns` 的 HTML？ | 非 cutover：webui PHP `Ns::index()`；crane cutover：ms-bootstrap `AppController.root()` |
| Shell | 最後是誰在掌控頁面？ | Angular shell（webui neo）或 React shell（webui2 frame） |

- ms-bootstrap **不是接在 webui 後面**，它是 crane 租戶用來**取代** webui PHP、負責產生 `/ns` 的服務。
- `/mf/frame` **不是 crane 專用**，它就是 webui2 獨立 React shell 的 build。crane config 會特別為它寫 location，只是因為 crane 租戶的 frame 由 AWS 提供。

---

## 3. webui2 的兩份 build

同一份原始碼 build 兩次（`webui2/Dockerfile`）：

```dockerfile
RUN PUBLIC_PATH_PREFIX=/mf/shell pnpm --filter shell build:cdn                       # → dist/
RUN PUBLIC_PATH_PREFIX=/mf/frame PROD_PATH_PREFIX=/mf/frame OUT_DIR=dist-frame \
    pnpm --filter shell build:cdn                                                    # → dist-frame/
```

| build | URL 前綴 | 用途 | 備註 |
|---|---|---|---|
| `dist` | `/mf/shell/*` | Module Federation remote，給 Angular 嵌入 | image 裡刪掉了 `index.html`，Angular host 是唯一的入口（ENG-1000627） |
| `dist-frame` | `/mf/frame/*` | 獨立 React shell，有自己的 `index.html` | ms-bootstrap / Ns.php 代理的就是這份 |

**一句話記法**：
- `dist/index.html` 在 production 用不到，image 裡已經刪掉，只用 `remoteEntry.js` 和 assets。Angular 會把 `<balkan-shell>` 嵌進頁面，這是 **embedded** 模式：React 只渲染頁面內容，外框由 Angular 負責。
- `dist-frame/index.html` 就是全頁 React shell 的入口：`main.tsx` → `setShellMode('standalone')`，TopBar、Sidebar、router、auth 都由 React 負責。`dist-frame/remoteEntry.js` 雖然存在，但沒人用。
- 兩份是同一份原始碼，只有寫死的路徑前綴不同。standalone 和 embedded 是 runtime 依入口決定的模式，不是兩份不同的程式。

---

## 4. `/ns` HTML → JS 的載入鏈

### 4.1 每一層都寫死了下一層的檔名

```
/ns                                   ← 檔名固定，沒有 hash
 └─ HTML 裡寫死：<script src="/mf/frame/assets/index-praQZ3lv.js">
     └─ index-praQZ3lv.js 裡寫死：import "./route-bootstrap-5gvgmIXt.js"
         └─ route-bootstrap-5gvgmIXt.js 裡寫死：import "./dashboard-D0vFlrRg.js" …
```

main 和每個 PR sidecar 都是各自 build 的，hash 完全不同。main 的 `index-*.js` 只會去要 main 的 chunk，不可能去要 sidecar 的 chunk。

### 4.2 帶 hash 的 `<script>` 是怎麼產生的（webui2 原始碼）

1. **原始碼只有入口**：`apps/shell/index.html:146` → `<script type="module" src="/src/main.tsx"></script>`
2. **`vite build`** 從 `main.tsx` 開始打包整個 import graph，依每個 chunk 的內容算出 hash，再把 `src` 換成 `index-<hash>.js`。chunk 之間的 `import` 也是這時候寫進 JS 的。這是 Vite（rolldown）內建的行為，repo 裡沒有自己寫這段。
3. **前綴**：
   - `apps/shell/vite/env.ts:9-14,60`：`PROD_PATH_PREFIX` 只允許 `/mf/shell` 或 `/mf/frame`。
   - `apps/shell/vite.config.ts:41`：`base: ${env.pathPrefix}/`。
   - `vite.config.ts:49-61`：`renderBuiltUrl()` 把 HTML/CSS 的參照輸出成 `${prodPathPrefix}/${filename}`；JS 的動態 import 改成 runtime 運算式 `(window.__CDN_URL__||"")+"/mf/frame/…"`。
4. **build 後處理**：`apps/shell/vite/plugins.ts:736-770` 的 `cdnPlaceholderPlugin` / `patchProductionHtml()`：
   - `"/mf/frame/assets/…"` → `"{{CDN_URL}}/mf/frame/assets/…"`
   - `<script type="module" crossorigin` → 補上 `nonce="{{NONCE}}"`
   - Module Federation 的 `hostInit-<hash>.js` 也在這個階段注入。
5. **serve 時 pod 端 nginx 換掉 placeholder**：`webui2/deploy/nginx/default.conf:33-35`
   ```nginx
   sub_filter '{{CDN_URL}}' '';            # 同源，換成空字串
   sub_filter '{{NONCE}}'   '$request_id';
   ```
6. PHP 或 ms-bootstrap 抓回這份 HTML 後，再把 nonce 換成 session 的 nonce，配合 CSP header。

### 4.3 `x-npe-env` 改變的只有「去哪裡拿」

```
瀏覽器要  /mf/frame/assets/route-bootstrap-5gvgmIXt.js
edge 改成 /mf/frame/npe-pr-3893/assets/route-bootstrap-5gvgmIXt.js   ← 換地方拿，檔名不變
sidecar 沒有這個 hash → 404 → @crane_mf_npe_fallback → main → 200
```

拿個比喻來說：HTML 是印好的菜單，上面寫著 A 廚房的菜號；header 只是叫你改去 B 廚房點菜。B 廚房沒有 A 的菜號，就把你轉回 A 廚房。

---

## 5. 兩種 HTML，差別在 hash 寫在哪裡

| | React shell HTML（frame `index.html`） | Angular HTML（`neo_view` / ms-bootstrap Angular template） |
|---|---|---|
| HTML 裡有沒有 webui2 的 hash | **有**，直接寫死 `index-<hash>.js` | **沒有** |
| webui2 的 hash 從哪來 | HTML 本身 | 瀏覽器執行到 Angular 時，才去抓 `${balkan_s3_cloudfront_url}/mf/shell/remoteEntry.js`（檔名固定、no-cache），hash 寫在這個檔案裡 |
| 第一個沒有 hash 的檔案 | `/ns` | `/mf/shell/remoteEntry.js` |
| 誰去拿這個檔案 | **server**（Ns.php / ms-bootstrap curl `webui2.ngweb-v2`） | **瀏覽器**（帶 header，經過 edge） |
| 修正前 header 有沒有效 | ❌ | ✅（同源時） |

---

## 6. `/ns` 的 shell 判斷

| 租戶 | 產生者 | 條件 | 結果 | 出處 |
|---|---|---|---|---|
| 非 cutover | webui PHP `Ns::index()` | `NG_BALKAN_SHELL_ENABLED` 且 `isLoginComplete()` 且 `ngBalkanShellEnabled()` | server 端 curl `http://webui2.ngweb-v2/mf/frame/index.html`，換 nonce → **React**；抓失敗回 503，不會退回 Angular（避免 reload 無限循環） | webui#19174（ENG-1356940，2026-11-03） |
| 非 cutover | 同上 | 其他情況（還沒登入、MFA、TOS、flag 關） | `neo_view` → **Angular** | `Ns.php` |
| crane | ms-bootstrap `root()` | `globals.ng_balkan_shell_enabled`（**不檢查登入狀態**） | 抓 `${REACT_SHELL_SERVICE}/mf/frame/index.html`，換 nonce → **React**；失敗回 503 | `app.controller.ts:42-53, getReactShellHtml()` |
| crane | 同上 | flag 關 | 抓 `${ANGULAR_UI_SERVICE}/ng/dist/prod-lazy/angular_view.txt`，套進 `index` template → **Angular** | `getAngularIndexScripts()` |

非 cutover 租戶登入後，Angular 的 `LoginService.loadPostAuthConfigs()` 看到 flag 開著，會 `history.replaceState('/ns#<target>')` 再 `location.reload()`，這次 PHP 就改回 React。這就是常說的「Angular shell → frame handoff」。

---

## 7. 四種主要組合與 sidecar 支援

|  | HTML 產生者 = PHP | HTML 產生者 = ms-bootstrap |
|---|---|---|
| **shell = Angular** | ① 非 cutover，flag 關 → ✅ | ③ crane，flag 關 → ✅ |
| **shell = React** | ② 非 cutover，flag 開 → 修正前 ❌，ENG-1419883 / webui#19476 | ④ crane，flag 開 → 修正前 ❌，ENG-1419882 / ms-bootstrap#433 |

- ① ③：瀏覽器自己去抓 `/mf/shell/remoteEntry.js`，請求帶著 header，經過 ngssl 的 generic block。⚠️ 如果 `balkan_s3_cloudfront_url` 是 CloudFront 網址，請求不經過 ngssl，sidecar 也會失效（qa01 的實際值還沒確認）。
- ② ④：入口 hash 寫在 server 端 curl 回來的 HTML 裡，server 沒帶 header，所以固定拿到 main。
- 直接打 `/mf/frame/<route>`：沒有經過 server 端代理，edge 的 `^/mf/(frame)` rewrite 會拿到 sidecar 的 `index.html`，兩種租戶都 ✅。

### 情境 ② 走一次（以 `npe-pr-3893`、`/ns#/private-apps` 為例）

1. 登入前打 `/ns`：ngssl → `$webui_pass` → `Ns::index()`，`isLoginComplete()=false` → Angular 登入頁。
2. 在 Angular 登入 → `reloadIntoBalkanShell()` → `replaceState('/ns#/private-apps')` + `reload()`。
3. 再打 `/ns`：三個條件都成立 → `getBalkanShellHtml()` curl `webui2.ngweb-v2/mf/frame/index.html`。**沒帶 header、直接打 main 的 Service** → 拿到 main 的 HTML（`route-bootstrap-5gvgmIXt`）。**sidecar 在這一步失效。**
4. 瀏覽器照 main 的 hash 抓 asset → edge rewrite 到 sidecar → 404 → fallback → main → 200。
5. 頁面完全正常，但跑的是 main。

對照：直接打 `/mf/frame/private-apps` 就會拿到 sidecar 的 `route-bootstrap-DvgR58Nj`。

---

## 8. ngssl edge（qa01 `ngsslwebui01`）的分流

### 8.1 crane 相關的 map（`aws_crane/upstream_map_definition.conf`）

| 變數 | crane=1 | crane=0 | 用在 |
|---|---|---|---|
| `$crane_webui_proxy_pass` | `http://aws_nlb` | `$webui_pass` | `/ns`、`/login`、`/ng/`、靜態檔 |
| `$crane_mf_proxy_pass` | `http://aws_nlb` | `$ngweb_mf_pass` | `/mf/frame/*` |
| `$crane_mf_host_header` | `$http_host` | `ngweb-fe` | `/mf/frame/*` |
| `$mp_webui_proxy_pass` | api-gateway | `$webui_pass` | `/ns/.+`（post-auth API） |

`x-npe-env` 先經過 `webui_proxy.nginx.conf` L187 的 map 驗證（`^npe-[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$`），格式不對就是空字串。

### 8.2 location 比對順序（main server block）

| 順序 | 來源 | Location | npe rewrite | 404 fallback |
|---|---|---|---|---|
| L919 | `ngweb_mf_route_mappings.conf` | `~ ^/mf/(frame)/remoteEntry\.js$`、`build-info`、`~ ^/mf/(frame)(/\|$)` | ✅ | ✅ `@crane_mf_npe_fallback` |
| L985 | `webui_proxy.nginx.conf` | `~ .*remoteEntry.js$`（shell 和其他 MF） | ✅ | ✅ `@mf_npe_fallback` |
| L1062 | `webui_proxy.nginx.conf` | `~ ^/mf` | ✅ | ✅ |
| L1208 | `webui_route_mappings.conf` L19 | `~ ^/ns/?$`（**入口 HTML**） | ❌ 不需要（改由產生者處理） | — |

crane 的 `/mf/frame` block 對**所有 tenant** 都生效，非 cutover 租戶也會進這個 block，只是 map 會把它導回 `ngweb_mf`。

### 8.3 pod 端（webui2 `deploy/nginx/default.conf`）

- `^~ /mf/frame/` L178：把 `/mf/frame/npe-*/` 剝掉，用 `last` 重新比對 location。
- `@frame_fallback`：路徑最後一段有副檔名就回真正的 404（讓 edge fallback）；沒有副檔名就回 SPA 的 `index.html`。
- `^~ /mf/shell/`：同樣會剝掉 npe 段落。

---

## 9. 修正方案（已送 PR）

兩個 repo 用同一套規則，只有下面三個條件都成立時才先去抓 sidecar：
1. tenant host 等於 `NPE_SIDECAR_TENANT_DOMAINS`（目前是 `['qa.boomskope.com']`）中的某一項，或以 `.<該項>` 結尾。用的是後綴比對、不分大小寫、會先去掉 port。之後要開放 stg，加一項 `'stg.boomskope.com'` 就好。
   - webui 讀 `$_SERVER['HTTP_HOST']`（`NS_Loader` 用它查 tenant DB）。
   - ms-bootstrap 讀 `req.tenantUrl`（`tenant-info.middleware.ts` 從 core DB 的 `uiHostname` 填入）。
2. `x-npe-env` 符合 `NPE_ENV_HEADER_PATTERN`，跟 edge 用的 regex 相同。
3. 原本的 shell 判斷已經決定要用 React。

sidecar 的 URL 由 `REACT_SHELL_SERVICE` 推出來：把 host 第一段加上 `-<env>`，例如 `http://webui2.ngweb-v2` → `http://webui2-npe-pr-3893.ngweb-v2`。這對應 webui2 sidecar chart 的 `fullnameOverride: "webui2-{{ SUFFIX }}"`，跟 main 在同一個 namespace。server 是直接打 Service，所以 qa01 sidecar 雖然沒有 `/mf/frame` ingress（刻意關掉的），也不影響。

sidecar 回 200 而且有內容就用它；否則照原本的流程抓 main。只有 main 也失敗時才回 503。shell 判斷、nonce、metrics 都維持原樣。

| Repo | PR | Ticket | 主要檔案 |
|---|---|---|---|
| webui | netSkope/webui#19476 → `develop` | ENG-1419883 | `controllers/Ns.php`、`config/constants.php`、`tests/controllers_no_db/ns/nsTest.php` |
| ms-bootstrap | netSkope/ms-bootstrap#433 → `main` | ENG-1419882 | `src/app.controller.ts`、`src/common/npe-sidecar.ts`、`src/constants/general.constants.ts` |
| service | netSkope/service#111366（draft，**不 merge**，已被 #433 取代） | ENG-1419054 | `aws_crane/webui_route_mappings.conf`、`upstream_map_definition.conf` |

測試結果：webui PHPUnit `nsTest.php` 99/99、`controllers_no_db` 0 failure；ms-bootstrap jest 230/230，改動的檔案 coverage 100%。

### 為什麼不用 nginx 繞過（#111366）

#111366 在 edge 讓帶 header 的 crane `/ns` 直接去抓 `/mf/frame/<env>/index.html`，跳過 ms-bootstrap。問題有：
- nginx 讀不到 tenant DB 裡的 `ng_balkan_shell_enabled`，所以 ③（flag 關）帶 header 時會**被強制切成 React**。
- ms-bootstrap#433 的程式碼會永遠執行不到。
- 沒有 domain 限制。
- 如果在 `/ns` 裡宣告 `error_page`，該 location 會**不再繼承** server 層級的 `error_page`（maintenance 頁、507、404），影響所有租戶。所以拆分版才把 npe 邏輯移到 internal location `/__ns_npe_frame`。

---

## 10. qa01 ngssl 目前狀態（2026-11-14）

- hotfix **已被還原並生效**（不是我們做的，建議跟做 ENG-1421154 的人確認）：
  - `aws_crane/webui_route_mappings.conf` 跟 service `develop` 版本相同（md5 `787b9ca0`），2026-11-12 13:59 改回。
  - `aws_crane/upstream_map_definition.conf` 的 `$ns_frame_npe_env` map 已刪除。2026-11-13 14:07 另外加了 **ENG-1421154 reporting cutover** 的 map，改動前的備份是 `.erased-202611131357`。
  - 實測：cpcs-auth-3 帶 `x-npe-env: npe-pr-4071` 打 `/ns`，回的是 main `index-praQZ3lv`；sidecar 是 `index-DjRXN8tB`。
- 所以**在 ms-bootstrap#433 部署之前，crane 的 `/ns` 不會吃 sidecar**；直接打 `/mf/frame/<route>` 還是可以。
- 殘留的備份檔：`webui_route_mappings.conf.broken-20261112101409`、`.hotfix-v1-20261112103605`，可以在 #433 驗證完後清掉。
- 這台 VM 服務**所有** qa01 租戶。改動前一定要先備份，再跑 `sudo nginx -t -c /etc/nginx/nginx-sslwebui.conf`（要帶 `-c`），reload（`sudo supervisorctl signal HUP nginx`）前要先協調。

---

## 11. 驗證方法

### 在 DevTools 看「第一個沒有 hash 的檔案」

| 看到的 | 代表 |
|---|---|
| `/ns` document response 裡有 `/mf/frame/assets/index-*.js` | React shell（②④）。hash 是 server 決定的 |
| `/ns` 是 Angular，之後才載 `/mf/shell/remoteEntry.js` | Angular 嵌入（①③） |
| `route-bootstrap-*.js` 的 URL 是 `/mf/shell/assets/…` | ①③ |
| `route-bootstrap-*.js` 的 URL 是 `/mf/frame/assets/…` | ②④ |
| `ns.globals.balkan_s3_cloudfront_url` 不是空值 | ① 走 CDN，sidecar 不會生效 |

第一個對了，後面全部都會對；第一個錯了，後面每個請求就算都帶了 header 也沒用。

### curl

```bash
H=https://cpcs-auth-3.qa.boomskope.com
curl -s "$H/ns" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1                               # main
curl -s -H 'x-npe-env: npe-pr-4071' "$H/ns" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1   # 修正部署後應該不同
curl -s -H 'x-npe-env: npe-pr-4071' "$H/mf/frame/index.html" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1  # sidecar 本身
curl -s -H 'x-npe-env: npe-pr-4071' "$H/mf/frame/build-info.json"                             # deploymentSuffix
```

### 部署後的驗收清單

- 非 cutover `*.qa.boomskope.com`、flag 開：`/ns` 帶 header → sidecar；不帶 → main；`npe-foo` → main。
- crane `*.qa.boomskope.com`、flag 開：同上。
- crane、flag 關、帶 header → 仍然是 Angular。
- 非 qa 網域的租戶帶 header → 不受影響。

---

## 12. 踩過的坑

- **zsh 的 `curl ${h:+-H "$h"}`**：zsh 不做 word split，整串會變成一個參數，送出去的 header 開頭多了空格，nginx 回 `400 Bad Request`。這讓我們一度以為是 nginx 間歇性回 400。請用 array：`args=(-H "$h"); curl "${args[@]}"`。
- **zsh `$R:apps/...`**：`:a` 會被當成 modifier。請寫成 `"${R}:apps/..."`。
- **本機 checkout 過期**：本機 webui2 的 master 比 origin 落後 50 個 commit，導致第一版的 render-flow 報告有錯（embedded fixture、LD stage、pinger 的 method）。引用前先 `git fetch`，對照 `origin/master`。
- **`/ns` 和 `/ns/.+` 不要搞混**：`/ns/.+` 是 post-auth API（`getStaticGlobals` 等），在那裡加 rewrite 會讓 API 壞掉。
- **ms-bootstrap `.env.test`**：`REACT_SHELL_SERVICE="localhost"` 不是合法 URL，spec 裡要在 `beforeEach` 覆寫成真實 URL、在 `afterEach` 還原。
- **ms-bootstrap 的 flag cache 是 request-scoped**：`TenantDbFactory` 是 `Scope.REQUEST`，scope 會往上傳染，所以改 flag 不需要重啟 pod。

---

## 13. 相關文件

- [crane-frame-index-serving.md](crane-frame-index-serving.md)：`dist-frame/index.html` 從 build、pod nginx 到 PHP / ms-bootstrap / 瀏覽器的回傳路徑（含流程圖）
- `all-html/eng-1419054-ns-npe-sidecar/crane-asset-routing-explainer.html`：crane asset routing 講解
- `all-html/eng-1419054-ns-npe-sidecar/webui2-render-modes.html`：渲染模式總覽表
- `all-html/eng-1419054-ns-npe-sidecar/ns-shell-npe-sidecar-webui-msb.html`：webui + ms-bootstrap 修正 report
- `all-html/webui2-render-flow/webui2-render-flow.html`：完整的渲染流程（已對照 `origin/master` 修訂）
- OpenSpec：webui `openspec/specs/balkan-shell-npe-sidecar/`；global `pr-deployment-exp/openspec/specs/ms-bootstrap-react-shell-npe-sidecar/`；`changes/ns-npe-sidecar-crane-routing/`（還沒 archive，等 #433 驗證後以 superseded archive）
