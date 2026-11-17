from services.autoresearch_convergence_monitor import AutoResearchConvergenceMonitor


def _candidate(mape=None, improvement=None, status="success"):
    evaluation = {}
    if mape is not None:
        evaluation["challenger_mape"] = mape
    if improvement is not None:
        evaluation["mape_improvement"] = improvement
    return {"status": status, "evaluation": evaluation}


def test_check_convergence_requires_enough_success_rounds():
    monitor = AutoResearchConvergenceMonitor()

    result = monitor.check_convergence([_candidate(0.1), _candidate(0.11)], window=3)

    assert result["converged"] is False
    assert result["window_used"] == 2


def test_check_convergence_detects_low_variance():
    monitor = AutoResearchConvergenceMonitor()
    iterations = [_candidate(0.100), _candidate(0.101), _candidate(0.099)]

    result = monitor.check_convergence(iterations, window=3, var_threshold=0.00001)

    assert result["converged"] is True
    assert result["mape_variance"] is not None


def test_check_convergence_handles_missing_mape():
    monitor = AutoResearchConvergenceMonitor()
    iterations = [_candidate(0.1), _candidate(None), _candidate(0.11)]

    result = monitor.check_convergence(iterations, window=3)

    assert result["converged"] is False
    assert result["reason"] == "部分迭代缺少 challenger_mape，无法判断收敛"


def test_parameter_saturation_requires_recent_low_improvements():
    monitor = AutoResearchConvergenceMonitor()

    assert monitor.is_parameter_saturated(
        [_candidate(improvement=0.01), _candidate(improvement=0.02), _candidate(improvement=0.03)],
        k=3,
        threshold=0.05,
    ) is True
    assert monitor.is_parameter_saturated(
        [_candidate(improvement=0.01), _candidate(improvement=0.08), _candidate(improvement=0.03)],
        k=3,
        threshold=0.05,
    ) is False
