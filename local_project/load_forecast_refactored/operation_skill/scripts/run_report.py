# @AI_GENERATED
"""
Skill 执行脚本: 生成 HTML 运营报告（demo 风格）
读取当前 active run 目录下的 JSON 产出，生成带日期的 HTML 报告。

用法（从 operation_skill/ 根目录运行）:
  conda run -n cp_web python scripts/run_report.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from scripts.core.html_report import write_html_report
from scripts.core.run_workspace import get_active_run_dir, get_active_run_info


def main() -> dict:
    run_dir = get_active_run_dir(_SKILL_ROOT)
    run_info = get_active_run_info(_SKILL_ROOT)
    out_path = write_html_report(run_dir)
    result = {
        "phase": "report",
        "run_dir": str(run_dir),
        "html_path": str(out_path),
        "report_file": run_info.get("report_file"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
