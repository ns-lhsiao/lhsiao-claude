// CDP sidecar screenshot helper library. Generalized from a toast-verification
// spike. Nothing here is machine-specific -- configure via env (see SKILL.md):
// CDP_URL, CDP_PORT, BASE, SHOTS, X_NPE_ENV.
const { chromium } = require('@playwright/test');

const CDP_URL = process.env.CDP_URL || `http://localhost:${process.env.CDP_PORT || 9222}`;
const BASE = process.env.BASE;
const SHOTS = process.env.SHOTS;
const X_NPE_ENV = process.env.X_NPE_ENV;

// Default toast-keyword list -- single source of truth for "what a toast looks
// like". Consumers pass a narrower `re` to exclude success toasts.
const DEFAULT_TOAST_RE =
  /fail|error|failed|couldn|unable|invalid|duplicate|forced|success|saved|deleted|created|updated|applied|submitted|restored|uploaded|sent|moved/i;

function requireEnv(name) {
  throw new Error(`Set ${name} first (see SKILL.md env table):  ${name} was not provided.`);
}

// Attach to a real (headed) Chrome over CDP, pick the tenant origin tab, and set
// the sidecar header via CDP session (NOT context-level headers -- see SKILL.md).
async function attach() {
  const base = BASE || requireEnv('BASE');
  const header = X_NPE_ENV || requireEnv('X_NPE_ENV');
  const origin = new URL(base).origin;
  const browser = await chromium.connectOverCDP(CDP_URL);
  const ctx = browser.contexts()[0];
  const pages = ctx.pages();

  const isTenant = (p) => {
    try {
      return new URL(p.url()).origin === origin;
    } catch (e) {
      return false;
    }
  };

  // dedicated tab: one carrying OUR tab marker in sessionStorage, else the first
  // tenant-origin tab (cdp_login.js uses pages()[0], so they stay in sync)
  let page = pages.find(isTenant);
  for (const p of pages) {
    if (!isTenant(p)) continue;
    try {
      const mine = await p.evaluate(() => sessionStorage.getItem('cdp-sidecar-owner'));
      if (mine === 'sidecar-screenshots') { page = p; break; }
    } catch (e) {}
  }
  if (!page) throw new Error(`No tab on ${origin} under ${CDP_URL} -- open one in the debug Chrome first`);
  if (!(await page.evaluate(() => sessionStorage.getItem('cdp-sidecar-owner')).catch(() => null))) {
    try { await page.evaluate(() => sessionStorage.setItem('cdp-sidecar-owner', 'sidecar-screenshots')); } catch (e) {}
  }
  await page.bringToFront();

  const session = await ctx.newCDPSession(page);
  await session.send('Network.enable');
  await session.send('Network.setExtraHTTPHeaders', { headers: { 'x-npe-env': header } });
  return { page, session };
}

// Perform the tenant shell login. Shared by loginIfNeeded and the one-off
// cdp_login.js so selectors/timeouts live in exactly one place.
async function performLogin(page, user, pass) {
  const u = page.locator('[data-testid=login-username] input');
  await u.waitFor({ state: 'visible', timeout: 60000 });
  await u.fill(user);
  await page.locator('[data-testid=login-password] input').fill(pass);
  await page.locator('#btn-sign-in').click();
  await page.waitForFunction(() => location.href.includes('/ns#/') && !location.href.includes('/login'), { timeout: 60000 });
}

// Login only if the page is on the login screen, then wait for the shell chrome
// (bounded, event-driven -- not a fixed sleep). user/pass passed explicitly so
// credentials never live in this repo.
async function loginIfNeeded(page, user, pass) {
  if (!page.url().includes('/login') && page.url().includes('/ns')) return;
  await page.goto(BASE || requireEnv('BASE'), { waitUntil: 'domcontentloaded' });
  await performLogin(page, user, pass);
  await page
    .waitForFunction(() => {
      const t = document.body.innerText || '';
      return t.length > 800 && /Settings|Dashboard|Reports/i.test(t);
    }, { timeout: 60000 })
    .catch(() => {});
  await page.waitForTimeout(1500); // settle after sidecar boot
}

// Navigate via full reload to the hash route. Plain location.hash navigation is
// unreliable after an MFE remount; full reload remounts cleanly. Waits until the
// loading screen is gone AND body content is past the shell chrome.
async function gotoRoute(page, route) {
  const clean = route.replace(/^#?\/?/, '');
  await page.goto(`${BASE || requireEnv('BASE')}/ns#/${clean}`, { waitUntil: 'domcontentloaded' });
  await page
    .waitForFunction(() => {
      const t = document.body.innerText || '';
      return !/LOADING/i.test(t) && t.length > 800;
    }, { timeout: 60000 })
    .catch(() => {});
}

// Poll DOM for a toast-like element: innerText matches + reasonable size.
// Sonner toasts are classless <li>s, so match on text + bounding rect.
async function findToast(page, { timeout = 20000, re } = {}) {
  const rx = re || DEFAULT_TOAST_RE;
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const res = await page.evaluate(
      (src) => {
        const rx = new RegExp(src, 'i');
        const els = [...document.querySelectorAll('li,div,section')];
        const out = [];
        for (const el of els) {
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.width < 500 && r.height > 20 && r.height < 200) {
            const txt = (el.innerText || '').trim();
            if (txt && txt.length < 300 && rx.test(txt)) {
              out.push({ text: txt.slice(0, 120), x: r.x, y: r.y, w: r.width, h: r.height, iw: innerWidth, ih: innerHeight });
            }
          }
        }
        return out;
      },
      rx.source
    );
    if (res.length) {
      const t = res[0];
      const cx = t.x + t.w / 2;
      const zoneX = cx < t.iw / 3 ? 'left' : cx > (2 * t.iw) / 3 ? 'right' : 'center';
      const zoneY = t.y < 0.2 * t.ih ? 'top' : t.y > 0.8 * t.ih ? 'bottom' : 'middle';
      return { ...t, position: `${zoneY}-${zoneX}` };
    }
    await page.waitForTimeout(400);
  }
  return null;
}

// Force a mutation API to return 400 so the app's validation-error toast fires.
// url-list's unified onError needs the validation_errors shape; a plain
// {"message": "..."} body is swallowed and shows nothing. `pattern` is a CDP
// Fetch glob that gates the URL; the listener only narrows by HTTP method (Fetch
// patterns cannot express method). Disables itself after the first mutation.
async function interceptMutationError(session, pattern, fields) {
  const body = Buffer.from(
    JSON.stringify({ validation_errors: fields.map((f) => ({ field: f, error: 'forced validation failure' })) })
  ).toString('base64');
  await session.send('Fetch.enable', { patterns: [{ urlPattern: pattern, requestStage: 'Request' }] });
  let mutated = false;
  const handler = async (ev) => {
    const req = ev.request;
    if (/post|put|delete/i.test(req.method)) {
      mutated = true;
      await session
        .send('Fetch.fulfillRequest', {
          requestId: ev.requestId,
          responseCode: 400,
          responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
          body,
        })
        .catch(() => {});
      await session.send('Fetch.disable').catch(() => {});
      session.off('Fetch.requestPaused', handler);
    } else {
      await session.send('Fetch.continueRequest', { requestId: ev.requestId }).catch(() => {});
    }
  };
  session.on('Fetch.requestPaused', handler);
  return () => mutated;
}

async function shot(page, name) {
  await page.screenshot({ path: `${SHOTS || requireEnv('SHOTS')}/${name}.png`, fullPage: false });
}

module.exports = { attach, loginIfNeeded, performLogin, gotoRoute, findToast, interceptMutationError, shot, CDP_URL };
