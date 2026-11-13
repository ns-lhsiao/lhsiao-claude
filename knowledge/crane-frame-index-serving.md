# `dist-frame/index.html` 是怎麼被回傳的

最後更新：2026-11-14。相關文件：[crane-webui2-render.md](crane-webui2-render.md)

這份文件說明全頁 React shell 的入口 HTML（`dist-frame/index.html`），從 build、放進 image、由 pod nginx 送出，一路到被 PHP / ms-bootstrap 代理、最後回給瀏覽器的完整路徑，以及 PR sidecar（`x-npe-env`）修正改了哪一段。

---

## 1. 總覽

```mermaid
flowchart LR
  subgraph Build["webui2 build（Dockerfile）"]
    SRC["apps/shell/index.html<br/>&lt;script src=/src/main.tsx&gt;"] -->|vite build<br/>PROD_PATH_PREFIX=/mf/shell| D1["dist/"]
    SRC -->|vite build<br/>PROD_PATH_PREFIX=/mf/frame<br/>OUT_DIR=dist-frame| D2["dist-frame/<br/>index.html 寫死 index-HASH.js"]
  end
  subgraph Image["webui2 image（/usr/share/nginx/html）"]
    D1 -->|COPY 後 rm index.html| I1["/ (= /mf/shell build)<br/>remoteEntry.js + assets"]
    D2 -->|COPY → /mf/frame| I2["/mf/frame/index.html"]
  end
  subgraph Pod["webui2 pod nginx（deploy/nginx/default.conf）"]
    I2 --> L155["location = /mf/frame/index.html"]
    I2 --> FB["location ^~ /mf/frame/<br/>→ @frame_fallback"]
  end
  L155 --> PHP["webui PHP Ns.php<br/>（非 cutover /ns）"]
  L155 --> MSB["ms-bootstrap<br/>（crane /ns）"]
  FB --> BR["瀏覽器直接打<br/>/mf/frame/&lt;route&gt;"]
  PHP --> U["瀏覽器"]
  MSB --> U
  BR --> U
```

---

## 2. Build：檔案從哪裡來

`webui2/Dockerfile`：

```dockerfile
# 同一份原始碼 build 兩次
RUN PUBLIC_PATH_PREFIX=/mf/shell pnpm --filter shell build:cdn                       # → dist/
RUN PUBLIC_PATH_PREFIX=/mf/frame PROD_PATH_PREFIX=/mf/frame OUT_DIR=dist-frame \
    pnpm --filter shell build:cdn                                                    # → dist-frame/

COPY --from=build-deps /usr/src/app/apps/shell/dist /usr/share/nginx/html
69: RUN rm /usr/share/nginx/html/index.html && rm -f /usr/share/nginx/html/50x.html   # 刪掉 dist/index.html（ENG-1000627）
72: COPY --chown=nginx:nginx --from=build-deps /usr/src/app/apps/shell/dist-frame /usr/share/nginx/html/mf/frame
```

- `dist-frame/index.html` 在 pod 裡的位置是 `/usr/share/nginx/html/mf/frame/index.html`，剛好對應 URL `/mf/frame/index.html`。
- `dist/index.html` 被刪掉了，所以 `/mf/shell` 不會回傳 HTML，只提供 `remoteEntry.js` 和 assets，給 Angular 嵌入用。

### index.html 裡的 hash 是怎麼寫進去的

```mermaid
flowchart TD
  A["apps/shell/index.html:146<br/>&lt;script type=module src=/src/main.tsx&gt;"] --> B["vite build（rolldown）<br/>從 main.tsx 打包 import graph<br/>依內容算 hash → index-praQZ3lv.js"]
  B --> C["vite.config.ts:41 base + :49-61 renderBuiltUrl()<br/>HTML 參照 → /mf/frame/assets/index-praQZ3lv.js"]
  C --> D["plugins.ts:736 cdnPlaceholderPlugin / patchProductionHtml()<br/>→ {{CDN_URL}}/mf/frame/assets/…<br/>→ 補上 nonce={{NONCE}}"]
  D --> E["dist-frame/index.html<br/>&lt;script nonce={{NONCE}} src={{CDN_URL}}/mf/frame/assets/index-praQZ3lv.js&gt;"]
```

hash 在 build 時就寫死了，main 和每個 PR sidecar 各自 build，hash 都不一樣。

---

## 3. Pod nginx：誰把檔案送出去

`webui2/deploy/nginx/default.conf`：

