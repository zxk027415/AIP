# @AI_GENERATED: Kiro v1.0
"""
行业场景匹配 Skill — 基于关键词 + TF-IDF 的规则引擎实现
预留 LLMScenarioMatcher 接口，当前使用 RuleBasedScenarioMatcher
"""
import json
import math
import os
import re
import time
import logging
from collections import Counter
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from models.workflow_agent_models import (
    ScenarioMatchRequest,
    ScenarioMatchResponse,
    ScenarioMatchResult,
    SkillContext,
)
from services.workflow_agent.skills.base_skill import BaseSkill
from utils.cache import scenario_cache

logger = logging.getLogger(__name__)

# 场景数据文件路径
SCENARIOS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "industry_scenarios.json"
)


# ============ 业务实体提取关键词表 ============

INDUSTRY_KEYWORDS: Dict[str, List[str]] = {
    "新能源": ["新能源", "光伏", "风电", "风力", "太阳能", "发电", "renewable", "solar", "wind"],
    "储能": ["储能", "电池", "SOC", "SOH", "充放电", "battery", "storage", "BMS"],
    "电网": ["电网", "微网", "潮流", "负荷", "配电", "grid", "power", "load"],
    "钢铁": ["钢铁", "炼钢", "轧钢", "铸造", "冶金", "steel", "metallurgy"],
    "光伏制造": ["光伏制造", "硅片", "电池片", "组件", "良率", "pv manufacturing"],
    "电池制造": ["动力电池", "电芯", "pack", "一致性", "容量分选", "battery manufacturing"],
    "工业制造": ["制造", "排程", "OEE", "SPC", "manufacturing", "production"],
    "港口": ["港口", "泊位", "AGV", "集装箱", "吞吐", "port", "logistics"],
    "楼宇": ["楼宇", "暖通", "HVAC", "照明", "空调", "building", "campus"],
    "碳管理": ["碳", "碳排放", "碳核算", "碳交易", "减排", "carbon"],
    "可视化": ["可视化", "大屏", "SCADA", "看板", "dashboard", "visualization"],
    "LLM": ["LLM", "大模型", "RAG", "NLP", "知识图谱", "OCR", "问答"],
    "视觉": ["视觉", "图像", "检测", "分割", "目标检测", "vision", "image", "defect"],
    "设备健康": ["设备", "维护", "RUL", "FMEA", "振动", "故障", "health", "predictive"],
}

DATA_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "时序数据": ["时序", "时间序列", "趋势", "timeseries", "temporal"],
    "图像数据": ["图像", "图片", "视觉", "image", "photo", "picture"],
    "表格数据": ["表格", "结构化", "CSV", "tabular", "structured"],
    "文本数据": ["文本", "日志", "文档", "text", "log", "document"],
}

OBJECTIVE_KEYWORDS: Dict[str, List[str]] = {
    "预测": ["预测", "forecast", "predict", "估计", "estimation"],
    "分类": ["分类", "classify", "classification", "识别"],
    "异常检测": ["异常", "故障", "缺陷", "anomaly", "fault", "defect"],
    "优化": ["优化", "调度", "optimize", "scheduling", "optimization"],
    "聚类": ["聚类", "分群", "cluster", "grouping"],
}

EQUIPMENT_KEYWORDS: Dict[str, List[str]] = {
    "风机": ["风机", "风力发电机", "wind turbine"],
    "光伏板": ["光伏板", "太阳能板", "solar panel", "组件"],
    "电池": ["电池", "电芯", "蓄电池", "battery", "cell"],
    "电机": ["电机", "马达", "motor"],
    "变压器": ["变压器", "transformer"],
    "传感器": ["传感器", "sensor"],
}


# ============ 场景→关键词映射（用于 TF-IDF 匹配） ============

