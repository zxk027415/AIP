import json
import os
import re
from typing import Any, Dict, Optional, Tuple

from services.agent_tools import get_tool_executor


class OperationContextPreloader:
    """强制预读取：模板结构 + 算子参数 + 最近训练/回测结果。"""

    def __init__(self) -> None:
        self._executor = get_tool_executor()
        self._backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self._workflow_dir = os.path.join(self._backend_dir, "data", "workflows_enhanced")

    @staticmethod
    def _resolve_workflow_id(message: str, context: Dict[str, Any]) -> Tuple[Optional[str], str]:
        """
        解析顺序（后者不覆盖前者）：
        1) 用户消息里显式写出 workflow-*
        2) 上下文 workflow_id / template_id（本轮指定模板）
        3) 策划/入口预选的 preselected_template.id
        4) last_executed_workflow_id（最近一次流水线/回测启动的模板，由前端或会话回写）
        """
        m = re.search(r"(workflow-[a-zA-Z0-9\-_]+)", message or "")
        if m:
            return m.group(1).strip(), "user_message"
        for key in ("workflow_id", "template_id"):
            v = context.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip(), "explicit_context"
        pre = context.get("preselected_template")
        if isinstance(pre, dict):
            tid = pre.get("id")
            if isinstance(tid, str) and tid.strip().startswith("workflow-"):
                return tid.strip(), "preselected_template"
        v = context.get("last_executed_workflow_id")
        if isinstance(v, str) and v.strip():
            return v.strip(), "last_executed_run"
        return None, "none"

    def _load_template_from_workflow_id(self, workflow_id: str) -> Dict[str, Any]:
        path = os.path.join(self._workflow_dir, f"{workflow_id}.json")
        if not os.path.exists(path):
            return {"found": False, "source": "workflow_id", "workflow_id": workflow_id, "error": "template not found"}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "found": True,
            "source": "workflow_id",
            "workflow_id": workflow_id,
            "path": path,
            "template": data,
        }

    def _load_template_from_path(self, template_path: str) -> Dict[str, Any]:
        if not os.path.exists(template_path):
            return {"found": False, "source": "template_path", "path": template_path, "error": "template path not found"}
        with open(template_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        workflow_id = data.get("id") if isinstance(data, dict) else None
        return {
            "found": True,
            "source": "template_path",
            "workflow_id": workflow_id,
            "path": template_path,
            "template": data,
        }

    def _load_template_from_name_match(self, message: str) -> Dict[str, Any]:
        """
        当 workflow_id 缺失时做兜底匹配，避免 nodes/edges=0:
        1) 关键词优先匹配固定模板
        2) 否则默认回测模板
        """
        msg = (message or "").lower()
        keyword_candidates = []
        if any(k in msg for k in ["调优", "tuning"]):
            keyword_candidates.append("workflow-load-forecast-tuning-v1")
        if any(k in msg for k in ["回测", "backtest", "漂移", "根因", "运营"]):
            keyword_candidates.append("workflow-load-forecast-backtest-v2")
        if any(k in msg for k in ["训练", "retrain", "重训"]):
            keyword_candidates.append("workflow-load-forecast-training-v2")
        if any(k in msg for k in ["预测", "inference", "predict"]):
            keyword_candidates.append("workflow-load-forecast-prediction-v2")
        if not keyword_candidates:
            keyword_candidates.append("workflow-load-forecast-backtest-v2")

        for wf_id in keyword_candidates:
            payload = self._load_template_from_workflow_id(wf_id)
            if payload.get("found"):
                payload["source"] = "auto_keyword_fallback"
                return payload

        # 兜底：取目录里最近文件
        try:
            files = sorted(
                [
                    fn for fn in os.listdir(self._workflow_dir)
                    if fn.endswith(".json") and not fn.startswith("_")
                ],
                key=lambda fn: os.path.getmtime(os.path.join(self._workflow_dir, fn)),
                reverse=True,
            )
            for fn in files:
                wf_id = fn[:-5]
                payload = self._load_template_from_workflow_id(wf_id)
                if payload.get("found"):
                    payload["source"] = "auto_latest_fallback"
                    return payload
        except Exception:
            pass

        return {
            "found": False,
            "source": "auto_fallback",
            "error": "no template matched",
        }

    async def load(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        workflow_id, workflow_id_source = self._resolve_workflow_id(message, context)
        template_path = context.get("template_path")

        template_payload: Dict[str, Any]
        if workflow_id:
            template_payload = self._load_template_from_workflow_id(workflow_id)
        elif isinstance(template_path, str) and template_path.strip():
            template_payload = self._load_template_from_path(template_path.strip())
            workflow_id = template_payload.get("workflow_id")
            if template_payload.get("found"):
                workflow_id_source = "template_path"
        else:
            template_payload = self._load_template_from_name_match(message)
            workflow_id = template_payload.get("workflow_id")
            workflow_id_source = str(template_payload.get("source") or "auto_keyword_fallback")

        if workflow_id and (not template_payload.get("found")):
            # 即使通过 context 给了 id，但文件未命中，也做兜底补救
            fallback_payload = self._load_template_from_name_match(message)
            if fallback_payload.get("found"):
                template_payload = fallback_payload
                workflow_id = fallback_payload.get("workflow_id")
                workflow_id_source = str(fallback_payload.get("source") or "auto_fallback")

        try:
            kwargs = {"workflow_id": workflow_id} if workflow_id else {}
            backtest_result = await self._executor.get_backtest_results(**kwargs)
        except Exception as e:
            backtest_result = {"error": str(e)}
        try:
            kwargs = {"workflow_id": workflow_id} if workflow_id else {}
            training_result = await self._executor.get_training_results(**kwargs)
        except Exception as e:
            training_result = {"error": str(e)}

        tpl = template_payload.get("template") or {}
        nodes = tpl.get("nodes") or []
        edges = tpl.get("edges") or []
        template_summary = {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "template_name": tpl.get("name"),
            "operator_ids": sorted(
                {
                    ((n.get("data") or {}).get("config") or {}).get("functionId")
                    for n in nodes
                    if ((n.get("data") or {}).get("config") or {}).get("functionId")
                }
            ),
            "operator_param_keys": {
                str(((n.get("data") or {}).get("config") or {}).get("functionId")): sorted(
                    [
                        k
                        for k in (((n.get("data") or {}).get("config") or {}).keys())
                        if k != "functionId"
                    ]
                )[:12]
                for n in nodes
                if ((n.get("data") or {}).get("config") or {}).get("functionId")
            },
        }

        return {
            "workflow_id": workflow_id,
            "workflow_id_source": workflow_id_source,
            "template_payload": template_payload,
            "template_summary": template_summary,
            "latest_backtest": backtest_result,
            "latest_training": training_result,
        }
