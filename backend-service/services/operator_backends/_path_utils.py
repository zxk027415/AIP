# @AI_GENERATED
"""
_path_utils.py — 算子后端共享路径解析工具

提供 resolve_file_path() 工具函数，将用户传入的相对路径解析为绝对路径。
搜索顺序：workspace_root → aip_dir → backend_dir → cwd
由于文件名以 _ 开头，OperatorRouter.auto_discover() 会自动跳过此文件。
"""
import os


def resolve_file_path(file_path: str) -> str:
    """
    将相对文件路径解析为绝对路径，按固定顺序搜索多个候选目录。

    搜索顺序（与 load_csv.py 的内置逻辑保持一致）：
      1. workspace_root  — 项目根目录（backend-service 的上上级）
      2. aip_dir         — AIP 服务目录（backend-service 的上级）
      3. backend_dir     — backend-service 目录
      4. cwd             — 当前工作目录

    如果 file_path 已是绝对路径或在当前目录下存在，直接返回。
    找不到时抛出 FileNotFoundError，并列出所有已搜索路径。

    Args:
        file_path: 文件路径（相对路径或绝对路径）。

    Returns:
        str: 解析后的绝对路径（已确认文件存在）。

    Raises:
        FileNotFoundError: 在所有候选目录下均未找到该文件。
    """
    # 绝对路径或当前目录下直接存在 — 直接返回
    if os.path.isabs(file_path) or os.path.exists(file_path):
        return file_path

    # __file__ = backend-service/services/operator_backends/_path_utils.py
    # backend_dir  = backend-service/
    # aip_dir      = AIP/  (backend-service 的父目录)
    # workspace_root = project root (AIP/ 的父目录，datasets/ 等数据集所在层级)
    backend_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    aip_dir = os.path.dirname(backend_dir)
    workspace_root = os.path.dirname(aip_dir)

    search_bases = [workspace_root, aip_dir, backend_dir, os.getcwd()]

    for base in search_bases:
        candidate = os.path.join(base, file_path)
        if os.path.exists(candidate):
            return candidate

    searched = "\n  ".join(
        os.path.join(b, file_path) for b in search_bases
    )
    raise FileNotFoundError(
        f"File not found: '{file_path}'\n"
        f"Searched the following paths:\n  {searched}"
    )
# @AI_GENERATED: end
