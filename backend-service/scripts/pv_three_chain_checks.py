# @AI_GENERATED
"""pv-three-chain-product-validation 自动化交付检查（任务 9.4）。

检查三件事（不改任何文件，只读扫描）：
1. AI 标记成对：本 spec 新增 / 修改的源码文件必须含成对 `@AI_GENERATED` 起止标记（按语言注释语法）。
2. 相对路径红线：pv_projects 后端源码不得出现 `os.path.abspath(` 或机器绝对路径字面量
   （`C:\\Users`、`/Users/`、`/opt/`、`/home/`），避免把绝对路径写入持久化。
3. 差异完整性：列出的关键交付文件必须存在（防止漏交 / 误删）。

用法：conda run -n cp_web python scripts/pv_three_chain_checks.py
退出码：0 全过；1 有问题（打印明细）。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]           # backend-service
ROOT = BACKEND.parent                                    # 项目根
FRONTEND = ROOT / "frontend-sevice"

# 本 spec 关键交付文件（相对项目根）。
DELIVERABLES = [
    # 后端 services
    "backend-service/services/pv_projects/scope.py",
    "backend-service/services/pv_projects/paths.py",
    "backend-service/services/pv_projects/repositories.py",
    "backend-service/services/pv_projects/stores.py",
    "backend-service/services/pv_projects/governance.py",
    "backend-service/services/pv_projects/review_service.py",
    "backend-service/services/pv_projects/cumulative.py",
    "backend-service/services/pv_projects/workflows.py",
    "backend-service/services/pv_projects/runner.py",
    "backend-service/services/pv_projects/day_adapter.py",
    "backend-service/services/pv_projects/sandbox_runtime.py",
    "backend-service/services/pv_projects/tsc_adapter.py",
    "backend-service/services/pv_projects/cross_dataset.py",
    "backend-service/services/pv_projects/projects.py",
    # 后端 API
    "backend-service/api/pv_projects/__init__.py",
    "backend-service/api/pv_projects/common.py",
    "backend-service/api/pv_projects/projects.py",
    "backend-service/api/pv_projects/datasets.py",
    "backend-service/api/pv_projects/runs.py",
    "backend-service/api/pv_projects/governance.py",
    "backend-service/api/pv_projects/reviews.py",
    "backend-service/api/pv_projects/cumulative.py",
    "backend-service/api/pv_projects/day.py",
    "backend-service/api/pv_projects/point.py",
    "backend-service/api/pv_projects/tsc.py",
    "backend-service/api/pv_projects/cross_dataset.py",
    # 属性测试
    "backend-service/tests/pv_projects/test_prop_scope_isolation.py",
    "backend-service/tests/pv_projects/test_prop_lineage.py",
    "backend-service/tests/pv_projects/test_governance_review_cumulative.py",
    "backend-service/tests/pv_projects/test_prop_point_causality.py",
    "backend-service/tests/pv_projects/test_prop_three_path.py",
    "backend-service/tests/pv_projects/test_prop_zero_pollution_governance.py",
    # 前端关键
    "frontend-sevice/src/services/pvProjectsApi.ts",
    "frontend-sevice/src/pv-fault/pages/ProjectListPage.tsx",
    "frontend-sevice/src/pv-fault/pages/ProjectOverviewPage.tsx",
    "frontend-sevice/src/pv-fault/pages/ProjectWorkbenchLayout.tsx",
    "frontend-sevice/src/pv-fault/components/CommandPalette.tsx",
    "frontend-sevice/src/pv-fault/components/ProjectEfficiencyBar.tsx",
    "frontend-sevice/src/pv-fault/components/PointRunSessionPanel.tsx",
    "frontend-sevice/src/pv-fault/components/DayGoldenPathPanel.tsx",
    "frontend-sevice/src/pv-fault/components/TscCanonicalPanel.tsx",
    "frontend-sevice/src/pv-fault/pages/stages/ProjectModelsStagePage.tsx",
    "frontend-sevice/src/pv-fault/pages/stages/ProjectReviewsStagePage.tsx",
    "frontend-sevice/src/pv-fault/pages/stages/ProjectCumulativeStagePage.tsx",
    "frontend-sevice/src/pv-fault/pages/stages/ProjectOperationsStagePage.tsx",
    "frontend-sevice/src/pv-fault/pages/stages/ProjectValidationsStagePage.tsx",
]

# 需要 AI 标记成对检查的文件（源码；.py / .ts / .tsx）。
_MARK_SUFFIXES = {".py", ".ts", ".tsx"}

# 相对路径红线扫描目标（仅 pv_projects 后端源码）。
_REL_PATH_DIRS = [
    BACKEND / "services" / "pv_projects",
    BACKEND / "api" / "pv_projects",
]
_ABS_PATTERNS = [
    re.compile(r"os\.path\.abspath\("),
    re.compile(r"[Cc]:\\\\Users"),
    re.compile(r"(?<![\w.])/Users/"),
    re.compile(r"(?<![\w.])/opt/"),
    re.compile(r"(?<![\w.])/home/"),
]


def check_ai_markers() -> list[str]:
    problems: list[str] = []
    for rel in DELIVERABLES:
        path = ROOT / rel
        if path.suffix not in _MARK_SUFFIXES:
            continue
        if not path.is_file():
            continue  # 缺失由 check_deliverables 报告
        text = path.read_text(encoding="utf-8")
        starts = len(re.findall(r"@AI_GENERATED(?!: end)", text))
        ends = len(re.findall(r"@AI_GENERATED: end", text))
        if starts == 0:
            problems.append(f"[AI-MARK] 缺少起始标记：{rel}")
        elif starts != ends:
            problems.append(f"[AI-MARK] 起止不成对（start={starts}, end={ends}）：{rel}")
    return problems


def check_relative_paths() -> list[str]:
    problems: list[str] = []
    for base in _REL_PATH_DIRS:
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for pat in _ABS_PATTERNS:
                for m in pat.finditer(text):
                    line_no = text.count("\n", 0, m.start()) + 1
                    rel = py.relative_to(ROOT).as_posix()
                    problems.append(f"[REL-PATH] {rel}:{line_no} 命中绝对路径 / abspath：{m.group(0)!r}")
    return problems


def check_deliverables() -> list[str]:
    problems: list[str] = []
    for rel in DELIVERABLES:
        if not (ROOT / rel).is_file():
            problems.append(f"[MISSING] 关键交付文件缺失：{rel}")
    return problems


def main() -> int:
    all_problems: list[str] = []
    all_problems += check_deliverables()
    all_problems += check_ai_markers()
    all_problems += check_relative_paths()

    if all_problems:
        print(f"CHECKS_FAILED count={len(all_problems)}")
        for p in all_problems:
            print(p)
        return 1
    print("CHECKS_OK 全部通过：AI 标记成对、相对路径红线、关键交付文件齐全")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# @AI_GENERATED: end
