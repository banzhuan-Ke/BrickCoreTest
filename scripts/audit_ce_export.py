#!/usr/bin/env python3
"""
Audit Pro -> CE export: forbidden leaks, sensitive paths, user-facing wording.

Usage:
  python scripts/audit_ce_export.py --pro-root .          # before sync (simulated CE docs)
  python scripts/audit_ce_export.py --ce-root ../fastapi-ui-ce  # after sync

Exit 0 = pass; 1 = blocking issues; 2 = warnings only (use --strict to fail on warnings).
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Mirrors scripts/sync-to-ce.ps1 exclusions (directory prefix or exact file, use /)
EXCLUDE_DIRS = {
    "runner",
    ".git",
    ".cursor",
    ".qoder",
    ".idea",
    ".githooks",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    "__pycache__",
    "scripts/.cache",
    "runner_client/dist",
    "runner_client/build",
    "runner_client/venv",
    "frontend/node_modules",
    "frontend/dist",
    "backend/venv",
    "runner/browsers",
    "runner/venv",
    "runner/logs",
    "docs",
}

EXCLUDE_FILES = {
    "scripts/build_runner_client.ps1",
    "scripts/migrate_to_test_catalog.py",
    "scripts/update_resume_2026.py",
    "scripts/reset-local-docker.ps1",
    "scripts/verify_runner_dist.ps1",
    "backend/static/runner/BrickCoreRunner.zip",
    "backend/check_migration.py",
    "backend/check_migration2.py",
    "backend/test_stream_debug.py",
    "import_ui_case.py",
    "restart-all.bat",
    "restart-dev.bat",
    "restart-fix.bat",
    "start-all.bat",
    "start-all-safe.bat",
    "start-local-simple.bat",
    "start-services-wsl.bat",
    "deploy-to-server.bat",
    "deploy-windows.bat",
    "deploy-frontend.bat",
    "deploy-frontend.sh",
    "deploy.sh",
    "upload-redis-image.bat",
}

EXCLUDE_PATTERNS = [
    re.compile(r"^runner_client/upload.*\.bat$", re.I),
    re.compile(r"^runner_client/upload-server.*\.bat$", re.I),
]

# CE stub overlays applied by sync-to-ce.ps1 (dest relative to repo root -> stub under scripts/ce-stubs)
CE_DOC_STUBS: dict[str, str] = {
    "docs-site/index.md": "scripts/ce-stubs/docs-index-ce.md",
    "docs-site/guide/highlights.md": "scripts/ce-stubs/docs-highlights-ce.md",
    "docs-site/guide/ui-automation.md": "scripts/ce-stubs/docs-ui-automation-ce.md",
    "docs-site/guide/runner-packaging.md": "scripts/ce-stubs/docs-runner-packaging-ce.md",
    "docs-site/guide/system-admin.md": "scripts/ce-stubs/docs-system-admin-ce.md",
    "docs-site/guide/data-factory.md": "scripts/ce-stubs/docs-data-factory-ce.md",
    "docs-site/guide/runner-linux-server.md": "scripts/ce-stubs/docs-runner-linux-server-ce.md",
}

CE_ROOT_FILES_FROM_STUBS = {
    "README.md": "docs/其他文档/README-CE.template.md",
    "runner/README.md": "scripts/ce-stubs/runner-README.md",
    "runner_client/README.md": "scripts/ce-stubs/runner-client-README.md",
    "LICENSE-RUNNER.md": "scripts/ce-stubs/LICENSE-RUNNER.md",
}

MUST_NOT_EXIST_IN_CE = [
    "runner/WebEngine",
    "docs",
    "scripts/build_runner_client.ps1",
    "backend/static/runner/BrickCoreRunner.zip",
    "backend/app/core/qa_judge_prompt.py",
]

# User-facing copy must not mention edition split (help center / Gitee / showcase).
FORBIDDEN_DOC_TERMS = [
    re.compile(r"社区版"),
    re.compile(r"商业版"),
    re.compile(r"Pro\s*版"),
    re.compile(r"\bCE\s*版\b"),
    re.compile(r"community\s+edition", re.I),
]

# In user-facing docs/README only — Pro devs may mention build script in internal comments.
FORBIDDEN_DOC_EXTRA = [
    re.compile(r"build_runner_client\.ps1"),
]

USER_DOC_GLOBS = [
    "docs-site/**/*.md",
    "scripts/ce-stubs/**/*.md",
    "showcase/docs/content/*.md",
    "showcase/README.md",
    "runner/README.md",
    "runner_client/README.md",
    "README.md",
]

USER_UI_GLOBS = [
    "runner_client/app/**/*.py",
    "frontend/src/**/*.vue",
    "frontend/src/**/*.js",
]

# Code paths where edition terms in comments/docstrings are OK (not shown in UI/docs center).
EDITION_TERM_ALLOW_PATHS = {
    "backend/app/core/edition.py",
    "backend/app/core/docs_catalog.py",
    "scripts/audit_ce_export.py",
    "scripts/sync-to-ce.ps1",
    "scripts/publish-ce.ps1",
    "scripts/verify-ce-sync.ps1",
}

SENSITIVE_PATTERNS = [
    (re.compile(r"runner[/\\]WebEngine"), "runner engine source path"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "possible API key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "possible AWS key"),
]


@dataclass
class Finding:
    level: str  # error | warn
    category: str
    path: str
    detail: str


@dataclass
class AuditReport:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, category: str, path: str, detail: str) -> None:
        self.findings.append(Finding(level, category, path, detail))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warn"]


def norm_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_excluded(rel: str) -> bool:
    rel_norm = rel.replace("\\", "/")
    for d in EXCLUDE_DIRS:
        if rel_norm == d or rel_norm.startswith(d + "/"):
            return True
    if rel_norm in EXCLUDE_FILES:
        return True
    for pat in EXCLUDE_PATTERNS:
        if pat.match(rel_norm):
            return True
    return False


def iter_sync_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = norm_rel(p, root)
        if is_excluded(rel):
            continue
        out.append(p)
    return sorted(out)


def resolve_ce_doc_path(pro_root: Path, rel: str) -> Path | None:
    """Effective docs-site file after CE stub overlay."""
    stub = CE_DOC_STUBS.get(rel.replace("\\", "/"))
    if stub:
        p = pro_root / stub
        return p if p.is_file() else None
    p = pro_root / rel
    return p if p.is_file() else None


def scan_forbidden_terms(text: str, path: str, *, include_build_script: bool) -> list[str]:
    hits: list[str] = []
    patterns = list(FORBIDDEN_DOC_TERMS)
    if include_build_script:
        patterns.extend(FORBIDDEN_DOC_EXTRA)
    for line_no, line in enumerate(text.splitlines(), 1):
        for pat in patterns:
            if pat.search(line):
                hits.append(f"L{line_no}: {line.strip()[:120]}")
    return hits


def audit_must_not_exist(ce_root: Path, report: AuditReport) -> None:
    for rel in MUST_NOT_EXIST_IN_CE:
        p = ce_root / rel.replace("/", "\\")
        if p.exists():
            report.add("error", "leak", rel, "must not exist in CE export")


def audit_webengine_leak(root: Path, report: AuditReport, *, label: str) -> None:
    we = root / "runner" / "WebEngine"
    if we.is_dir():
        report.add("error", "leak", str(we), f"{label}: runner/WebEngine must not be exported")


def audit_sync_exclusions(pro_root: Path, report: AuditReport) -> None:
    for rel in MUST_NOT_EXIST_IN_CE:
        p = pro_root / rel.replace("/", "\\")
        if p.exists() and not is_excluded(rel):
            report.add(
                "error",
                "exclude-config",
                rel,
                "exists in Pro but is NOT in sync exclude list — update sync-to-ce.ps1",
            )


def audit_user_docs(pro_root: Path, report: AuditReport, *, simulate_ce: bool) -> None:
    checked: set[str] = set()

    if simulate_ce:
        for dest_rel, stub_rel in CE_DOC_STUBS.items():
            src = pro_root / stub_rel
            if not src.is_file():
                report.add("error", "stub-missing", stub_rel, f"CE doc stub missing for {dest_rel}")
                continue
            text = src.read_text(encoding="utf-8")
            for hit in scan_forbidden_terms(text, dest_rel, include_build_script=True):
                report.add("error", "wording", dest_rel, hit)
            checked.add(dest_rel)

        for dest_rel, src_rel in CE_ROOT_FILES_FROM_STUBS.items():
            src = pro_root / src_rel
            if not src.is_file():
                report.add("warn", "stub-missing", src_rel, f"template/stub missing for {dest_rel}")
                continue
            text = src.read_text(encoding="utf-8")
            for hit in scan_forbidden_terms(text, dest_rel, include_build_script=dest_rel.endswith(".md")):
                report.add("error", "wording", dest_rel, hit)

    for pattern in USER_DOC_GLOBS:
        for p in pro_root.glob(pattern):
            if not p.is_file():
                continue
            rel = norm_rel(p, pro_root)
            if is_excluded(rel):
                continue
            if simulate_ce and rel in checked:
                continue
            if simulate_ce and rel in CE_ROOT_FILES_FROM_STUBS:
                continue
            if simulate_ce and rel.startswith("docs-site/") and rel in CE_DOC_STUBS:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            include_build = rel.endswith(".md") and "scripts/" not in rel
            for hit in scan_forbidden_terms(text, rel, include_build_script=include_build):
                if simulate_ce and rel.startswith("docs-site/guide/") and rel not in CE_DOC_STUBS:
                    report.add(
                        "warn",
                        "wording-pro-only",
                        rel,
                        f"{hit} (not stubbed; OK in Pro, fix stub if this page is synced as-is)",
                    )
                else:
                    report.add("error", "wording", rel, hit)


def audit_user_ui_strings(pro_root: Path, report: AuditReport) -> None:
    for pattern in USER_UI_GLOBS:
        for p in pro_root.glob(pattern):
            if not p.is_file():
                continue
            rel = norm_rel(p, pro_root)
            if is_excluded(rel) or rel in EDITION_TERM_ALLOW_PATHS:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            for pat in FORBIDDEN_DOC_TERMS:
                for m in pat.finditer(text):
                    snippet = text[max(0, m.start() - 40) : m.end() + 40].replace("\n", " ")
                    report.add("error", "wording-ui", rel, f"...{snippet}...")


def audit_sensitive_content(root: Path, report: AuditReport, files: list[Path] | None = None) -> None:
    paths = files if files is not None else iter_sync_files(root)
    root = root.resolve()
    for p in paths:
        rel = norm_rel(p, root)
        if not rel.endswith((".py", ".md", ".vue", ".js", ".ts", ".json", ".yml", ".yaml", ".env", ".sql", ".bat", ".ps1")):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat, label in SENSITIVE_PATTERNS:
            if pat.search(text) and "audit_ce_export" not in rel:
                if label == "runner engine source path" and (
                    rel.startswith("scripts/") or rel.endswith("edition.py") or rel.endswith("docs_catalog.py")
                ):
                    continue
                if label == "runner engine source path" and rel == "runner_client/app/settings_dialog.py":
                    continue
                report.add("warn", "sensitive", rel, f"matched {label}")


def audit_ce_root(ce_root: Path, report: AuditReport) -> None:
    if not ce_root.is_dir():
        report.add("error", "path", str(ce_root), "CE root directory not found")
        return
    audit_must_not_exist(ce_root, report)
    audit_webengine_leak(ce_root, report, label="CE tree")
    audit_user_docs(ce_root, report, simulate_ce=False)
    audit_user_ui_strings(ce_root, report)
    audit_sensitive_content(ce_root, report)


def audit_pro_export(pro_root: Path, report: AuditReport) -> None:
    audit_sync_exclusions(pro_root, report)
    audit_user_docs(pro_root, report, simulate_ce=True)
    audit_user_ui_strings(pro_root, report)
    sync_files = iter_sync_files(pro_root)
    audit_sensitive_content(pro_root, report, sync_files)
    # Simulated: no WebEngine copy
    if (pro_root / "runner" / "WebEngine").is_dir() and not is_excluded("runner"):
        report.add("warn", "exclude-config", "runner/", "entire runner/ excluded — OK if WebEngine stays in Pro only")


def print_report(report: AuditReport, *, strict: bool) -> int:
    if not report.findings:
        print("CE export audit: PASS (no issues)")
        return 0

    for f in report.findings:
        prefix = "ERROR" if f.level == "error" else "WARN "
        print(f"{prefix} [{f.category}] {f.path}\n       {f.detail}")

    err_n = len(report.errors)
    warn_n = len(report.warnings)
    print(f"\nSummary: {err_n} error(s), {warn_n} warning(s)")
    if err_n:
        return 1
    if strict and warn_n:
        return 2
    if warn_n:
        print("(warnings only — re-run with --strict to fail CI on warnings)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit BrickCore CE export safety and wording")
    parser.add_argument("--pro-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ce-root", type=Path, default=None, help="Audit existing CE directory after sync")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on warnings")
    args = parser.parse_args()

    pro_root = args.pro_root.resolve()
    report = AuditReport()

    if args.ce_root:
        audit_ce_root(args.ce_root.resolve(), report)
    else:
        audit_pro_export(pro_root, report)

    return print_report(report, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