```nginx
33: sub_filter '{{CDN_URL}}' '';            # 同源，換成空字串
34: sub_filter '{{NONCE}}'   '$request_id';
35: sub_filter_once off;

155: location = /mf/frame/index.html {      # 指名要 index.html（PHP / ms-bootstrap 走這裡）
         add_header Cache-Control "no-cache, no-store, must-revalidate";
         try_files $uri =404;
     }

177: location ^~ /mf/frame/ {               # 其他 /mf/frame/* 路徑
178:     rewrite ^/mf/frame/(npe-[a-zA-Z0-9_-]+)(/.*)$ /mf/frame$2 last;   # 剝掉 sidecar 的 env 段
179:     try_files $uri $uri/ @frame_fallback;
     }

186: location @frame_fallback {             # 檔案不存在時
         if ($uri ~ "\.[^/]+$") { return 404; }   # 有副檔名 → 真正的 404（讓 edge fallback）
190:     rewrite ^ /mf/frame/index.html break;     # SPA route → 回 index.html
     }
```

```mermaid
flowchart TD
  R["request 進到 pod"] --> Q1{"路徑是<br/>/mf/frame/index.html？"}
  Q1 -- 是 --> L155["L155 = /mf/frame/index.html<br/>try_files → 回 index.html（no-cache）"]
  Q1 -- 否 --> L177["L177 ^~ /mf/frame/"]
  L177 --> Q2{"有 /mf/frame/npe-xxx/ 段？"}
  Q2 -- 是 --> STRIP["L178 剝掉 env 段，last 重新比對"] --> Q1
  Q2 -- 否 --> TF["L179 try_files $uri"]
  TF -- 檔案存在 --> FILE["回該檔案<br/>（assets 走 ^~ /mf/frame/assets/，1y immutable）"]
  TF -- 不存在 --> FBK["L186 @frame_fallback"]
  FBK --> Q3{"最後一段有副檔名？"}
  Q3 -- 有 --> E404["404（讓 edge fallback 回 main）"]
  Q3 -- 沒有 --> SPA["L190 rewrite → /mf/frame/index.html"]
  L155 --> SUB["sub_filter 換掉 {{NONCE}} / {{CDN_URL}}"]
  SPA --> SUB
```

---

## 4. 三條取得路徑

| 呼叫的人 | 什麼時候 | 抓的 URL | 命中 pod 的哪裡 | 怎麼回給瀏覽器 |
|---|---|---|---|---|
| **webui PHP**（非 cutover） | `/ns`，且 `NG_BALKAN_SHELL_ENABLED`、`isLoginComplete()`、`ngBalkanShellEnabled()` 都成立 | `REACT_SHELL_SERVICE . '/' . REACT_SHELL_INDEX_PATH` = `http://webui2.ngweb-v2/mf/frame/index.html` | L155 | `Ns::getBalkanShellHtml()` → `applySessionNonce()` → `Ns::index()` 的 `$this->output->set_output()` |
| **ms-bootstrap**（crane） | `/ns`，`ng_balkan_shell_enabled` 開 | `${REACT_SHELL_SERVICE}/${REACT_SHELL_INDEX_PATH}` | L155 | `getReactShellHtml()` 換掉 nonce → `root()` 的 `res.send()` |
| **瀏覽器直接打** | `/mf/frame/private-apps` 這類路徑 | edge `^/mf/(frame)(/\|$)` 轉送 | L177 → `@frame_fallback` → L190 | pod nginx 直接回（經過 edge） |

`REACT_SHELL_INDEX_PATH = 'mf/frame/index.html'` 在兩個 repo 都有定義：webui 在 `constants.php:1029`，ms-bootstrap 在 `general.constants.ts:26`。

### 4.1 非 cutover：webui PHP

```mermaid
sequenceDiagram
  autonumber
  participant B as 瀏覽器
  participant E as ngssl edge
  participant P as webui PHP Ns::index()
  participant W as webui2 pod (main)<br/>webui2.ngweb-v2
  B->>E: GET /ns（有 session）
  E->>P: $webui_pass（crane=0）
  P->>P: CF + isLoginComplete() + ngBalkanShellEnabled() 都成立
  P->>W: curl GET /mf/frame/index.html（fetchBalkanShell）
  W-->>P: index.html（L155，nonce=$request_id）
  P->>P: applySessionNonce()
  P-->>E: 200 HTML（index-HASH.js）
  E-->>B: 200 HTML
  B->>E: GET /mf/frame/assets/index-HASH.js …
```

### 4.2 crane：ms-bootstrap

```mermaid
sequenceDiagram
  autonumber
  participant B as 瀏覽器
  participant E as ngssl edge
  participant M as ms-bootstrap root()
  participant W as webui2 pod (main)<br/>REACT_SHELL_SERVICE
  B->>E: GET /ns
  E->>M: aws_nlb（crane=1，$crane_webui_proxy_pass）
  M->>M: globals.ng_balkan_shell_enabled = true
  M->>W: GET /mf/frame/index.html（getReactShellHtml）
  W-->>M: index.html（L155）
  M->>M: 換掉 nonce
  M-->>E: res.send(HTML)
  E-->>B: 200 HTML
```

### 4.3 瀏覽器直接打 `/mf/frame/<route>`

