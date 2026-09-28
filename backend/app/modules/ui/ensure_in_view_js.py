"""元素智能进视口脚本（与执行器侧脚本保持同步，仅允许模块 docstring 差异）。

供 Backend page_fetcher 探页与 Runner 点击 / 滚动到元素 共用语义，避免双份漂移。

规则：
- 只滚最近的可滚动祖先（弹窗内列表），不连滚外层 / 整页
- 已在容器可视区内（含上下 pad）→ 不滚
- 否则做「最小位移」露出（带 pad），避免居中/贴顶导致滚过头被粘性头挡住
"""

ENSURE_IN_VIEW_SMART_JS = """
(el, opts) => {
  const pad = Math.max(0, Number((opts && opts.pad != null) ? opts.pad : 40) || 0);
  if (!el || typeof el.getBoundingClientRect !== 'function') {
    return { scrolled: false, reason: 'no_element', pad: pad };
  }

  const isDocRoot = (node) => {
    if (!node) return false;
    return (
      node === document.scrollingElement ||
      node === document.documentElement ||
      node === document.body
    );
  };

  const isScrollable = (node) => {
    if (!node || node.nodeType !== 1) return false;
    const room = (node.scrollHeight || 0) - (node.clientHeight || 0);
    if (room <= 2) return false;
    if (isDocRoot(node)) return true;
    const st = window.getComputedStyle(node);
    const oy = st.overflowY || st.overflow;
    return oy === 'auto' || oy === 'scroll' || oy === 'overlay';
  };

  const viewBox = (root) => {
    if (isDocRoot(root)) {
      return {
        top: 0,
        bottom: window.innerHeight || 0,
        left: 0,
        right: window.innerWidth || 0,
        isDoc: true,
      };
    }
    const r = root.getBoundingClientRect();
    return {
      top: r.top,
      bottom: r.bottom,
      left: r.left,
      right: r.right,
      isDoc: false,
    };
  };

  const findNearestScrollParent = (node) => {
    let p = node.parentElement;
    while (p) {
      if (isScrollable(p)) return p;
      p = p.parentElement;
    }
    const se = document.scrollingElement || document.documentElement;
    if (se && isScrollable(se)) return se;
    return null;
  };

  const fullyIn = (er, vb, edgePad) => {
    if (!(er && er.height > 0 && er.width > 0)) return false;
    return (
      er.top >= vb.top + edgePad &&
      er.bottom <= vb.bottom - edgePad
    );
  };

  const root = findNearestScrollParent(el);
  if (!root) {
    return { scrolled: false, reason: 'no_scroll_parent', pad: pad };
  }

  const er0 = el.getBoundingClientRect();
  const vb0 = viewBox(root);
  if (fullyIn(er0, vb0, pad)) {
    return {
      scrolled: false,
      reason: 'already_visible',
      pad: pad,
      roots: [],
    };
  }

  const before = root.scrollTop || 0;
  const maxTop = Math.max(0, (root.scrollHeight || 0) - (root.clientHeight || 0));
  let delta = 0;
  // 最小位移：上方被挡 → 往上挪一点；下方看不见 → 往下挪一点（带 pad）
  if (er0.top < vb0.top + pad) {
    delta = er0.top - (vb0.top + pad);
  } else if (er0.bottom > vb0.bottom - pad) {
    delta = er0.bottom - (vb0.bottom - pad);
  } else {
    // 宽高异常等：退回相对容器中线微调
    const elMid = er0.top + er0.height / 2;
    const viewMid = (vb0.top + vb0.bottom) / 2;
    delta = elMid - viewMid;
  }

  const next = Math.max(0, Math.min(maxTop, before + delta));
  root.scrollTop = next;
  if (vb0.isDoc) {
    try { window.scrollTo(0, root.scrollTop); } catch (e) {}
  }

  // 若仍贴顶被挡，再补一次向下回拉（粘性头 / 过冲）
  const er1 = el.getBoundingClientRect();
  const vb1 = viewBox(root);
  if (er1.top < vb1.top + pad) {
    const fix = er1.top - (vb1.top + pad);
    root.scrollTop = Math.max(0, Math.min(maxTop, (root.scrollTop || 0) + fix));
    if (vb1.isDoc) {
      try { window.scrollTo(0, root.scrollTop); } catch (e) {}
    }
  }

  const after = root.scrollTop || 0;
  const scrolled = Math.abs(after - before) > 1;
  return {
    scrolled: scrolled,
    reason: scrolled ? 'minimal' : 'already_visible',
    pad: pad,
    roots: scrolled ? [String(root.tagName || '').toLowerCase()] : [],
  };
}
"""