# @AI_GENERATED: Kiro v1.0
# 13个行业场景关键词映射
SCENARIO_KEYWORD_MAP: Dict[str, List[str]] = {
    "renewable-energy": ["新能源", "光伏", "风电", "功率预测", "发电", "资源评估", "solar", "wind", "power forecast"],
    "thermal-power": ["火力发电", "火电", "燃煤", "燃气", "锅炉", "汽轮机", "煤耗", "煤价", "脱硫", "脱硝", "thermal power"],
    "energy-storage": ["储能", "SOC", "SOH", "电池", "调度", "寿命预测", "充放电", "BMS", "battery"],
    "power-grid": ["电网", "微网", "潮流", "负荷预测", "调度", "电能质量", "配电", "grid"],
    "steel-manufacturing": ["钢铁", "质量预测", "工艺优化", "缺陷检测", "能耗", "炼钢", "轧钢", "steel"],
    "pv-manufacturing": ["光伏制造", "缺陷检测", "效率预测", "良率", "组件分选", "硅片", "EL检测"],
    "battery-manufacturing": ["动力电池", "一致性", "安全预测", "工艺优化", "容量分选", "电芯", "化成"],
    "semiconductor": ["半导体", "晶圆", "芯片", "良率", "刻蚀", "光刻", "CVD", "CMP", "fab"],
    "chemical-process": ["化工", "反应器", "精馏", "催化剂", "工艺优化", "安全预警", "chemical"],
    "port-logistics": ["港口", "泊位", "AGV", "路径规划", "吞吐", "集装箱", "物流", "port"],
    "building-campus": ["楼宇", "暖通", "能源审计", "照明", "舒适度", "空调", "HVAC", "building"],
    "carbon-management": ["碳", "碳核算", "碳交易", "碳足迹", "减排", "碳排放", "carbon"],
    "water-environment": ["水务", "污水", "水质", "管网", "加药", "曝气", "COD", "氨氮", "water"],
}
# @AI_GENERATED: end


# ============ 工具函数 ============

def _tokenize(text: str) -> List[str]:
    """简单分词：中文按字符 bigram，英文按空格/标点"""
    text = text.lower().strip()
    tokens: List[str] = []
    # 英文单词
    eng_words = re.findall(r"[a-zA-Z][a-zA-Z0-9_]*", text)
    tokens.extend(eng_words)
    # 中文字符提取 bigram
    cn_chars = re.findall(r"[\u4e00-\u9fff]+", text)
    for seg in cn_chars:
        tokens.append(seg)  # 完整词
        for i in range(len(seg) - 1):
            tokens.append(seg[i:i+2])  # bigram
    return tokens


def _extract_entities(text: str) -> Dict[str, str]:
    """从用户描述中提取业务实体"""
    text_lower = text.lower()
    entities: Dict[str, str] = {
        "industry_type": "",
        "data_type": "",
        "business_objective": "",
        "equipment_type": "",
    }
    for label, kws in INDUSTRY_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in kws):
            entities["industry_type"] = label
            break
    for label, kws in DATA_TYPE_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in kws):
            entities["data_type"] = label
            break
    for label, kws in OBJECTIVE_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in kws):
            entities["business_objective"] = label
            break
    for label, kws in EQUIPMENT_KEYWORDS.items():
        if any(kw.lower() in text_lower for kw in kws):
            entities["equipment_type"] = label
            break
    return entities


def _compute_tfidf_scores(
    query_tokens: List[str],
    scenario_docs: Dict[str, List[str]],
) -> Dict[str, float]:
    """计算查询与每个场景文档的 TF-IDF 余弦相似度"""
    # 构建词汇表
    all_docs = list(scenario_docs.values()) + [query_tokens]
    vocab: set = set()
    for doc in all_docs:
        vocab.update(doc)
    if not vocab:
        return {sid: 0.0 for sid in scenario_docs}

    vocab_list = sorted(vocab)
    vocab_idx = {w: i for i, w in enumerate(vocab_list)}
    n_docs = len(all_docs)

    # 计算 DF
    df = Counter()
    for doc in all_docs:
        unique = set(doc)
        for w in unique:
            df[w] += 1

    def _tfidf_vec(tokens: List[str]) -> List[float]:
        tf = Counter(tokens)
        vec = [0.0] * len(vocab_list)
        for w, count in tf.items():
            if w in vocab_idx:
                idf = math.log((n_docs + 1) / (df.get(w, 0) + 1)) + 1
                vec[vocab_idx[w]] = count * idf
        return vec

    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    query_vec = _tfidf_vec(query_tokens)
    scores: Dict[str, float] = {}
    for sid, doc_tokens in scenario_docs.items():
        doc_vec = _tfidf_vec(doc_tokens)
        scores[sid] = _cosine(query_vec, doc_vec)
    return scores


# ============ 匹配器接口抽象（预留 LLM 替换） ============

class ScenarioMatcher:
    """场景匹配器基类（策略模式）"""
    def match(
        self, description: str, scenarios: List[Dict]
    ) -> List[Tuple[str, str, int, str]]:
        """返回 [(scenario_id, scenario_name, confidence, rationale), ...]"""
        raise NotImplementedError


