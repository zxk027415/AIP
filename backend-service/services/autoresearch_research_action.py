"""
autoresearch_research_action.py
第六代 AutoResearch 核心数据模型：ResearchAction schema 和 Evidence Ledger Entry。

职责：
  - 定义 ResearchAction（研究动作）的类型化 schema
  - 定义 EvidenceLedgerEntry（统一证据条目）
  - 定义 ProfileSignal（画像信号）用于 profile-to-action 映射
  - 提供 action 编译为 runtime patch 的接口

设计文档：ob/AutoResearch第六代演进设计与任务拆解.md
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ─── T1: 成功标准指标 ─────────────────────────────────────────────────────────

@dataclass
class ResearchQualityMetrics:
    """第六代研究质量评估指标（T1 产出）。

    Attributes:
        novelty_rate（新颖率）: new_count / total_candidates，越高越好
        action_success_rate（动作成功率）: positive_evidence / total_actions
        multi_window_confirmed_rate（多窗口确认率）: confirmed / total_evidence
        duplicate_patch_rate（重复补丁率）: duplicate_count / total_candidates，越低越好
        question_resolution_rate（问题解决率）: resolved / total_questions
    """
    novelty_rate: float = 0.0
    action_success_rate: float = 0.0
    multi_window_confirmed_rate: float = 0.0
    duplicate_patch_rate: float = 0.0
    question_resolution_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def compute_from_run(cls, run_state: Dict[str, Any]) -> "ResearchQualityMetrics":
        """从 run_state 快照计算研究质量指标。"""
        novelty = run_state.get("novelty_summary") or {}
        new_count = int(novelty.get("new_count") or 0)
        dup_count = int(novelty.get("duplicate_count") or 0)
        total_cand = new_count + dup_count

        evidence_records = run_state.get("evidence_records") or []
        total_evidence = len(evidence_records)
        confirmed = sum(
            1 for e in evidence_records
            if isinstance(e, dict) and str(e.get("evidence_strength")) == "multi_window_confirmed"
        )
        positive = sum(
            1 for e in evidence_records
            if isinstance(e, dict) and str(e.get("evidence_strength")) in {
                "single_window_positive", "multi_window_confirmed"
            }
        )

        questions = run_state.get("research_questions") or []
        total_q = len(questions)
        resolved_q = sum(
            1 for q in questions
            if isinstance(q, dict) and str(q.get("status")) == "resolved"
        )

        return cls(
            novelty_rate=new_count / total_cand if total_cand > 0 else 0.0,
            action_success_rate=positive / total_evidence if total_evidence > 0 else 0.0,
            multi_window_confirmed_rate=confirmed / total_evidence if total_evidence > 0 else 0.0,
            duplicate_patch_rate=dup_count / total_cand if total_cand > 0 else 0.0,
            question_resolution_rate=resolved_q / total_q if total_q > 0 else 0.0,
        )


# ─── T2: ResearchAction schema ───────────────────────────────────────────────

@dataclass
class ProfileCondition:
    """画像适用条件（`applicable_profile`）。

    Attributes:
        signal（信号名）: 如 "volatility_high", "weekend_sensitive", "drift_strong"
        operator（比较算子）: "eq", "gt", "lt", "in", "not_in"
        value（阈值或枚举）: 比较值
    """
    signal: str
    operator: str = "eq"
    value: Any = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchAction:
    """研究动作（第六代核心单元）。

    每个 action 代表一个有明确假设、可编译为 patch、有停止条件的实验单元。
    与 v1/v2 registry 的区别：v1/v2 的 param 只是枚举值，action 是带假设和证据期望的实验。

    Attributes:
        action_id（动作 ID）: 全局唯一标识，如 "short_window_vs_long_window"
        action_type（动作类型）: "ablation" / "probe" / "compare" / "sweep"
        target_direction（目标方向）: "parameter" / "feature" / "model" / "data" / "risk"
        target_layer（目标层）: "training" / "feature" / "model" / "data"
        description（描述）: 人类可读的实验假设
        applicable_profile（适用画像条件列表）: 满足时才激活该 action
        patch_template（补丁模板）: 可直接编译为 runtime patch 的结构
        max_changed_variables（最大变更变量数）: 单变量控制原则上限
        risk_level（风险等级）: "low" / "medium" / "high"
        expected_evidence（期望证据描述）: 成功/失败时应观察到什么
        stop_conditions（停止条件列表）: 满足时不再重复执行
        fallback_actions（降级动作 ID 列表）: 本 action 失败后可尝试的替代
        known_anti_patterns（已知反模式列表）: 已证明无效的变量组合
        cooldown_iterations（冷却轮数）: 同 run 内连续失败后等待几轮
        stage（实验阶段）: "A" / "B" / "C"，对应 probe / formal / verification
    """
    action_id: str
    action_type: str = "compare"
    target_direction: str = "parameter"
    target_layer: str = "training"
    description: str = ""
    applicable_profile: List[ProfileCondition] = field(default_factory=list)
    patch_template: Dict[str, Any] = field(default_factory=dict)
    max_changed_variables: int = 2
    risk_level: str = "low"
    expected_evidence: str = ""
    stop_conditions: List[str] = field(default_factory=list)
    fallback_actions: List[str] = field(default_factory=list)
    known_anti_patterns: List[str] = field(default_factory=list)
    cooldown_iterations: int = 3
    stage: str = "B"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["applicable_profile"] = [p.to_dict() if hasattr(p, "to_dict") else p for p in self.applicable_profile]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchAction":
        profiles = [
            ProfileCondition(**p) if isinstance(p, dict) else p
            for p in (data.get("applicable_profile") or [])
        ]
        return cls(
            action_id=str(data.get("action_id") or ""),
            action_type=str(data.get("action_type") or "compare"),
            target_direction=str(data.get("target_direction") or "parameter"),
            target_layer=str(data.get("target_layer") or "training"),
            description=str(data.get("description") or ""),
            applicable_profile=profiles,
            patch_template=data.get("patch_template") or {},
            max_changed_variables=int(data.get("max_changed_variables") or 2),
            risk_level=str(data.get("risk_level") or "low"),
            expected_evidence=str(data.get("expected_evidence") or ""),
            stop_conditions=list(data.get("stop_conditions") or []),
            fallback_actions=list(data.get("fallback_actions") or []),
            known_anti_patterns=list(data.get("known_anti_patterns") or []),
            cooldown_iterations=int(data.get("cooldown_iterations") or 3),
            stage=str(data.get("stage") or "B"),
        )


# ─── T6: Evidence Ledger Entry ────────────────────────────────────────────────

@dataclass
class EvidenceLedgerEntry:
    """统一证据条目（T6 产出）。

    所有实验结论的单一事实来源。候选池、复验池、问题生命周期、知识层
    都从这里派生状态，而不是各自维护独立的 evidence 字段。

    Attributes:
        evidence_id（证据 ID）: 全局唯一
        run_id（来源 run ID）: AutoResearch run 标识
        iteration（来源迭代）: run 内第几轮
        group_idx（组索引）: batch 模式下的组号
        action_id（关联动作 ID）: 对应 ResearchAction.action_id
        research_question_id（关联问题 ID）: 对应 question_key
        patch_fingerprint（补丁指纹）: 内容哈希，用于去重
        changed_variables（变更变量列表）: 本次实际改了哪些参数
        profile_fingerprint（画像指纹）: 执行时的数据画像条件哈希
        windows_total（总窗口数）: 回测窗口数量
        windows_challenger_better（胜出窗口数）: challenger 优于 baseline 的窗口数
        evidence_strength（证据强度）: "single_window_positive" / "single_window_negative" /
            "multi_window_confirmed" / "multi_window_rejected" / "insufficient_evidence"
        mape_improvement（MAPE 改善量）: 聚合分差
        baseline_metric（基线指标值）: aggregate baseline MAPE
        challenger_metric（挑战者指标值）: aggregate challenger MAPE
        failure_reason（失败原因）: 非 positive 时的结构化原因
        novelty_result（新颖性结果）: "novel" / "duplicate" / "near_duplicate"
        stage（实验阶段）: "A" / "B" / "C"
        status（状态）: "active" / "promoted" / "rejected" / "stale"
        created_at（创建时间）: ISO 格式
        verified_by（复验项 ID）: 若由复验池产生
    """
    evidence_id: str = ""
    run_id: str = ""
    iteration: int = 0
    group_idx: Optional[int] = None
    action_id: str = ""
    research_question_id: str = ""
    patch_fingerprint: str = ""
    changed_variables: List[str] = field(default_factory=list)
    profile_fingerprint: str = ""
    windows_total: int = 0
    windows_challenger_better: int = 0
    evidence_strength: str = "insufficient_evidence"
    mape_improvement: float = 0.0
    baseline_metric: Optional[float] = None
    challenger_metric: Optional[float] = None
    failure_reason: Optional[str] = None
    novelty_result: str = "novel"
    stage: str = "B"
    status: str = "active"
    created_at: str = ""
    verified_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceLedgerEntry":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


# ─── T4: Profile Signal（画像信号） ─────────────────────────────────────────────

@dataclass
class ProfileSignal:
    """从 Dataset Profile 提取的结构化信号，用于 action 选路。

    Attributes:
        volatility_level（波动水平）: "low" / "medium" / "high"
        weekend_sensitive（周末敏感）: True/False
        drift_strength（漂移强度）: 0.0~1.0
        weather_correlated（天气相关性）: True/False
        data_length_days（数据天数）: 可用训练数据长度
        noise_level（噪声水平）: "low" / "medium" / "high"
        has_anomaly_windows（是否有异常窗口）: True/False
        dominant_period（主周期模式）: "daily" / "weekly" / "none"
    """
    volatility_level: str = "medium"
    weekend_sensitive: bool = False
    drift_strength: float = 0.0
    weather_correlated: bool = False
    data_length_days: int = 90
    noise_level: str = "medium"
    has_anomaly_windows: bool = False
    dominant_period: str = "daily"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_train_profile(cls, profile: Dict[str, Any]) -> "ProfileSignal":
        """从 TrainProfile.to_dict() 构造信号。"""
        stats = profile.get("load_curve_stats") or {}
        quality = profile.get("data_quality") or {}
        profile_quality = profile.get("profile_quality") or {}
        periodicity = profile.get("periodicity_strength") or {}

        # 波动判断：优先用 cv，不存在时从 std/mean 计算
        cv = stats.get("cv")
        if cv is None:
            mean = stats.get("mean")
            std = stats.get("std")
            if mean and std and float(mean) != 0:
                cv = abs(float(std)) / abs(float(mean))
        if cv is not None:
            volatility = "high" if float(cv) > 0.3 else ("low" if float(cv) < 0.15 else "medium")
        else:
            volatility = "medium"

        # 周末敏感：weekday_weekend_gap > 10%
        gap = profile.get("weekday_weekend_gap")
        weekend_sens = bool(gap is not None and abs(float(gap)) > 0.1)

        # 漂移：从 CrossWindowPattern.drift_signal 获取（如果有）
        cross_window = profile.get("cross_window_pattern") or {}
        drift = float(cross_window.get("drift_signal") or 0.0)

        # 数据长度：优先从 profile_quality.point_count，回退 data_quality
        point_count = (
            profile_quality.get("point_count")
            or quality.get("point_count")
            or quality.get("total_points")
        )
        # 假设 96 点/天
        data_days = int(float(point_count or 0) / 96) if point_count else 90

        # 噪声：missing_rate（注意不是 missing_ratio）
        missing = quality.get("missing_rate") or quality.get("missing_ratio")
        noise = "high" if (missing and float(missing) > 0.05) else "medium"

        # 天气相关性：如果 profile 里有 weather_correlation 字段
        weather_corr = profile.get("weather_correlation") or profile_quality.get("weather_correlation")
        weather_related = bool(weather_corr and float(weather_corr) > 0.3) if weather_corr is not None else False

        # 异常窗口：从 cross_window_pattern.consistently_bad_periods
        bad_periods = cross_window.get("consistently_bad_periods") or []
        has_anomaly = bool(bad_periods)

        return cls(
            volatility_level=volatility,
            weekend_sensitive=weekend_sens,
            drift_strength=drift,
            weather_correlated=weather_related,
            data_length_days=data_days,
            noise_level=noise,
            has_anomaly_windows=has_anomaly,
            dominant_period=str(profile.get("dominant_pattern") or "daily"),
        )

    def matches_condition(self, condition: ProfileCondition) -> bool:
        """判断当前信号是否满足某个 ProfileCondition。"""
        value = getattr(self, condition.signal, None)
        if value is None:
            return False
        op = condition.operator
        target = condition.value
        if op == "eq":
            return value == target
        elif op == "gt":
            return float(value) > float(target)
        elif op == "lt":
            return float(value) < float(target)
        elif op == "in":
            return value in (target if isinstance(target, (list, set)) else [target])
        elif op == "not_in":
            return value not in (target if isinstance(target, (list, set)) else [target])
        return False

    def action_applicable(self, action: ResearchAction) -> bool:
        """判断某个 action 是否适用于当前画像信号。无条件时默认适用。"""
        if not action.applicable_profile:
            return True
        return all(self.matches_condition(c) for c in action.applicable_profile)
