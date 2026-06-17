"""Audit frontend ActionGroup keywords vs Runner KeywordRegistry."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runner"))

from WebEngine.basecase import KeywordRegistry  # noqa: E402

ag = (ROOT / "frontend/src/datas/ActionGroup.js").read_text(encoding="utf-8")
pairs = re.findall(r"keyword:\s*'([^']+)',\s*\n\s*method:\s*\"([^\"]+)\"", ag)
frontend = dict(pairs)

missing = []
method_only = []
ok = []
for kw, method in frontend.items():
    has_kw = bool(KeywordRegistry.get_handler(kw))
    has_method = bool(KeywordRegistry.get_handler(method))
    if has_kw:
        ok.append((kw, method))
    elif has_method:
        method_only.append((kw, method))
    else:
        missing.append((kw, method))

print(f"total={len(frontend)} ok={len(ok)} method_only={len(method_only)} missing={len(missing)}")
print("\n-- method_only (need Chinese alias) --")
for x in method_only:
    print(x)
print("\n-- missing --")
for x in missing:
    print(x)
