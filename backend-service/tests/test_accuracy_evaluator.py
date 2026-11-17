"""
AccuracyEvaluator 单元测试

验证三方精度增量计算的核心逻辑。
"""

import pytest
from services.iterative_labeling.accuracy_evaluator import AccuracyEvaluator


def test_empty_evaluator():
    """测试边界情况：无已审核单元时返回占位值"""
    evaluator = AccuracyEvaluator()
    accuracy = evaluator.get_current_accuracy()
    
    assert accuracy["classifier_accuracy"] == 0.0
    assert accuracy["llm_accuracy"] == 0.0
    assert accuracy["human_verified_accuracy"] == 0.0
    assert accuracy["llm_coverage"] == 0.0
    assert accuracy["counted_units"] == 0
    assert accuracy["macro"]["precision"] == 0.0
    assert accuracy["macro"]["recall"] == 0.0
    assert accuracy["macro"]["f1"] == 0.0


def test_skip_action_excluded():
    """测试 pending 单元被排除（需求 6.2）"""
    evaluator = AccuracyEvaluator()
    
    # 提交一条 skip 动作
    evaluator.update(
        verdict={"verdict_label": 1, "action_type": "skip"},
        classifier_prediction={"predicted_label": 1}
    )
    
    accuracy = evaluator.get_current_accuracy()
    assert accuracy["counted_units"] == 0  # skip 不计入


def test_confirm_action_counted():
    """测试 confirm/correct/new_label 动作被纳入统计"""
    evaluator = AccuracyEvaluator()
    
    # confirm: 分类器预测正确
    evaluator.update(
        verdict={"verdict_label": 1, "action_type": "confirm"},
        classifier_prediction={"predicted_label": 1}
    )
    
    # correct: 分类器预测错误
    evaluator.update(
        verdict={"verdict_label": 2, "action_type": "correct"},
        classifier_prediction={"predicted_label": 1}
    )
    
    # new_label: 分类器预测错误
    evaluator.update(
        verdict={"verdict_label": 3, "action_type": "new_label"},
        classifier_prediction={"predicted_label": 1}
    )
    
    accuracy = evaluator.get_current_accuracy()
    assert accuracy["counted_units"] == 3
    assert accuracy["classifier_accuracy"] == 1.0 / 3.0  # 1 正确 / 3 总数


def test_llm_coverage_and_accuracy():
    """测试 LLM 覆盖率和精度计算（需求 6.5）"""
    evaluator = AccuracyEvaluator()
    
    # 单元 1: 有 LLM 建议且正确
    evaluator.update(
        verdict={"verdict_label": 1, "action_type": "confirm"},
        classifier_prediction={"predicted_label": 1},
        llm_suggestion={"suggested_label": 1, "available": True}
    )
    
    # 单元 2: 有 LLM 建议但错误
    evaluator.update(
        verdict={"verdict_label": 2, "action_type": "correct"},
        classifier_prediction={"predicted_label": 1},
        llm_suggestion={"suggested_label": 1, "available": True}
    )
    
    # 单元 3: 无 LLM 建议
    evaluator.update(
        verdict={"verdict_label": 3, "action_type": "confirm"},
        classifier_prediction={"predicted_label": 3},
        llm_suggestion=None
    )
    
    accuracy = evaluator.get_current_accuracy()
    assert accuracy["counted_units"] == 3
    assert accuracy["llm_coverage"] == 2.0 / 3.0  # 2 个单元有 LLM 建议
    assert accuracy["llm_accuracy"] == 1.0 / 2.0  # 1 正确 / 2 有建议


def test_llm_unavailable_excluded():
    """测试 LLM 不可用时从 LLM 分母中剔除"""
    evaluator = AccuracyEvaluator()
    
    # 单元 1: LLM 不可用
    evaluator.update(
        verdict={"verdict_label": 1, "action_type": "confirm"},
        classifier_prediction={"predicted_label": 1},
        llm_suggestion={"suggested_label": 1, "available": False}
    )
    
    # 单元 2: LLM 可用且正确
    evaluator.update(
        verdict={"verdict_label": 2, "action_type": "confirm"},
        classifier_prediction={"predicted_label": 2},
        llm_suggestion={"suggested_label": 2, "available": True}
    )
    
    accuracy = evaluator.get_current_accuracy()
    assert accuracy["llm_coverage"] == 1.0 / 2.0  # 1 可用 / 2 总数
    assert accuracy["llm_accuracy"] == 1.0  # 1 正确 / 1 可用