```mermaid
sequenceDiagram
  autonumber
  participant B as 瀏覽器
  participant E as ngssl edge
  participant W as webui2 pod
  B->>E: GET /mf/frame/private-apps
  E->>W: ^/mf/(frame)(/|$)（crane → aws_nlb；非 cutover → ngweb_mf）
  W->>W: L177 try_files 找不到 → @frame_fallback<br/>沒有副檔名 → L190 rewrite /mf/frame/index.html
  W-->>E: index.html
  E-->>B: 200 HTML
```

---

## 5. 帶 `x-npe-env` 時：修正前後

### 修正前：server 端固定抓 main

```mermaid
sequenceDiagram
  autonumber
  participant B as 瀏覽器（x-npe-env: npe-pr-3893）
  participant E as ngssl edge
  participant S as Ns.php / ms-bootstrap
  participant WM as webui2 main
  participant WS as webui2-npe-pr-3893（sidecar）
  B->>E: GET /ns + header
  E->>S: 轉送（header 有帶到）
  S->>WM: GET /mf/frame/index.html（沒看 header）
  WM-->>S: main index.html（index-MAIN.js）
  S-->>B: main HTML
  B->>E: GET /mf/frame/assets/route-bootstrap-MAIN.js + header
  E->>WS: rewrite → /mf/frame/npe-pr-3893/assets/route-bootstrap-MAIN.js
  WS-->>E: 404（sidecar 沒有 MAIN 的 hash）
  E->>WM: @crane_mf_npe_fallback（原路徑）
  WM-->>B: 200 main chunk（看起來正常，其實是 main）
```

### 修正後（webui#19476、ms-bootstrap#433）：server 端先抓 sidecar

```mermaid
sequenceDiagram
  autonumber
  participant B as 瀏覽器（x-npe-env: npe-pr-3893）
  participant E as ngssl edge
  participant S as Ns.php / ms-bootstrap
  participant WS as webui2-npe-pr-3893（sidecar）
  participant WM as webui2 main
  B->>E: GET /ns + header
  E->>S: 轉送
  S->>S: tenant ∈ NPE_SIDECAR_TENANT_DOMAINS？header 合法？已決定用 React？
  alt 都成立
    S->>WS: GET http://webui2-npe-pr-3893.ngweb-v2/mf/frame/index.html
    alt 200 且有內容
      WS-->>S: sidecar index.html（index-SIDECAR.js）
    else 錯誤 / 非 200 / 空內容
      S->>WM: GET http://webui2.ngweb-v2/mf/frame/index.html（照原本流程）
      WM-->>S: main index.html
    end
  else 不符合
    S->>WM: GET main（照原本流程）
    WM-->>S: main index.html
  end
  S-->>B: HTML（換掉 nonce）
  B->>E: GET /mf/frame/assets/route-bootstrap-SIDECAR.js + header
  E->>WS: rewrite → sidecar 有這個檔案 → 200 ✅
```

修正只改了第 4 節表格前兩列「抓的 URL」：從 `webui2.ngweb-v2` 換成 `webui2-<env>.ngweb-v2`。build（第 2 節）和 pod nginx（第 3 節）都沒有動。

---

## 6. 程式碼位置

| 位置 | 作用 |
|---|---|
| `webui2/Dockerfile:51,69,72` | build `dist-frame`；刪掉 `dist/index.html`；把 `dist-frame` COPY 到 `/mf/frame` |
| `webui2/apps/shell/index.html:146` | 原始入口 `<script src="/src/main.tsx">` |
| `webui2/apps/shell/vite.config.ts:41,49-61` | `base`、`renderBuiltUrl()` |
| `webui2/apps/shell/vite/env.ts:9-14,60` | `PROD_PATH_PREFIX` 只允許 `/mf/shell`、`/mf/frame` |
| `webui2/apps/shell/vite/plugins.ts:736-770` | `cdnPlaceholderPlugin` / `patchProductionHtml()` |
| `webui2/deploy/nginx/default.conf:33-35,155,177-190` | `sub_filter`；`= /mf/frame/index.html`；`^~ /mf/frame/`；`@frame_fallback` |
| `webui/.../controllers/Ns.php` `index()`、`getBalkanShellHtml()`、`fetchBalkanShell()` | 非 cutover 的 server 端代理 |
| `webui/.../config/constants.php:1028-1029` | `REACT_SHELL_SERVICE`、`REACT_SHELL_INDEX_PATH` |
| `ms-bootstrap/src/app.controller.ts` `root()`、`getReactShellHtml()` | crane 的 server 端代理 |
| `ms-bootstrap/src/constants/general.constants.ts:26` | `REACT_SHELL_INDEX_PATH` |

行號是依 webui2 `origin/master`、webui `develop`、ms-bootstrap `main` 在 2026-11-13～14 的版本。
