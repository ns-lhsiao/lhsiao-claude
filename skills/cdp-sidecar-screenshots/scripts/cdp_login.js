// One-off login helper for a fresh CDP Chrome profile. Thin wrapper over the
// lib's shared login flow -- username/password come from the environment
// (TU/TP), never from the repo.
const { chromium } = require('@playwright/test');
const { CDP_URL, loginIfNeeded } = require(process.env.TOAST_LIB || '../scripts/cdp_toast_lib.js');

const TU = process.env.TU;
const TP = process.env.TP;

if (!TU || !TP) {
  console.error('Set TU, TP first (see SKILL.md).');
  process.exit(1);
}

(async () => {
  const browser = await chromium.connectOverCDP(CDP_URL);
  const ctx = browser.contexts()[0];
  const page = ctx.pages()[0] || (await ctx.newPage());
  await page.goto(process.env.BASE, { waitUntil: 'domcontentloaded' }).catch(() => {});
  await loginIfNeeded(page, TU, TP);
  console.log('after login url:', page.url());
  await page.screenshot({ path: `${process.env.SHOTS || '/tmp'}/after-login.png`, fullPage: false });
  console.log('LOGIN_DONE');
  process.exit(0);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