class RuleBasedScenarioMatcher(ScenarioMatcher):
    """基于关键词 + TF-IDF 的规则匹配器"""

    def match(
        self, description: str, scenarios: List[Dict]
    ) -> List[Tuple[str, str, int, str]]:
        query_tokens = _tokenize(description)
        if not query_tokens:
            return []

        # 构建场景文档
        scenario_docs: Dict[str, List[str]] = {}
        scenario_map: Dict[str, Dict] = {}
        for s in scenarios:
            sid = s["id"]
            scenario_map[sid] = s
            doc_tokens: List[str] = []
            doc_tokens.extend(_tokenize(s.get("name", "")))
            doc_tokens.extend(_tokenize(s.get("description", "")))
            for tag in s.get("industry_tags", []):
                doc_tokens.extend(_tokenize(tag))
            for cap in s.get("capabilities", []):
                doc_tokens.extend(_tokenize(cap))
            # 加入预定义关键词
            if sid in SCENARIO_KEYWORD_MAP:
                for kw in SCENARIO_KEYWORD_MAP[sid]:
                    doc_tokens.extend(_tokenize(kw))
            scenario_docs[sid] = doc_tokens

        # TF-IDF 相似度
        tfidf_scores = _compute_tfidf_scores(query_tokens, scenario_docs)

        # 关键词直接命中加分
        desc_lower = description.lower()
        keyword_bonus: Dict[str, float] = {}
        for sid, kws in SCENARIO_KEYWORD_MAP.items():
            hits = sum(1 for kw in kws if kw.lower() in desc_lower)
            keyword_bonus[sid] = hits * 0.08  # 每命中一个关键词加 8%

        # 综合得分
        results: List[Tuple[str, str, int, str]] = []
        for sid, s in scenario_map.items():
            raw = tfidf_scores.get(sid, 0.0) + keyword_bonus.get(sid, 0.0)
            confidence = min(100, max(0, int(raw * 100)))
            if confidence > 0:
                rationale = self._build_rationale(sid, description, s, confidence)
                results.append((sid, s["name"], confidence, rationale))

        results.sort(key=lambda x: x[2], reverse=True)
        return results[:5]

    @staticmethod
    def _build_rationale(
        sid: str, desc: str, scenario: Dict, confidence: int
    ) -> str:
        desc_lower = desc.lower()
        matched_kws = []
        for kw in SCENARIO_KEYWORD_MAP.get(sid, []):
            if kw.lower() in desc_lower:
                matched_kws.append(kw)
        if matched_kws:
            return f"匹配关键词: {', '.join(matched_kws[:5])}; 场景描述: {scenario.get('description', '')}"
        return f"基于语义相似度匹配; 场景描述: {scenario.get('description', '')}"


# 预留 LLM 匹配器接口
class LLMScenarioMatcher(ScenarioMatcher):
    """基于大模型的场景匹配器（未来实现）"""
    def match(
        self, description: str, scenarios: List[Dict]
    ) -> List[Tuple[str, str, int, str]]:
        raise NotImplementedError("LLM 匹配器尚未实现，请使用 RuleBasedScenarioMatcher")


# ============ ScenarioMatchSkill ============

class ScenarioMatchSkill(BaseSkill):
    """行业场景匹配 Skill"""

    skill_name = "scenario-match"
    required_role = "user"

    def __init__(self, matcher: Optional[ScenarioMatcher] = None):
        self._matcher = matcher or RuleBasedScenarioMatcher()
        self._scenarios: Optional[List[Dict]] = None

    def _load_scenarios(self) -> List[Dict]:
        """加载场景数据（懒加载 + Redis/内存缓存）"""
        if self._scenarios is None:
            # 尝试从缓存读取
            cached = scenario_cache.get("all_scenarios")
            if cached is not None:
                self._scenarios = cached
                return self._scenarios
            path = os.path.normpath(SCENARIOS_PATH)
            with open(path, "r", encoding="utf-8") as f:
                self._scenarios = json.load(f)
            # 写入缓存
            scenario_cache.set("all_scenarios", self._scenarios)
        return self._scenarios

    async def validate_input(self, request: BaseModel) -> None:
        if isinstance(request, ScenarioMatchRequest):
            if not request.description.strip():
                raise ValueError("业务描述不能为空")

    async def execute(
        self, request: BaseModel, context: SkillContext
    ) -> ScenarioMatchResponse:
        if not isinstance(request, ScenarioMatchRequest):
            raise ValueError("请求类型错误，期望 ScenarioMatchRequest")

        start = time.time()
        scenarios = self._load_scenarios()
        extracted = _extract_entities(request.description)
        raw_matches = self._matcher.match(request.description, scenarios)

        # 过滤 confidence < 30 的结果
        matches = [
            ScenarioMatchResult(
                scenario_id=sid,
                scenario_name=name,
                confidence_score=conf,
                rationale=rationale,
                extracted_entities=extracted,
            )
            for sid, name, conf, rationale in raw_matches
            if conf >= 30
        ]

        return ScenarioMatchResponse(
            matches=matches,
            extracted_entities=extracted,
            processing_time_ms=int((time.time() - start) * 1000),
        )
# @AI_GENERATED: end
