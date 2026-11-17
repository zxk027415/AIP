# @AI_GENERATED: Kiro v1.0
"""
算法方案库管理 API
提供方案列表、详情、统计、精度管理、应用实例等端点
"""
from fastapi import APIRouter, Query
from typing import Optional
import json, os, glob
from datetime import datetime

router = APIRouter(prefix="/api/algorithm-solutions", tags=["algorithm-solutions"])

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def _load_templates():
    with open(os.path.join(DATA_DIR, "industry_templates.json"), "r", encoding="utf-8") as f:
        return json.load(f)["templates"]

def _load_scenarios():
    with open(os.path.join(DATA_DIR, "industry_scenarios.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def _load_accuracy():
    path = os.path.join(DATA_DIR, "template_accuracy.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def _save_accuracy(records):
    path = os.path.join(DATA_DIR, "template_accuracy.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def _calc_status(metrics: dict) -> str:
    val = metrics.get("rmse") or metrics.get("mae") or (1 - metrics.get("f1", 1))
    if val is None:
        return "fair"
    if val < 0.03:
        return "excellent"
    if val < 0.06:
        return "good"
    if val < 0.10:
        return "fair"
    return "needs_improvement"

# @AI_GENERATED: Kiro v1.0
# 模板挂载管理
MOUNT_FILE = os.path.join(DATA_DIR, "solution_workflow_mounts.json")
# 业务场景挂载管理
SCENARIO_MOUNT_FILE = os.path.join(DATA_DIR, "scenario_workflow_mounts.json")

def _load_mounts():
    if os.path.exists(MOUNT_FILE):
        with open(MOUNT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_mounts(mounts):
    with open(MOUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(mounts, f, ensure_ascii=False, indent=2)

def _load_scenario_mounts():
    if os.path.exists(SCENARIO_MOUNT_FILE):
        with open(SCENARIO_MOUNT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_scenario_mounts(mounts):
    with open(SCENARIO_MOUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(mounts, f, ensure_ascii=False, indent=2)

def _get_workflow_info(workflow_id: str):
    """获取算法模板信息"""
    wf_dir = os.path.join(DATA_DIR, "workflows_enhanced")
    fp = os.path.join(wf_dir, f"{workflow_id}.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            wf = json.load(f)
        return {
            "id": workflow_id,
            "name": wf.get("name", workflow_id),
            "node_count": len(wf.get("nodes", [])),
            "edge_count": len(wf.get("edges", [])),
        }
    return None

# 业务场景映射
BUSINESS_SCENARIOS_MAP = {
    "pv_power_forecast": [
        {"id": "centralized_pv", "name": "集中式光伏电站", "description": "大型地面光伏电站功率预测"},
        {"id": "distributed_pv", "name": "分布式光伏", "description": "屋顶分布式光伏功率预测"},
        {"id": "floating_pv", "name": "水面光伏", "description": "水上漂浮式光伏电站功率预测"},
    ],
    "wind_power_forecast": [
        {"id": "onshore_wind", "name": "陆上风电", "description": "陆上风电场功率预测"},
        {"id": "offshore_wind", "name": "海上风电", "description": "海上风电场功率预测"},
        {"id": "distributed_wind", "name": "分散式风电", "description": "分散式风电功率预测"},
    ],
    "load_forecast": [
        {"id": "industrial_load", "name": "工业负荷", "description": "工业园区电力负荷预测"},
        {"id": "commercial_load", "name": "商业负荷", "description": "商业建筑电力负荷预测"},
        {"id": "residential_load", "name": "居民负荷", "description": "居民区电力负荷预测"},
    ],
    # @AI_GENERATED
    # 能源预测 — 电网与微网下的负荷预测（新业务场景）
    "energy_load_forecast": [
        {"id": "node_load", "name": "节点负荷", "description": "电网节点级负荷预测，精确到单个变电站或馈线"},
        {"id": "busbar_load", "name": "母线负荷", "description": "母线级负荷预测，用于变电站母线负荷平衡"},
        {"id": "regional_load", "name": "区域负荷", "description": "区域级负荷预测，覆盖地区或省级电网"},
    ],
    "energy_wind_forecast": [
        {"id": "onshore_wind_energy", "name": "陆上风电", "description": "陆上风电场发电功率预测"},
        {"id": "offshore_wind_energy", "name": "海上风电", "description": "海上风电场发电功率预测"},
    ],
    "energy_pv_forecast": [
        {"id": "centralized_pv_energy", "name": "集中式光伏", "description": "大型地面光伏电站功率预测"},
        {"id": "distributed_pv_energy", "name": "分布式光伏", "description": "屋顶分布式光伏功率预测"},
    ],
    "energy_hydro_forecast": [
        {"id": "reservoir_hydro", "name": "水库式水电", "description": "水库式水电站发电功率预测"},
        {"id": "runofriver_hydro", "name": "径流式水电", "description": "径流式水电站发电功率预测"},
    ],
    "energy_thermal_forecast": [
        {"id": "coal_thermal", "name": "燃煤火电", "description": "燃煤火电机组出力预测"},
        {"id": "gas_thermal", "name": "燃气火电", "description": "燃气火电机组出力预测"},
    ],
    "energy_price_forecast": [
        {"id": "spot_price", "name": "现货价格", "description": "电力现货市场价格预测"},
        {"id": "futures_price", "name": "期货价格", "description": "电力期货市场价格预测"},
    ],
    # @AI_GENERATED: end
    "inverter_fault": [
        {"id": "string_inverter", "name": "组串式逆变器", "description": "组串式逆变器故障诊断"},
        {"id": "central_inverter", "name": "集中式逆变器", "description": "集中式逆变器故障诊断"},
        {"id": "micro_inverter", "name": "微型逆变器", "description": "微型逆变器故障诊断"},
    ],
    "pv_module_fault": [
        {"id": "mono_module", "name": "单晶硅组件", "description": "单晶硅光伏组件故障分类"},
        {"id": "poly_module", "name": "多晶硅组件", "description": "多晶硅光伏组件故障分类"},
        {"id": "thin_film", "name": "薄膜组件", "description": "薄膜光伏组件故障分类"},
    ],
    "wind_turbine_fault": [
        {"id": "gearbox_fault", "name": "齿轮箱故障", "description": "风机齿轮箱故障诊断"},
        {"id": "generator_fault", "name": "发电机故障", "description": "风机发电机故障诊断"},
        {"id": "blade_fault", "name": "叶片故障", "description": "风机叶片故障诊断"},
    ],
    "generation_pattern": [
        {"id": "seasonal_pattern", "name": "季节性模式", "description": "按季节特征聚类发电模式"},
        {"id": "weather_pattern", "name": "气象模式", "description": "按气象条件聚类发电模式"},
        {"id": "load_pattern", "name": "负荷模式", "description": "按负荷特征聚类发电模式"},
    ],
    "weather_pattern": [
        {"id": "solar_radiation", "name": "辐照模式", "description": "太阳辐照强度模式聚类"},
        {"id": "wind_speed", "name": "风速模式", "description": "风速变化模式聚类"},
        {"id": "temperature", "name": "温度模式", "description": "温度变化模式聚类"},
    ],
    "island_detection": [
        {"id": "passive_detection", "name": "被动检测", "description": "被动式孤岛检测方案"},
        {"id": "active_detection", "name": "主动检测", "description": "主动式孤岛检测方案"},
        {"id": "hybrid_detection", "name": "混合检测", "description": "混合式孤岛检测方案"},
    ],
    "pv_station_monitor": [
        {"id": "real_time_monitor", "name": "实时监控", "description": "光伏电站实时运行监控"},
        {"id": "performance_monitor", "name": "性能监控", "description": "光伏电站性能指标监控"},
        {"id": "alarm_monitor", "name": "告警监控", "description": "光伏电站告警事件监控"},
    ],
    "wind_farm_monitor": [
        {"id": "turbine_monitor", "name": "风机监控", "description": "单台风机运行状态监控"},
        {"id": "farm_monitor", "name": "场站监控", "description": "整场风电运行监控"},
        {"id": "grid_monitor", "name": "并网监控", "description": "风电并网状态监控"},
    ],
    "generation_planning": [
        {"id": "day_ahead", "name": "日前计划", "description": "日前发电计划编制"},
        {"id": "intraday", "name": "日内计划", "description": "日内发电计划滚动修正"},
        {"id": "real_time", "name": "实时调度", "description": "实时发电调度优化"},
    ],
}

DEFAULT_SCENARIOS = [
    {"id": "standard", "name": "标准场景", "description": "标准应用场景"},
    {"id": "complex", "name": "复杂场景", "description": "复杂环境应用场景"},
    {"id": "edge", "name": "边缘场景", "description": "边缘计算应用场景"},
]

def _get_business_scenarios(template_id: str):
    """获取模板的业务场景列表"""
    return BUSINESS_SCENARIOS_MAP.get(template_id, DEFAULT_SCENARIOS)
# @AI_GENERATED: end

SCENARIO_INDUSTRY = {}

def _get_scenario_industry():
    if not SCENARIO_INDUSTRY:
        for s in _load_scenarios():
            SCENARIO_INDUSTRY[s["id"]] = s.get("industry_tags", [])
    return SCENARIO_INDUSTRY


@router.get("")
async def list_templates(
    scenario: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    templates = _load_templates()
    si = _get_scenario_industry()
    if scenario:
        templates = [t for t in templates if t["scenario_id"] == scenario]
    if industry:
        templates = [t for t in templates if industry in si.get(t["scenario_id"], [])]
    if keyword:
        kw = keyword.lower()
        templates = [t for t in templates if kw in t["name"].lower() or kw in t.get("description", "").lower()]
    total = len(templates)
    start = (page - 1) * page_size
    items = templates[start:start + page_size]
    # attach latest accuracy
    acc = _load_accuracy()
    acc_map = {}
    for a in acc:
        tid = a["template_id"]
        if tid not in acc_map or a["test_date"] > acc_map[tid]["test_date"]:
            acc_map[tid] = a
    # @AI_GENERATED: Kiro v1.0
    # 加载挂载关系
    mounts = _load_mounts()
    scenario_mounts = _load_scenario_mounts()
    # @AI_GENERATED: end
    for item in items:
        latest = acc_map.get(item["id"])
        item["accuracy_status"] = latest["status"] if latest else None
        item["accuracy_metrics"] = latest["metrics"] if latest else None
        # @AI_GENERATED: Kiro v1.0
        item["mounted_workflows"] = mounts.get(item["id"], [])
        # 添加业务场景
        base_scenarios = _get_business_scenarios(item["id"])
        business_scenarios = []
        for bs in base_scenarios:
            scenario_key = f"{item['id']}_{bs['id']}"
            mounted = scenario_mounts.get(scenario_key, [])
            business_scenarios.append({
                **bs,
                "mounted_workflows": mounted,
            })
        item["business_scenarios"] = business_scenarios
        # @AI_GENERATED: end
    return {"total": total, "page": page, "page_size": page_size, "items": items}


# @AI_GENERATED: Kiro v1.0
@router.get("/stats")
async def template_stats():
    templates = _load_templates()
    scenarios = _load_scenarios()
    by_scenario = {}
    for t in templates:
        sid = t["scenario_id"]
        by_scenario[sid] = by_scenario.get(sid, 0) + 1
    scenario_stats = []
    for s in scenarios:
        scenario_stats.append({
            "scenario_id": s["id"],
            "name": s["name"],
            "icon": s.get("icon", ""),
            "count": by_scenario.get(s["id"], 0),
            "industry_tags": s.get("industry_tags", []),
        })
    return {"total": len(templates), "by_scenario": scenario_stats, "scenario_count": len(scenarios)}
# @AI_GENERATED: end


@router.get("/accuracy/ranking")
async def accuracy_ranking(
    scenario_id: Optional[str] = Query(None),
):
    templates = _load_templates()
    if scenario_id:
        templates = [t for t in templates if t["scenario_id"] == scenario_id]
    tid_set = {t["id"] for t in templates}
    tid_name = {t["id"]: t["name"] for t in templates}
    tid_scenario = {t["id"]: t["scenario_id"] for t in templates}
    acc = _load_accuracy()
    latest = {}
    for a in acc:
        tid = a["template_id"]
        if tid not in tid_set:
            continue
        if tid not in latest or a["test_date"] > latest[tid]["test_date"]:
            latest[tid] = a
    ranking = []
    for tid, a in latest.items():
        ranking.append({
            "template_id": tid,
            "template_name": tid_name.get(tid, tid),
            "scenario_id": tid_scenario.get(tid, ""),
            "metrics": a["metrics"],
            "status": a["status"],
            "test_date": a["test_date"],
        })
    ranking.sort(key=lambda x: x["metrics"].get("rmse", x["metrics"].get("mae", 999)))
    return {"ranking": ranking, "total": len(ranking)}


@router.get("/applications/stats")
async def application_stats():
    wf_dir = os.path.join(DATA_DIR, "workflows_enhanced")
    templates = _load_templates()
    tid_set = {t["id"] for t in templates}
    usage = {}
    total_wf = 0
    for fp in glob.glob(os.path.join(wf_dir, "*.json")):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                wf = json.load(f)
            total_wf += 1
            nodes = wf.get("nodes", [])
            seen = set()
            for n in nodes:
                fid = n.get("data", {}).get("function_id") or n.get("data", {}).get("functionId", "")
                if fid in tid_set and fid not in seen:
                    seen.add(fid)
                    if fid not in usage:
                        usage[fid] = {"count": 0, "workflows": []}
                    usage[fid]["count"] += 1
                    usage[fid]["workflows"].append(os.path.basename(fp))
        except Exception:
            continue
    return {"total_templates_used": len(usage), "total_workflows": total_wf, "usage": usage}


@router.get("/{template_id}")
async def get_template(template_id: str):
    templates = _load_templates()
    tpl = next((t for t in templates if t["id"] == template_id), None)
    if not tpl:
        return {"error": "Template not found"}
    acc = _load_accuracy()
    history = [a for a in acc if a["template_id"] == template_id]
    history.sort(key=lambda x: x["test_date"], reverse=True)
    tpl["accuracy_history"] = history
    tpl["accuracy_status"] = history[0]["status"] if history else None
    return tpl


@router.get("/{template_id}/accuracy")
async def get_accuracy(template_id: str):
    acc = _load_accuracy()
    history = [a for a in acc if a["template_id"] == template_id]
    history.sort(key=lambda x: x["test_date"], reverse=True)
    return {"template_id": template_id, "records": history}


@router.post("/{template_id}/accuracy")
async def add_accuracy(template_id: str, body: dict):
    acc = _load_accuracy()
    record = {
        "id": f"acc-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "template_id": template_id,
        "dataset_id": body.get("dataset_id", ""),
        "dataset_name": body.get("dataset_name", ""),
        "test_date": body.get("test_date", datetime.now().strftime("%Y-%m-%d")),
        "metrics": body.get("metrics", {}),
        "status": _calc_status(body.get("metrics", {})),
        "tester": body.get("tester", ""),
        "notes": body.get("notes", ""),
    }
    acc.append(record)
    _save_accuracy(acc)
    return record


@router.get("/{template_id}/applications")
async def get_applications(template_id: str):
    wf_dir = os.path.join(DATA_DIR, "workflows_enhanced")
    results = []
    for fp in glob.glob(os.path.join(wf_dir, "*.json")):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                wf = json.load(f)
            nodes = wf.get("nodes", [])
            for n in nodes:
                fid = n.get("data", {}).get("function_id") or n.get("data", {}).get("functionId", "")
                if fid == template_id:
                    results.append({
                        "workflow_id": os.path.basename(fp).replace(".json", ""),
                        "workflow_name": wf.get("name", os.path.basename(fp)),
                        "created_at": wf.get("created_at", ""),
                        "node_count": len(nodes),
                        "edge_count": len(wf.get("edges", [])),
                    })
                    break
        except Exception:
            continue
    return {"template_id": template_id, "applications": results, "total": len(results)}


@router.post("/{solution_id}/mount")
async def mount_workflow(solution_id: str, body: dict):
    """挂载算法模板到算法方案"""
    workflow_id = body.get("workflow_id")
    if not workflow_id:
        return {"error": "workflow_id is required"}
    
    # 验证方案存在
    templates = _load_templates()
    tpl = next((t for t in templates if t["id"] == solution_id), None)
    if not tpl:
        return {"error": "Solution not found"}
    
    # 验证模板存在
    wf_info = _get_workflow_info(workflow_id)
    if not wf_info:
        return {"error": "Workflow not found"}
    
    # 加载挂载关系
    mounts = _load_mounts()
    if solution_id not in mounts:
        mounts[solution_id] = []
    
    # 检查是否已挂载
    if any(m["id"] == workflow_id for m in mounts[solution_id]):
        return {"error": "Workflow already mounted"}
    
    # 添加挂载
    mounts[solution_id].append({
        **wf_info,
        "mounted_at": datetime.now().isoformat(),
    })
    _save_mounts(mounts)
    
    return {"success": True, "message": f"Workflow {workflow_id} mounted to solution {solution_id}"}


@router.delete("/{solution_id}/mount/{workflow_id}")
async def unmount_workflow(solution_id: str, workflow_id: str):
    """从算法方案卸载算法模板"""
    mounts = _load_mounts()
    if solution_id not in mounts:
        return {"error": "No mounts found for this solution"}
    
    original_len = len(mounts[solution_id])
    mounts[solution_id] = [m for m in mounts[solution_id] if m["id"] != workflow_id]
    
    if len(mounts[solution_id]) == original_len:
        return {"error": "Workflow not mounted to this solution"}
    
    _save_mounts(mounts)
    return {"success": True, "message": f"Workflow {workflow_id} unmounted from solution {solution_id}"}


@router.get("/{solution_id}/mounts")
async def get_mounts(solution_id: str):
    """获取算法方案已挂载的模板列表"""
    mounts = _load_mounts()
    return {"solution_id": solution_id, "mounted_workflows": mounts.get(solution_id, [])}


# @AI_GENERATED: Kiro v1.0
@router.post("/{solution_id}/scenarios/{scenario_id}/mount")
async def mount_workflow_to_scenario(solution_id: str, scenario_id: str, body: dict):
    """挂载算法模板到业务场景"""
    workflow_id = body.get("workflow_id")
    if not workflow_id:
        return {"error": "workflow_id is required"}
    
    # 验证方案存在
    templates = _load_templates()
    tpl = next((t for t in templates if t["id"] == solution_id), None)
    if not tpl:
        return {"error": "Solution not found"}
    
    # 验证业务场景存在
    scenarios = _get_business_scenarios(solution_id)
    if not any(s["id"] == scenario_id for s in scenarios):
        return {"error": "Business scenario not found"}
    
    # 验证模板存在
    wf_info = _get_workflow_info(workflow_id)
    if not wf_info:
        return {"error": "Workflow not found"}
    
    # 加载挂载关系
    mounts = _load_scenario_mounts()
    scenario_key = f"{solution_id}_{scenario_id}"
    if scenario_key not in mounts:
        mounts[scenario_key] = []
    
    # 检查是否已挂载
    if any(m["id"] == workflow_id for m in mounts[scenario_key]):
        return {"error": "Workflow already mounted to this scenario"}
    
    # 添加挂载
    mounts[scenario_key].append({
        **wf_info,
        "mounted_at": datetime.now().isoformat(),
    })
    _save_scenario_mounts(mounts)
    
    return {"success": True, "message": f"Workflow {workflow_id} mounted to scenario {scenario_id}"}


@router.delete("/{solution_id}/scenarios/{scenario_id}/mount/{workflow_id}")
async def unmount_workflow_from_scenario(solution_id: str, scenario_id: str, workflow_id: str):
    """从业务场景卸载算法模板"""
    mounts = _load_scenario_mounts()
    scenario_key = f"{solution_id}_{scenario_id}"
    
    if scenario_key not in mounts:
        return {"error": "No mounts found for this scenario"}
    
    original_len = len(mounts[scenario_key])
    mounts[scenario_key] = [m for m in mounts[scenario_key] if m["id"] != workflow_id]
    
    if len(mounts[scenario_key]) == original_len:
        return {"error": "Workflow not mounted to this scenario"}
    
    _save_scenario_mounts(mounts)
    return {"success": True, "message": f"Workflow {workflow_id} unmounted from scenario {scenario_id}"}


@router.get("/{solution_id}/scenarios/{scenario_id}/mounts")
async def get_scenario_mounts(solution_id: str, scenario_id: str):
    """获取业务场景已挂载的模板列表"""
    mounts = _load_scenario_mounts()
    scenario_key = f"{solution_id}_{scenario_id}"
    return {"solution_id": solution_id, "scenario_id": scenario_id, "mounted_workflows": mounts.get(scenario_key, [])}
# @AI_GENERATED: end
