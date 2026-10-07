() => {
  const g = (window.ns && window.ns.globals) || {};
  const re = new RegExp('__PATTERN__', 'i');
  const out = {};
  Object.keys(g).filter(k => re.test(k)).forEach(k => { out[k] = g[k]; });
  return JSON.stringify(out);
}
