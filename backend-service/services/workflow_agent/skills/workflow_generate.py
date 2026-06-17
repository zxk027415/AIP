# @AI_GENERATED: Kiro v1.0
"""
算法模板自动生成 Skill — 根据算法组合生成 WorkflowDefinition
"""
import time
import uuid
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from models.workflow_agent_models import (
    AlgorithmCombination,
    WorkflowGenerateRequest,
    WorkflowGenerateResponse,
    SkillContext,
)
from services.workflow_agent.skills.base_skill import BaseSkill
from services.workflow_agent.knowledge.algorithm_library import get_algorithm_library

logger = logging.getLogger(__name__)

# 布局常量
NODE_WIDTH = 200
NODE_HEIGHT = 80
LAYER_GAP_Y = 150
NODE_GAP_X = 250
START_X = 100
START_Y = 80

LAYER_ORDER = ["数据管理层", "数据处理层", "算法模型层", "评估输出层"]


def _build_node(
    algorithm_id: str,
    algorithm_name: str,
    x: float,
    y: float,
    fn_meta: Optional[Dict],
) -> Dict[str, Any]:
    """构建一个 WorkflowNode dict"""
    node_id = f"node-{uuid.uuid4().hex[:8]}"
    inputs = []
    outputs = []
    params: Dict[str, Any] = {}

    if fn_meta:
        for p in fn_meta.get("parameters", []):
            inputs.append({
                "id": f"{node_id}-in-{p['name']}",
                "name": p["name"],
                "type": p.get("type", "ANY"),
                "required": p.get("required", False),
            })
            if "default" in p:
                params[p["name"]] = p["default"]
        ret_type = fn_meta.get("return_type", "ANY")
        outputs.append({
            "id": f"{node_id}-out-result",
            "name": "result",
            "type": ret_type,
            "required": False,
        })
    else:
        inputs.append({
            "id": f"{node_id}-in-data",
            "name": "data",
            "type": "ANY",
            "required": True,
        })
        outputs.append({
            "id": f"{node_id}-out-result",
            "name": "result",
            "type": "ANY",
            "required": False,
        })

    # @AI_GENERATED: Kiro v1.0
    description = ""
    if fn_meta:
        description = fn_meta.get("description", "")
    # @AI_GENERATED: end

    return {
        "id": node_id,
        "type": "function",
        "position": {"x": x, "y": y},
        "data": {
            "label": algorithm_name,
            "description": description,
            "functionId": algorithm_id,
            "parameters": params,
            "inputs": inputs,
            "outputs": outputs,
        },
    }


def _build_edges(layer_nodes: Dict[str, List[Dict]]) -> List[Dict[str, Any]]:
    """根据层级顺序创建节点间的边（上游最后一个 output → 下游第一个 input）"""
    edges: List[Dict[str, Any]] = []
    prev_layer_nodes: List[Dict] = []

    for layer_name in LAYER_ORDER:
        cur_nodes = layer_nodes.get(layer_name, [])
        if prev_layer_nodes and cur_nodes:
            for src in prev_layer_nodes:
                src_outputs = src["data"].get("outputs", [])
                if not src_outputs:
                    continue
                src_handle = src_outputs[0]["id"]
                for tgt in cur_nodes:
                    tgt_inputs = tgt["data"].get("inputs", [])
                    if not tgt_inputs:
                        continue
                    tgt_handle = tgt_inputs[0]["id"]
                    edges.append({
                        "id": f"edge-{uuid.uuid4().hex[:8]}",
                        "source": src["id"],
                        "sourceHandle": src_handle,
                        "target": tgt["id"],
                        "targetHandle": tgt_handle,
                    })
        prev_layer_nodes = cur_nodes
    return edges


def _generate_summary(
    scenario_id: str, node_count: int, edge_count: int, layer_counts: Dict[str, int]
) -> str:
    parts = [f"为场景 {scenario_id} 生成算法模板："]
    for layer in LAYER_ORDER:
        cnt = layer_counts.get(layer, 0)
        parts.append(f"{layer} {cnt} 个节点")
    parts.append(f"共 {node_count} 个节点、{edge_count} 条连接")
    return "，".join(parts)


class WorkflowGenerateSkill(BaseSkill):
    """算法模板自动生成 Skill"""

    skill_name = "workflow-generate"
    required_role = "user"

    async def validate_input(self, request: BaseModel) -> None:
        if isinstance(request, WorkflowGenerateRequest):
            if not request.scenario_id.strip():
                raise ValueError("scenario_id 不能为空")
            if not request.combination.layers:
                raise ValueError("算法组合不能为空")

    async def execute(
        self, request: BaseModel, context: SkillContext
    ) -> WorkflowGenerateResponse:
        if not isinstance(request, WorkflowGenerateRequest):
            raise ValueError("请求类型错误，期望 WorkflowGenerateRequest")

        start = time.time()
        lib = get_algorithm_library()
        combination = request.combination

        all_nodes: List[Dict] = []
        layer_nodes: Dict[str, List[Dict]] = {}
        layer_counts: Dict[str, int] = {}

        for layer_idx, layer in enumerate(combination.layers):
            layer_name = layer.layer_name
            nodes_in_layer: List[Dict] = []
            for algo_idx, algo in enumerate(layer.algorithms):
                x = START_X + algo_idx * NODE_GAP_X
                y = START_Y + layer_idx * LAYER_GAP_Y
                fn_meta = lib.get_by_id(algo.algorithm_id)
                node = _build_node(
                    algo.algorithm_id, algo.algorithm_name, x, y, fn_meta
                )
                nodes_in_layer.append(node)
                all_nodes.append(node)
            layer_nodes[layer_name] = nodes_in_layer
            layer_counts[layer_name] = len(nodes_in_layer)

        edges = _build_edges(layer_nodes)

        workflow_def = {
            "nodes": all_nodes,
            "edges": edges,
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "metadata": {
                "author": context.username,
                "version": "1.0.0",
                "tags": [request.scenario_id, combination.profile.value],
                "isTemplate": False,
            },
        }

        summary = _generate_summary(
            request.scenario_id, len(all_nodes), len(edges), layer_counts
        )

        return WorkflowGenerateResponse(
            workflow=workflow_def,
            generation_summary=summary,
            node_count=len(all_nodes),
            edge_count=len(edges),
            processing_time_ms=int((time.time() - start) * 1000),
        )
# @AI_GENERATED: end
