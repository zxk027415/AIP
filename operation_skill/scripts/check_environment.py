# @AI_GENERATED
"""
环境检查脚本: 验证运行所需的依赖和数据是否就绪。

用法（从 operation_skill/ 根目录运行）:
  conda run -n cp_web python scripts/check_environment.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[1]


def check():
    errors = []
    warnings = []

    # 1. Python 版本
    print(f"Python: {sys.version}")
    if sys.version_info < (3, 9):
        errors.append("需要 Python >= 3.9")

    # 2. 核心依赖
    deps = ["numpy", "pandas", "xgboost"]
    for dep in deps:
        try:
            __import__(dep)
            print(f"  ✓ {dep}")
        except ImportError:
            errors.append(f"缺少依赖: {dep}")
            print(f"  ✗ {dep}")

    # 3. 本地缓存数据
    cache_dir = _SKILL_ROOT / "cached_data"
    merged_file = cache_dir / "merged_20260201_20260527.csv"
    if merged_file.exists():
        print(f"  ✓ 本地缓存: {merged_file.name}")
    else:
        warnings.append(f"本地缓存不存在: {merged_file}")
        print(f"  ⚠ 本地缓存不存在（将尝试在线拉取）")

    # 4. 数据库连接
    try:
        sys.path.insert(0, str(_SKILL_ROOT))
        from fetch_asset_data import fetch_load
        print("  ✓ 数据库模块可用")
    except (ImportError, Exception) as e:
        if not merged_file.exists():
            errors.append(f"数据库不可用且无本地缓存: {e}")
        else:
            warnings.append(f"数据库不可用（将使用本地缓存）: {e}")
        print(f"  ⚠ 数据库模块: {e}")

    # 5. 产出目录
    artifact_dir = _SKILL_ROOT / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ 产出目录: {artifact_dir}")

    # 汇总
    print("\n" + "=" * 50)
    if errors:
        print("❌ 环境检查失败:")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)
    elif warnings:
        print("⚠️  环境检查通过（有警告）:")
        for w in warnings:
            print(f"   - {w}")
    else:
        print("✅ 环境检查全部通过，可以运行 Skill")


if __name__ == "__main__":
    check()
# @AI_GENERATED: end