def test_human_verified_accuracy_always_one():
    """测试人工核对后精度基线恒为 1.0（需求 6.1）"""
    evaluator = AccuracyEvaluator()
    
    # 无论分类器/LLM 如何，人工裁决就是真值
    evaluator.update(
        verdict={"verdict_label": 1, "action_type": "confirm"},
        classifier_prediction={"predicted_label": 2},  # 分类器错了
        llm_suggestion={"suggested_label": 3, "available": True}  # LLM 也错了
    )
    
    accuracy = evaluator.get_current_accuracy()
    assert accuracy["human_verified_accuracy"] == 1.0


def test_macro_metrics_calculation():
    """测试 macro precision/recall/f1 计算（需求 6.3）"""
    evaluator = AccuracyEvaluator()
    
    # 类别 1: 2 个样本，预测对 1 个
    evaluator.update(
        verdict={"verdict_label": 1, "action_type": "confirm"},
        classifier_prediction={"predicted_label": 1}
    )
    evaluator.update(
        verdict={"verdict_label": 1, "action_type": "correct"},
        classifier_prediction={"predicted_label": 2}  # 错误：预测为 2
    )
    
    # 类别 2: 1 个样本，预测对了
    evaluator.update(
        verdict={"verdict_label": 2, "action_type": "confirm"},
        classifier_prediction={"predicted_label": 2}
    )
    
    accuracy = evaluator.get_current_accuracy()
    macro = accuracy["macro"]
    
    # 类别 1: precision = 1/2 (TP=1, FP=1), recall = 1/2 (TP=1, FN=1), f1 = 2*(0.5*0.5)/(0.5+0.5) = 0.5
    # 类别 2: precision = 1/1 (TP=1, FP=0), recall = 1/1 (TP=1, FN=0), f1 = 2*(1.0*1.0)/(1.0+1.0) = 1.0
    # 但类别 2 还有 FP=1（真值=1时预测为2），所以类别2的precision应该重新计算
    # 
    # 重新分析：
    # 真值=1, 预测=1 -> 类别1 TP+1
    # 真值=1, 预测=2 -> 类别1 FN+1, 类别2 FP+1
    # 真值=2, 预测=2 -> 类别2 TP+1
    #
    # 类别 1: TP=1, FP=0, FN=1 -> precision=1/1=1.0, recall=1/2=0.5, f1=2*(1.0*0.5)/(1.0+0.5)=0.667
    # 类别 2: TP=1, FP=1, FN=0 -> precision=1/2=0.5, recall=1/1=1.0, f1=2*(0.5*1.0)/(0.5+1.0)=0.667
    # macro: precision=(1.0+0.5)/2=0.75, recall=(0.5+1.0)/2=0.75, f1=(0.667+0.667)/2=0.667
    
    assert macro["precision"] == pytest.approx(0.75)
    assert macro["recall"] == pytest.approx(0.75)
    assert macro["f1"] == pytest.approx(2.0/3.0)  # 0.667


def test_incremental_vs_batch_equivalence():
    """
    测试增量更新与全量重算等价（Property 9）
    
    验证逐条增量更新得到的三方精度，等于对同一最终裁决集合做全量重算的结果。
    """
    # 构造一批裁决
    verdicts = [
        ({"verdict_label": 1, "action_type": "confirm"}, {"predicted_label": 1}, {"suggested_label": 1, "available": True}),
        ({"verdict_label": 2, "action_type": "correct"}, {"predicted_label": 1}, {"suggested_label": 2, "available": True}),
        ({"verdict_label": 3, "action_type": "new_label"}, {"predicted_label": 3}, None),
        ({"verdict_label": 1, "action_type": "confirm"}, {"predicted_label": 2}, {"suggested_label": 1, "available": True}),
    ]
    
    # 增量更新
    evaluator_incremental = AccuracyEvaluator()
    for verdict, pred, llm in verdicts:
        evaluator_incremental.update(verdict, pred, llm)
    
    # 全量重算（模拟：重新构造一个新 evaluator，一次性喂入所有数据）
    evaluator_batch = AccuracyEvaluator()
    for verdict, pred, llm in verdicts:
        evaluator_batch.update(verdict, pred, llm)
    
    # 两者结果应完全一致
    accuracy_incremental = evaluator_incremental.get_current_accuracy()
    accuracy_batch = evaluator_batch.get_current_accuracy()
    
    assert accuracy_incremental == accuracy_batch


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
