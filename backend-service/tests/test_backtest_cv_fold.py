from api.workflows_enhanced import EnhancedWorkflow, _aggregate_cv_fold_metrics, _execute_backtest


def _folds(offset=0.0):
    return [
        {
            "fold_id": i,
            "train_loss": float(10 + i + offset),
            "val_loss": float(12 + i + offset),
            "val_mape": float(5 + i + offset),
        }
        for i in range(1, 6)
    ]


def test_aggregate_cv_fold_metrics_returns_complete_fold_structure():
    daily_results = [
        {"status": "success", "cv_fold_metrics": _folds(0.0)},
        {"status": "success", "cv_fold_metrics": _folds(2.0)},
        {"status": "failed", "cv_fold_metrics": _folds(100.0)},
    ]

    result = _aggregate_cv_fold_metrics(daily_results)

    assert len(result) == 5
    assert [item["fold_id"] for item in result] == [1, 2, 3, 4, 5]
    for item in result:
        assert set(item) == {"fold_id", "train_loss", "val_loss", "val_mape"}
        assert item["train_loss"] > 0
        assert item["val_loss"] > 0
        assert item["val_mape"] >= 0
        assert item["val_loss"] >= item["train_loss"]

    assert result[0]["train_loss"] == 12.0
    assert result[0]["val_loss"] == 14.0
    assert result[0]["val_mape"] == 7.0


def test_execute_backtest_includes_cv_fold_metrics(monkeypatch):
    workflow = EnhancedWorkflow(name="cv-test", nodes=[], edges=[], metadata={"global_config": {}})
    calls = {"count": 0}

    def fake_execute_pipeline_sync(_workflow):
        calls["count"] += 1
        offset = float(calls["count"] - 1)
        return {
            "success": True,
            "metrics": {"smape": 3.0 + offset, "rmse": 10.0, "mae": 5.0},
            "y_true": [100.0, 110.0],
            "y_pred": [101.0, 109.0],
            "cv_fold_metrics": _folds(offset),
        }

    monkeypatch.setattr("api.workflows_enhanced._execute_pipeline_sync", fake_execute_pipeline_sync)

    result = _execute_backtest(workflow, "2026-04-01", "2026-04-02")

    assert result["success_days"] == 2
    assert "cv_fold_metrics" in result
    assert len(result["cv_fold_metrics"]) == 5
    assert result["daily_results"][0]["cv_fold_metrics"] == _folds(0.0)
    assert result["daily_results"][1]["cv_fold_metrics"] == _folds(1.0)
    for item in result["cv_fold_metrics"]:
        assert set(item) == {"fold_id", "train_loss", "val_loss", "val_mape"}
        assert item["train_loss"] > 0
        assert item["val_loss"] > 0
        assert item["val_mape"] >= 0
