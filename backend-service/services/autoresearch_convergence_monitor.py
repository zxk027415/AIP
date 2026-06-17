from typing import Any, Dict, List


class AutoResearchConvergenceMonitor:
    def check_convergence(
        self,
        iterations: List[Dict[str, Any]],
        *,
        window: int = 5,
        var_threshold: float = 0.01,
    ) -> Dict[str, Any]:
        success_iters = [
            item for item in (iterations or [])
            if isinstance(item, dict) and str(item.get("status")) == "success"
        ]
        recent = success_iters[-window:]
        if len(recent) < window:
            return {
                "converged": False,
                "reason": f"成功轮数不足（需 {window} 轮，当前 {len(recent)} 轮）",
                "mape_variance": None,
                "window_used": len(recent),
            }

        mape_values: List[float] = []
        for item in recent:
            evaluation = item.get("evaluation") or {}
            mape = evaluation.get("challenger_mape")
            if mape is not None:
                try:
                    mape_values.append(float(mape))
                except (TypeError, ValueError):
                    pass

        if len(mape_values) < window:
            return {
                "converged": False,
                "reason": "部分迭代缺少 challenger_mape，无法判断收敛",
                "mape_variance": None,
                "window_used": len(mape_values),
            }

        mean_value = sum(mape_values) / len(mape_values)
        variance = sum((value - mean_value) ** 2 for value in mape_values) / len(mape_values)
        converged = variance < var_threshold

        return {
            "converged": converged,
            "reason": (
                f"最近 {window} 轮 MAPE 方差 {variance:.6f} < 阈值 {var_threshold}，判定收敛"
                if converged
                else f"最近 {window} 轮 MAPE 方差 {variance:.6f} >= 阈值 {var_threshold}，未收敛"
            ),
            "mape_variance": round(variance, 6),
            "window_used": window,
        }

    def is_parameter_saturated(
        self,
        iterations: List[Dict[str, Any]],
        *,
        k: int = 4,
        threshold: float = 0.05,
    ) -> bool:
        success_iters = [
            item for item in (iterations or [])
            if isinstance(item, dict) and str(item.get("status")) == "success"
        ]
        recent = success_iters[-k:]
        if len(recent) < k:
            return False
        for item in recent:
            evaluation = item.get("evaluation") or {}
            improvement = evaluation.get("mape_improvement")
            if improvement is None:
                return False
            try:
                if float(improvement) >= threshold:
                    return False
            except (TypeError, ValueError):
                return False
        return True
