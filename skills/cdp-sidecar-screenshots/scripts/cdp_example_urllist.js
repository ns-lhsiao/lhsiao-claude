// Example flow: url-list page mutation-error toast on a PR sidecar. Generic
// template -- adapt selectors/navigation for the page being verified. Requires
// the CDP helper bundle "where the scripts live" (see SKILL.md).
const { attach, loginIfNeeded, gotoRoute, findToast, shot, interceptMutationError } = require(process.env.TOAST_LIB);

(async () => {
  const { page, session } = await attach();
  await loginIfNeeded(page, process.env.TU, process.env.TP);

  // Force the create-URL-list mutation to fail with validation_errors
  // (this is what makes the unified onError show a mutation-error toast).
  const mutated = await interceptMutationError(session, '*policy/urllist*', ['name']);
  await gotoRoute(page, 'url-list');
  await shot(page, 'url-list-loaded');

  // Open the New URL List dialog (retry: hash re-nav can leave the page mid-render)
  const btn = page.locator('[data-testid="new-url-list-btn"]').first();
  let opened = false;
  for (let i = 0; i < 3 && !opened; i++) {
    await btn.waitFor({ state: 'visible', timeout: 30000 });
    await btn.click();
    await page.waitForTimeout(1500);
    opened = await page.locator('[data-testid="url-list-name-input"]').first().isVisible().catch(() => false);
  }
  await shot(page, 'url-list-dialog');

  const nameInput = page.locator('[data-testid="url-list-name-input"]').first();
  await nameInput.waitFor({ state: 'visible', timeout: 15000 });
  await nameInput.click();
  await nameInput.fill('toast-verify-' + Date.now());
  const urlArea = page.locator('textarea').first();
  await urlArea.click();
  await urlArea.fill('www.example.com');
  await shot(page, 'url-list-filled');

  const save = page.locator('div[data-ntskui-portal] button:has-text("Save")').last();
  await save.click();
  await shot(page, 'url-list-after-save');
  console.log('mutation intercepted:', await mutated());

  const toast = await findToast(page, { re: /fail|error|failed|couldn|unable|invalid|duplicate|required|forced/i });
  console.log('TOAST:', JSON.stringify(toast));
  await shot(page, 'url-list-mutationerror');

  process.exit(0);
})().catch((e) => {
  console.error('ERR', e);
  process.exit(1);
});
