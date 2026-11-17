"""
AccuracyEvaluator（三方精度增量计算器）

职责：
以已固化 Human_Verdict 为真值，实时增量计算三方精度对比：
- classifier_accuracy：分类器原始预测精度
- llm_accuracy：LLM 建议精度（仅在有 LLM 建议的单元上计算）
- human_verified_accuracy：人工核对后精度基线（恒 100%）
- llm_coverage：LLM 覆盖率
- macro precision/recall/f1：宏平均指标

只纳入 action_type ∈ {confirm, correct, new_label} 的单元，排除 pending。
每提交一条 Human_Verdict 增量更新，不重算全量。

映射需求：6.1, 6.2, 6.3, 6.4, 6.5

使用示例：
    evaluator = AccuracyEvaluator()
    
    # 每次提交裁决时增量更新
    evaluator.update(
        verdict={"verdict_label": 1, "action_type": "confirm", ...},
        classifier_prediction={"predicted_label": 1, "confidence": 0.87},
        llm_suggestion={"suggested_label": 1, "available": True}
    )
    
    # 获取当前三方精度
    accuracy = evaluator.get_current_accuracy()
"""

from typing import Dict, Optional, List
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class AccuracyEvaluator:
    """
    三方精度增量计算器
    
    维护累计计数状态，每提交一条 Human_Verdict 增量更新三方精度。
    
    Attributes:
        _total_counted: 纳入统计的单元总数（排除 pending）
        _classifier_correct: 分类器预测正确数
        _llm_correct: LLM 建议正确数
        _llm_available_count: 有 LLM 建议的单元数
        _per_class_stats: 每个类别的统计（用于计算 macro 指标）
            {
                label_id: {
                    "tp": 真阳性数,
                    "fp": 假阳性数,
                    "fn": 假阴性数,
                    "support": 该类别在真值中的样本数
                }
            }
    """
    
    def __init__(self):
        """初始化累计计数状态"""
        # 总体计数
        self._total_counted = 0  # 纳入统计的单元数（排除 pending）
        self._classifier_correct = 0  # 分类器预测正确数
        self._llm_correct = 0  # LLM 建议正确数
        self._llm_available_count = 0  # 有 LLM 建议的单元数
        
        # 每个类别的统计（用于 macro 指标）
        # label_id -> {"tp": int, "fp": int, "fn": int, "support": int}
        self._per_class_stats: Dict[int, Dict[str, int]] = defaultdict(
            lambda: {"tp": 0, "fp": 0, "fn": 0, "support": 0}
        )
        # label_source -> counted units / classifier correct
        self._by_source: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"counted": 0, "classifier_correct": 0}
        )
    
    def update(
        self,
        verdict: Dict,
        classifier_prediction: Dict,
        llm_suggestion: Optional[Dict] = None,
        *,
        label_source: Optional[str] = None,
    ) -> None:
        """
        增量更新：提交一条新裁决，更新三方精度
        
        Args:
            verdict: 人工裁决字典
                - verdict_label: 裁决标签（int，真值）
                - action_type: 动作类型（str: confirm/correct/new_label/skip）
            classifier_prediction: 分类器预测字典
                - predicted_label: 预测标签（int）
            llm_suggestion: LLM 建议字典（可选）
                - suggested_label: 建议标签（int）
                - available: 是否可用（bool）
        
        只纳入 action_type ∈ {confirm, correct, new_label} 的单元。
        """
        action_type = verdict.get("action_type")
        
        # 排除 pending（需求 6.2）
        if action_type not in {"confirm", "correct", "new_label"}:
            logger.debug(f"Skipping verdict with action_type={action_type} (not counted)")
            return
        
        verdict_label = verdict.get("verdict_label")
        predicted_label = classifier_prediction.get("predicted_label")
        
        if verdict_label is None or predicted_label is None:
            logger.warning("Skipping verdict: missing verdict_label or predicted_label")
            return
        
        # 纳入统计
        self._total_counted += 1
        source_key = str(label_source or verdict.get("label_source") or "unknown")
        self._by_source[source_key]["counted"] += 1
        
        # 分类器精度
        if predicted_label == verdict_label:
            self._classifier_correct += 1
            self._by_source[source_key]["classifier_correct"] += 1
        
        # LLM 精度（仅在有 LLM 建议的单元上计算，需求 6.5）
        if llm_suggestion and llm_suggestion.get("available", False):
            suggested_label = llm_suggestion.get("suggested_label")
            if suggested_label is not None:
                self._llm_available_count += 1
                if suggested_label == verdict_label:
                    self._llm_correct += 1
        
        # 更新每个类别的统计（用于 macro precision/recall/f1，需求 6.3）
        self._update_per_class_stats(
            true_label=verdict_label,
            predicted_label=predicted_label
        )
    
    def _update_per_class_stats(self, true_label: int, predicted_label: int) -> None:
        """
        更新每个类别的 TP/FP/FN 统计
        
        Args:
            true_label: 真值标签
            predicted_label: 预测标签
        """
        # 增加真值类别的 support
        self._per_class_stats[true_label]["support"] += 1
        
        if true_label == predicted_label:
            # 真阳性：预测为 X 且真值为 X
            self._per_class_stats[true_label]["tp"] += 1
        else:
            # 假阴性：预测为其他类，但真值为 X
            self._per_class_stats[true_label]["fn"] += 1
            # 假阳性：预测为 Y，但真值不是 Y
            self._per_class_stats[predicted_label]["fp"] += 1
    
    def get_current_accuracy(self) -> Dict:
        """
        获取当前三方精度
        
        Returns:
            精度字典，包含：
            - classifier_accuracy: 分类器原始预测精度（float）
            - llm_accuracy: LLM 建议精度（float，仅有建议的单元）
            - human_verified_accuracy: 人工核对后精度基线（float，恒 1.0）
            - llm_coverage: LLM 覆盖率（float）
            - macro: macro 口径指标字典
                - precision: 宏平均精确率（float）
                - recall: 宏平均召回率（float）
                - f1: 宏平均 F1（float）
            - counted_units: 纳入统计的单元数（int）
        
        边界情况（需求 6 接口契约）：
        - 无已审核单元时返回占位值（accuracy=0.0, counted_units=0），不抛异常
        """
        # 边界情况：无已审核单元
        if self._total_counted == 0:
            # @AI_GENERATED
            # P1-3 改动 A：零样本返回 None + accuracy_available=False，
            # 让下游可区分「没有可计量真值」和「全部预测错误」。
            return {
                "classifier_accuracy": None,
                "llm_accuracy": None,
                "human_verified_accuracy": None,
                "llm_coverage": None,
                "macro": {
                    "precision": None,
                    "recall": None,
                    "f1": None,
                },
                "counted_units": 0,
                "by_source": {},
                "accuracy_available": False,
            }
            # @AI_GENERATED: end
        
        # 分类器精度
        classifier_accuracy = self._classifier_correct / self._total_counted
        
        # LLM 精度（仅在有建议的单元上计算，需求 6.5）
        llm_accuracy = 0.0
        if self._llm_available_count > 0:
            llm_accuracy = self._llm_correct / self._llm_available_count
        
        # 人工核对后精度基线（恒 100%，需求 6.1）
        human_verified_accuracy = 1.0
        
        # LLM 覆盖率（需求 6.5）
        llm_coverage = self._llm_available_count / self._total_counted
        
        # macro precision/recall/f1（需求 6.3）
        macro_metrics = self._compute_macro_metrics()
        
        return {
            "classifier_accuracy": classifier_accuracy,
            "llm_accuracy": llm_accuracy,
            "human_verified_accuracy": human_verified_accuracy,
            "llm_coverage": llm_coverage,
            "macro": macro_metrics,
            "counted_units": self._total_counted,
            "by_source": self._compute_by_source_accuracy(),
        }
    
    def _compute_by_source_accuracy(self) -> Dict[str, Dict[str, float]]:
        result: Dict[str, Dict[str, float]] = {}
        for source, stats in self._by_source.items():
            counted = stats["counted"]
            if counted <= 0:
                continue
            result[source] = {
                "counted_units": counted,
                "classifier_accuracy": stats["classifier_correct"] / counted,
            }
        return result
    
    def _compute_macro_metrics(self) -> Dict[str, float]:
        """
        计算 macro precision/recall/f1
        
        macro 口径：对每个类别单独计算 precision/recall/f1，
        然后对所有类别取算术平均（不加权）。
        
        Returns:
            {
                "precision": macro 平均精确率,
                "recall": macro 平均召回率,
                "f1": macro 平均 F1
            }
        """
        if not self._per_class_stats:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        
        precisions = []
        recalls = []
        f1s = []
        
        for label_id, stats in self._per_class_stats.items():
            tp = stats["tp"]
            fp = stats["fp"]
            fn = stats["fn"]
            
            # 精确率：TP / (TP + FP)
            precision = 0.0
            if tp + fp > 0:
                precision = tp / (tp + fp)
            
            # 召回率：TP / (TP + FN)
            recall = 0.0
            if tp + fn > 0:
                recall = tp / (tp + fn)
            
            # F1：2 * (precision * recall) / (precision + recall)
            f1 = 0.0
            if precision + recall > 0:
                f1 = 2 * (precision * recall) / (precision + recall)
            
            precisions.append(precision)
            recalls.append(recall)
            f1s.append(f1)
        
        # macro 平均：算术平均（不加权）
        macro_precision = sum(precisions) / len(precisions) if precisions else 0.0
        macro_recall = sum(recalls) / len(recalls) if recalls else 0.0
        macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
        
        return {
            "precision": macro_precision,
            "recall": macro_recall,
            "f1": macro_f1
        }
    
    def reset(self) -> None:
        """
        重置累计状态（可选，用于开启新会话）
        """
        self._total_counted = 0
        self._classifier_correct = 0
        self._llm_correct = 0
        self._llm_available_count = 0
        self._per_class_stats.clear()
        self._by_source.clear()
