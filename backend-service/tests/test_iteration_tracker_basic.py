"""
Iteration_Tracker 基础功能测试

验证：
1. append_record 可追加迭代记录
2. list_history 返回按 iteration_round 排序的历史
3. get_trend 提取趋势（macro_f1_by_round / label_count_by_round）
4. get_record_by_round 按轮次定位记录
5. 必填字段缺失时抛 ValueError
"""

import pytest
import tempfile
import shutil
import os
from pathlib import Path

from services.iterative_labeling.iteration_tracker import IterationTracker
from services.iterative_labeling.storage.file_backend import FileIterationHistoryRepository


@pytest.fixture
def temp_data_root(monkeypatch):
    """创建临时数据根目录，测试后清理"""
    temp_dir = tempfile.mkdtemp()
    monkeypatch.setenv('ITERATIVE_LABELING_DATA_ROOT', temp_dir)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_append_and_list_history(temp_data_root):
    """测试追加记录和列出历史（按轮次排序）"""
    tracker = IterationTracker(slot='test-slot')
    
    # 追加三条记录（乱序）
    records = [
        {
            'iteration_id': 'iter-r3',
            'iteration_round': 3,
            'dataset_version': 'ds-v3',
            'model_version': 'mdl-v3',
            'accuracy_record': {'macro_f1_mean': 0.81, 'macro_f1_std': 0.02},
            'label_space_version': 'ls-v5',
            'label_count': 5
        },
        {
            'iteration_id': 'iter-r1',
            'iteration_round': 1,
            'dataset_version': 'ds-v1',
            'model_version': 'mdl-v1',
            'accuracy_record': {'macro_f1_mean': 0.75, 'macro_f1_std': 0.03},
            'label_space_version': 'ls-v3',
            'label_count': 3
        },
        {
            'iteration_id': 'iter-r2',
            'iteration_round': 2,
            'dataset_version': 'ds-v2',
            'model_version': 'mdl-v2',
            'accuracy_record': {'macro_f1_mean': 0.78, 'macro_f1_std': 0.025},
            'label_space_version': 'ls-v4',
            'label_count': 4
        }
    ]
    
    for record in records:
        tracker.append_record(record)
    
    # 列出历史（应按 iteration_round 升序）
    history = tracker.list_history()
    assert len(history) == 3
    assert history[0]['iteration_round'] == 1
    assert history[1]['iteration_round'] == 2
    assert history[2]['iteration_round'] == 3
    
    # 验证 created_at 自动生成
    assert 'created_at' in history[0]


def test_get_trend(temp_data_root):
    """测试趋势提取（macro_f1_by_round / label_count_by_round）"""
    tracker = IterationTracker(slot='test-slot')
    
    # 追加三条记录
    records = [
        {
            'iteration_id': 'iter-r1',
            'iteration_round': 1,
            'dataset_version': 'ds-v1',
            'model_version': 'mdl-v1',
            'accuracy_record': {'macro_f1_mean': 0.75},
            'label_space_version': 'ls-v3',
            'label_count': 3
        },
        {
            'iteration_id': 'iter-r2',
            'iteration_round': 2,
            'dataset_version': 'ds-v2',
            'model_version': 'mdl-v2',
            'accuracy_record': {'macro_f1_mean': 0.78},
            'label_space_version': 'ls-v4',
            'label_count': 4
        },
        {
            'iteration_id': 'iter-r3',
            'iteration_round': 3,
            'dataset_version': 'ds-v3',
            'model_version': 'mdl-v3',
            'accuracy_record': {},  # 缺少 macro_f1_mean，应返回 None
            'label_space_version': 'ls-v5',
            'label_count': 5
        }
    ]
    
    for record in records:
        tracker.append_record(record)
    
    # 获取趋势
    trend = tracker.get_trend()
    assert trend['macro_f1_by_round'] == [0.75, 0.78, None]
    assert trend['label_count_by_round'] == [3, 4, 5]


def test_get_record_by_round(temp_data_root):
    """测试按轮次定位记录"""
    tracker = IterationTracker(slot='test-slot')
    
    # 追加两条记录
    records = [
        {
            'iteration_id': 'iter-r1',
            'iteration_round': 1,
            'dataset_version': 'ds-v1',
            'model_version': 'mdl-v1',
            'accuracy_record': {'macro_f1_mean': 0.75},
            'label_space_version': 'ls-v3',
            'label_count': 3
        },
        {
            'iteration_id': 'iter-r2',
            'iteration_round': 2,
            'dataset_version': 'ds-v2',
            'model_version': 'mdl-v2',
            'accuracy_record': {'macro_f1_mean': 0.78},
            'label_space_version': 'ls-v4',
            'label_count': 4
        }
    ]
    
    for record in records:
        tracker.append_record(record)
    
    # 定位存在的轮次
    record_r2 = tracker.get_record_by_round(2)
    assert record_r2 is not None
    assert record_r2['iteration_id'] == 'iter-r2'
    assert record_r2['dataset_version'] == 'ds-v2'
    
    # 定位不存在的轮次
    record_r99 = tracker.get_record_by_round(99)
    assert record_r99 is None


def test_append_missing_required_fields(temp_data_root):
    """测试必填字段缺失时抛 ValueError"""
    tracker = IterationTracker(slot='test-slot')
    
    # 缺少 iteration_id
    with pytest.raises(ValueError, match='缺少必填字段'):
        tracker.append_record({
            'iteration_round': 1,
            'dataset_version': 'ds-v1',
            'model_version': 'mdl-v1',
            'accuracy_record': {},
            'label_space_version': 'ls-v3',
            'label_count': 3
        })
    
    # 缺少 label_count
    with pytest.raises(ValueError, match='缺少必填字段'):
        tracker.append_record({
            'iteration_id': 'iter-r1',
            'iteration_round': 1,
            'dataset_version': 'ds-v1',
            'model_version': 'mdl-v1',
            'accuracy_record': {},
            'label_space_version': 'ls-v3'
        })


def test_empty_history(temp_data_root):
    """测试空槽位返回空历史和空趋势"""
    tracker = IterationTracker(slot='empty-slot')
    
    history = tracker.list_history()
    assert history == []
    
    trend = tracker.get_trend()
    assert trend['macro_f1_by_round'] == []
    assert trend['label_count_by_round'] == []

