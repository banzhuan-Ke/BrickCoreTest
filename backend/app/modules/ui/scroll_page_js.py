"""页面滚动 evaluate 脚本（与 runner/WebEngine/scroll_page_js.py 保持同步，仅允许模块 docstring 差异）。

供 Backend page_fetcher 探页与 Runner kw_scroll 共用语义，避免双份漂移。
"""

SCROLL_PAGE_JS = """
([mode, value]) => {
  const num = (v, d) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : d;
  };
  const isScrollable = (el) => {
    if (!el) return false;
    const st = window.getComputedStyle(el);
    const oy = st.overflowY || st.overflow;
    if (!(oy === 'auto' || oy === 'scroll' || oy === 'overlay')) return false;
    return (el.scrollHeight - el.clientHeight) > 2;
  };
  const findScrollRoot = () => {
    const se = document.scrollingElement || document.documentElement;
    if (se && (se.scrollHeight - se.clientHeight) > 2) return se;
    if (document.body && (document.body.scrollHeight - document.body.clientHeight) > 2) {
      return document.body;
    }
    let best = null;
    let bestArea = 0;
    const nodes = document.querySelectorAll('div, main, section, article, aside, ul, ol, [class*="scroll"], [class*="content"]');
    for (const el of nodes) {
      if (!isScrollable(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 60 || r.height < 60) continue;
      // 优先视口内可见区域较大的容器
      const visibleH = Math.min(r.bottom, window.innerHeight) - Math.max(r.top, 0);
      const visibleW = Math.min(r.right, window.innerWidth) - Math.max(r.left, 0);
      if (visibleH < 40 || visibleW < 40) continue;
      const area = visibleW * visibleH;
      const room = el.scrollHeight - el.clientHeight;
      const score = area * Math.min(room, 4000);
      if (score > bestArea) {
        best = el;
        bestArea = score;
      }
    }
    return best || se || document.documentElement;
  };
  const root = findScrollRoot();
  const maxTop = Math.max(0, (root.scrollHeight || 0) - (root.clientHeight || 0));
  const before = root.scrollTop || 0;
  let target = before;
  if (mode === 'top') target = 0;
  else if (mode === 'bottom') target = maxTop;
  else if (mode === 'middle') target = Math.floor(maxTop / 2);
  else if (mode === 'down') target = Math.min(maxTop, before + Math.abs(num(value, 600)));
  else if (mode === 'up') target = Math.max(0, before - Math.abs(num(value, 600)));
  else if (mode === 'to') target = Math.max(0, Math.min(maxTop, num(value, 0)));
  else if (mode === 'xy') {
    const x = num(value && value.x, 0);
    const y = num(value && value.y, 0);
    if (typeof root.scrollLeft === 'number') root.scrollLeft = x;
    target = y;
  }
  root.scrollTop = target;
  if (root === document.documentElement || root === document.body || root === document.scrollingElement) {
    window.scrollTo(0, target);
  }
  return {
    before,
    after: root.scrollTop || 0,
    maxTop,
    moved: Math.abs((root.scrollTop || 0) - before) > 1,
    tag: root.tagName || '',
    id: root.id || '',
    className: ((root.className && root.className.toString) ? root.className.toString() : '').slice(0, 120),
  };
}
"""
