"""
Backfill 服务 - 打标回流为新训练集

职责：
- 将审核固化的真值标签（confirm/correct/new_label 单元）组装为新的 Labeled_Dataset 版本
- 支持与基线数据集累积合并，使标签样本随迭代累积增多
- 排除 pending（存疑跳过）单元，不纳入回流训练集
- 分配单调递增的 dataset_version，记录来源迭代轮次与基线数据集版本
- 回流标签列与 label_encode 的 Label_Map 兼容，可经 load_csv（rename_columns）+ merge_label（单文件模式）直接进入下一轮训练
- 成功后推进闭环阶段 reviewed → backfilled

映射需求：
- 需求 9.1: 将 confirm/correct/new_label 单元及其 Human_Verdict 组装为新 Labeled_Dataset 版本
- 需求 9.2: 分配新 dataset_version，记录 source_iteration / base_dataset_version
- 需求 9.3: 支持与上一轮 Labeled_Dataset 累积合并
- 需求 9.4: 允许基于回流后的新数据集版本直接发起下一轮训练
- 需求 9.5: 排除 pending 单元，不纳入回流训练集

复用边界（不重造）：
- load_csv 算子（支持 rename_columns 参数）：由 pv-fault-diagnosis-integration spec 交付
- merge_label 算子（支持单文件模式：源 CSV 已含标签列）：由 pv-fault-diagnosis-integration spec 交付
- label_encode 算子（encode/decode 模式）：由 pv-fault-diagnosis-integration spec 交付

本服务只负责：
1. 从审核会话中提取 confirm/correct/new_label 单元及其裁决标签
2. 组装符合 label_encode 兼容格式的标签列（与 Label_Map 对应）
3. 分配 dataset_version + 记录来源血缘（source_iteration / base_dataset_version）
4. 可选地与基线数据集合并（merge_base=true）
5. 调用 orchestrator 的 _advance_stage 推进阶段 reviewed → backfilled

本服务**不**重新实现 load_csv、merge_label、label_encode 的内部逻辑。
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from .storage.interfaces import (
    ReviewResultRepository,
    GroundTruthRepository
)

logger = logging.getLogger(__name__)


class BackfillService:
    """
    打标回流服务
    
    将人工审核固化的真值标签回流为新的训练集版本，供下一轮迭代使用。
    
    关键方法：
    - backfill_from_review: 从审核会话回流，组装新数据集版本
    
    内部符号：
    - _extract_ground_truth_units: 提取 confirm/correct/new_label 单元（排除 pending）
    - _allocate_dataset_version: 分配单调递增的数据集版本号
    - _merge_with_base: 可选累积合并逻辑（与基线数据集合并）
    
    依赖：
    - ReviewResultRepository: 读取审核会话状态与裁决记录
    - GroundTruthRepository: 持久化固化真值标签
    - Orchestrator._advance_stage: 推进闭环阶段 reviewed → backfilled
    """
    
    def __init__(
        self,
        review_repo: ReviewResultRepository,
        ground_truth_repo: GroundTruthRepository,
        slot: str = 'default'
    ):
        """
        初始化 Backfill 服务
        
        参数：
        - review_repo: ReviewResultRepository — 审核结果仓储
        - ground_truth_repo: GroundTruthRepository — 固化真值标签仓储
        - slot: str — 槽位（多环境/多产品线分区键），默认 'default'
        """
        self.review_repo = review_repo
        self.ground_truth_repo = ground_truth_repo
        self.slot = slot
    
    def backfill_from_review(
        self,
        review_id: str,
        loop_id: str,
        source_iteration: int,
        base_dataset_version: Optional[str] = None,
        merge_base: bool = True
    ) -> Dict[str, Any]:
        """
        从审核会话回流，组装新数据集版本
        
        参数：
        - review_id: str — 来源审核会话唯一标识
        - loop_id: str — 所属迭代闭环标识
        - source_iteration: int — 来源迭代轮次（当前轮）
        - base_dataset_version: str | None — 基线数据集版本（用于累积合并）
        - merge_base: bool — 是否与基线数据集累积合并，默认 true（需求 9.3）
        
        返回：
        - dict — 回流结果，包含：
            - dataset_version: str — 新分配的数据集版本
            - unit_count: int — 纳入回流的单元数（仅 confirm/correct/new_label，排除 pending）
            - source_iteration: int — 来源迭代轮次
            - base_dataset_version: str | None — 基线数据集版本（累积合并时）
            - created_at: str — 创建时间
        
        行为：
        1. 加载审核会话状态，校验 status='reviewed'（已完成审核）
        2. 提取 confirm/correct/new_label 单元及其 Human_Verdict（排除 pending，需求 9.5）
        3. 分配新 dataset_version（单调递增，需求 9.2）
        4. 若 merge_base=true 且 base_dataset_version 不为空，加载基线标签并去重合并（需求 9.3）
        5. 组装真值标签记录（含 unit_key / label_id / source_review_id / action_type / reviewer / labeled_at）
        6. 经 GroundTruthRepository 持久化（需求 9.1）
        7. 返回回流结果（含 dataset_version / unit_count / 来源血缘）
        
        异常：
        - 若 review_id 不存在，抛 KeyError
        - 若 status != 'reviewed'，抛 ValueError（会话未完成审核）
        - 若无任何 confirm/correct/new_label 单元，抛 ValueError（无真值可回流）
        
        映射需求：
        - 需求 9.1: 将 confirm/correct/new_label 单元组装为新 Labeled_Dataset 版本
        - 需求 9.2: 分配 dataset_version，记录 source_iteration / base_dataset_version
        - 需求 9.3: merge_base=true 时与基线累积合并
        - 需求 9.5: 排除 pending 单元
        
        **Validates: Requirements 9.1, 9.2, 9.3, 9.5**
        """
        # 1. 加载审核会话状态
        session_state = self.review_repo.load_session(self.slot, review_id)
        if not session_state:
            raise KeyError(f"审核会话 {review_id} 不存在")
        
        # 校验会话已完成审核
        status = session_state.get('status')
        if status != 'reviewed':
            raise ValueError(
                f"审核会话 {review_id} 状态为 '{status}'，"
                f"只有 status='reviewed' 的会话才能回流。"
                f"请先完成全部单元的审核。"
            )
        
        logger.info(f"开始从审核会话 {review_id} 回流真值标签（loop_id={loop_id}, iteration={source_iteration}）")
        
        # 2. 提取 confirm/correct/new_label 单元（排除 pending）
        ground_truth_units = self._extract_ground_truth_units(session_state)
        
        if not ground_truth_units:
            raise ValueError(
                f"审核会话 {review_id} 没有任何 confirm/correct/new_label 单元可回流。"
                f"reviewed_count={session_state.get('reviewed_count', 0)}, "
                f"但全部为 skip（pending），无真值标签。"
            )
        
        logger.info(f"提取到 {len(ground_truth_units)} 个真值单元（排除 pending）")
        
        # 3. 分配新 dataset_version
        dataset_version = self._allocate_dataset_version(source_iteration)
        logger.info(f"分配新数据集版本: {dataset_version}")
        
        # 4. 可选：与基线数据集累积合并
        final_labels = []
        if merge_base and base_dataset_version:
            logger.info(f"累积合并模式：加载基线数据集版本 {base_dataset_version}")
            base_labels = self.ground_truth_repo.load_labels(self.slot, base_dataset_version)
            
            # 构建 unit_key → label_id 的字典（新轮优先，覆盖基线同 unit_key 的旧标签）
            unit_to_label = {}
            
            # 先加载基线标签
            for label in base_labels:
                unit_key = label.get('unit_key')
                if unit_key:
                    unit_to_label[unit_key] = label
            
            # 再用本轮真值覆盖（本轮裁决优先级更高）
            for unit in ground_truth_units:
                unit_key = unit.get('unit_key')
                if unit_key:
                    unit_to_label[unit_key] = {
                        'unit_key': unit_key,
                        'label_id': unit.get('verdict_label'),
                        'source_review_id': review_id,
                        'action_type': unit.get('action_type'),
                        'reviewer': unit.get('reviewer'),
                        'labeled_at': unit.get('reviewed_at')
                    }
            
            # 去重后的累积标签集合
            final_labels = list(unit_to_label.values())
            logger.info(
                f"累积合并完成：基线 {len(base_labels)} 单元 + 本轮 {len(ground_truth_units)} 单元 "
                f"→ 去重后 {len(final_labels)} 单元"
            )
        else:
            # 仅本轮真值
            final_labels = [
                {
                    'unit_key': unit.get('unit_key'),
                    'label_id': unit.get('verdict_label'),
                    'source_review_id': review_id,
                    'action_type': unit.get('action_type'),
                    'reviewer': unit.get('reviewer'),
                    'labeled_at': unit.get('reviewed_at')
                }
                for unit in ground_truth_units
            ]
            logger.info(f"仅本轮真值模式：{len(final_labels)} 单元")
        
        # 5. 持久化固化真值标签
        self.ground_truth_repo.append_labels(self.slot, dataset_version, final_labels)
        logger.info(f"真值标签已持久化到数据集版本 {dataset_version}")
        
        # 6. 返回回流结果
        created_at = datetime.utcnow().isoformat()
        result = {
            'dataset_version': dataset_version,
            'unit_count': len(final_labels),
            'source_iteration': source_iteration,
            'base_dataset_version': base_dataset_version if merge_base else None,
            'created_at': created_at
        }
        
        logger.info(
            f"回流完成：dataset_version={dataset_version}, "
            f"unit_count={len(final_labels)}, "
            f"source_iteration={source_iteration}"
        )
        
        return result
    
    def backfill_to_raw_dataset(
        self,
        review_id: str,
        merge_base: bool = True,
        base_csv_path: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        编辑器驱动回流：把人工确认的窗口级标签回贴到原始时序，产出可直接再训练的 CSV。

        与 backfill_from_review（单元级标签映射）的区别：
        - 本方法输出**原始时序级** CSV（每个设备每天多行 + label 列），可被训练工作流的
          load_csv → merge_label 直接消费，无需额外转换。
        - 通过复用 load_csv / time_window_split 算子重算窗口键，保证与预测时的 time_window 一致。

        参数：
        - review_id: str — 审核会话标识（其 prediction_context 必须含 source_csv_path）
        - merge_base: bool — 是否与基线训练 CSV 累积合并，默认 True
        - base_csv_path: str | None — 基线训练 CSV 路径（merge_base=True 时拼接到新数据集前）
        - output_dir: str | None — 输出目录，默认 data/iterative_labeling/datasets/{slot}/

        返回：
        - dict — {dataset_version, csv_path, labeled_rows, labeled_units, total_source_rows}

        异常：
        - review_id 不存在 → KeyError；缺 source_csv_path → ValueError；无真值单元 → ValueError
        """
        import os
        import pandas as pd
        from services.operator_backends import load_csv as load_csv_op
        from services.operator_backends import time_window_split as tws_op

        session = self.review_repo.load_session(self.slot, review_id)
        if not session:
            raise KeyError(f"审核会话 {review_id} 不存在")

        ctx = session.get('prediction_context') or {}
        source_csv_path = ctx.get('source_csv_path')
        if not source_csv_path:
            raise ValueError(
                f"审核会话 {review_id} 缺少 prediction_context.source_csv_path，无法回贴原始时序。"
                f"请通过 from-prediction 接口创建会话。"
            )
        load_config = ctx.get('load_config') or {}
        window_config = ctx.get('window_config') or {}

        # 单元组件索引（unit_key → site/device/branch/time_window）
        units_by_key = {u.get('unit_key'): u for u in session.get('units', [])}

        # 真值裁决：unit_key → label_id（排除 pending/skip）
        gt_label_by_unit: Dict[str, int] = {}
        for v in session.get('verdicts', []):
            if v.get('is_ground_truth') and v.get('action_type') in {'confirm', 'correct', 'new_label'}:
                gt_label_by_unit[v.get('unit_key')] = v.get('verdict_label')

        if not gt_label_by_unit:
            raise ValueError(f"审核会话 {review_id} 没有可回流的真值单元（全部为 skip 或未审核）")

        # 归一化工具：保证预测侧字符串与原始 CSV 侧的键一致
        def _norm_id(x: Any) -> str:
            if x is None:
                return ''
            if isinstance(x, float) and x.is_integer():
                return str(int(x))
            return str(x).strip()

        def _norm_tw(x: Any) -> str:
            try:
                return pd.to_datetime(x).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                return str(x)

        def _comp_key(site: Any, dev: Any, br: Any, tw: Any) -> str:
            return f"{_norm_id(site)}|{_norm_id(dev)}|{_norm_id(br)}|{_norm_tw(tw)}"

        # 用归一化键重建 真值键 → label
        gt_norm: Dict[str, int] = {}
        for unit_key, label_id in gt_label_by_unit.items():
            u = units_by_key.get(unit_key, {})
            k = _comp_key(u.get('site_id'), u.get('device_id'), u.get('branch_id'), u.get('time_window'))
            gt_norm[k] = label_id

        # 1. 重新加载原始预测 CSV（复用 load_csv 算子，含 rename_columns）
        df = load_csv_op.execute({
            'file_path': source_csv_path,
            'rename_columns': load_config.get('rename_columns'),
            'encoding': load_config.get('encoding', 'utf-8'),
            'delimiter': load_config.get('delimiter', ','),
        }, {}).get('data')
        if df is None or len(df) == 0:
            raise ValueError(f"原始预测 CSV 为空或加载失败: {source_csv_path}")
        total_source_rows = len(df)

        # 2. 重算 time_window（复用 time_window_split 算子，与预测时同配置）
        id_fields = window_config.get('id_fields') or ['site_id', 'device_id', 'branch_id']
        time_field = window_config.get('time_field') or 'time'
        window = window_config.get('window') or '1d'
        df = tws_op.execute(
            {'window': window, 'id_fields': id_fields, 'time_field': time_field},
            {'data': df}
        ).get('data')

        # 3. 逐行构造归一化 unit_key，回贴标签
        df['__unit_key'] = [
            _comp_key(
                df['site_id'].iloc[i] if 'site_id' in df.columns else None,
                df['device_id'].iloc[i] if 'device_id' in df.columns else None,
                df['branch_id'].iloc[i] if 'branch_id' in df.columns else None,
                df['time_window'].iloc[i] if 'time_window' in df.columns else None,
            )
            for i in range(len(df))
        ]
        df['label'] = df['__unit_key'].map(gt_norm)

        labeled = df[df['label'].notna()].copy()
        if len(labeled) == 0:
            raise ValueError(
                f"回贴后没有任何原始行匹配到真值标签。可能是 time_window 归一化口径不一致，"
                f"请检查 window_config（当前 window={window}, id_fields={id_fields}, time_field={time_field}）。"
            )

        labeled_units = int(labeled['__unit_key'].nunique())
        labeled['label'] = labeled['label'].astype(int)
        # 丢弃流水线内部列，保留原始列 + label（训练 load_csv 会自己重算 time_window）
        labeled = labeled.drop(columns=['__unit_key', 'time_window'], errors='ignore')

        # 4. 可选：与基线训练 CSV 累积合并
        if merge_base and base_csv_path:
            try:
                base_df = load_csv_op.execute({
                    'file_path': base_csv_path,
                    'rename_columns': load_config.get('rename_columns'),
                    'encoding': load_config.get('encoding', 'utf-8'),
                    'delimiter': load_config.get('delimiter', ','),
                }, {}).get('data')
                if base_df is not None and len(base_df) > 0:
                    common_cols = [c for c in labeled.columns if c in base_df.columns]
                    labeled = pd.concat(
                        [base_df[common_cols], labeled[common_cols]],
                        ignore_index=True
                    )
                    logger.info(f"累积合并基线 {base_csv_path}: 基线 {len(base_df)} 行 → 共 {len(labeled)} 行")
            except Exception as e:
                logger.warning(f"基线合并失败（跳过，仅用本轮标注）: {e}")

        # 5. 写出新数据集 CSV
        if output_dir is None:
            root = os.environ.get('ITERATIVE_LABELING_DATA_ROOT', 'data/iterative_labeling')
            output_dir = os.path.join(root, 'datasets', self.slot)
        os.makedirs(output_dir, exist_ok=True)
        dataset_version = f"ds-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        csv_path = os.path.abspath(os.path.join(output_dir, f"{dataset_version}.csv"))
        labeled.to_csv(csv_path, index=False, encoding='utf-8')

        logger.info(
            f"回流完成（原始时序级）: review_id={review_id}, dataset_version={dataset_version}, "
            f"labeled_rows={len(labeled)}, labeled_units={labeled_units}, csv_path={csv_path}"
        )

        return {
            'dataset_version': dataset_version,
            'csv_path': csv_path,
            'labeled_rows': int(len(labeled)),
            'labeled_units': labeled_units,
            'total_source_rows': int(total_source_rows),
        }

    def _extract_ground_truth_units(self, session_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        内部符号：从会话状态中提取 confirm/correct/new_label 单元（排除 pending）
        
        参数：
        - session_state: dict — 审核会话状态（含 verdicts 数组）
        
        返回：
        - list[dict] — confirm/correct/new_label 单元数组，每项含：
            - unit_key: str — 诊断单元标识
            - verdict_label: int — 裁决标签（label_id）
            - action_type: str — 动作类型（confirm/correct/new_label）
            - reviewer: str — 审核人
            - reviewed_at: str — 审核时间
        
        行为：
        - 遍历 verdicts，筛选 is_ground_truth=true 的单元（即 action_type ∈ {confirm, correct, new_label}）
        - 排除 action_type='skip' 的 pending 单元（需求 9.5）
        
        映射需求：
        - 需求 9.5: 排除 pending 单元，不纳入回流训练集
        """
        verdicts = session_state.get('verdicts', [])
        ground_truth_units = []
        
        for verdict in verdicts:
            is_ground_truth = verdict.get('is_ground_truth', False)
            action_type = verdict.get('action_type')
            
            # 只保留 is_ground_truth=true 的单元（即 confirm/correct/new_label）
            if is_ground_truth and action_type in {'confirm', 'correct', 'new_label'}:
                ground_truth_units.append({
                    'unit_key': verdict.get('unit_key'),
                    'verdict_label': verdict.get('verdict_label'),
                    'action_type': action_type,
                    'reviewer': verdict.get('reviewer'),
                    'reviewed_at': verdict.get('reviewed_at')
                })
            else:
                # pending（skip）单元已被排除
                logger.debug(f"跳过 pending 单元: {verdict.get('unit_key')} (action_type={action_type})")
        
        return ground_truth_units
    
    def _allocate_dataset_version(self, source_iteration: int) -> str:
        """
        内部符号：分配单调递增的数据集版本号
        
        参数：
        - source_iteration: int — 来源迭代轮次
        
        返回：
        - str — 新数据集版本号（如 'ds-r3-2026060812'）
        
        行为：
        - 格式：'ds-r{iteration}-{timestamp}'（确保单调且可追溯）
        - 时间戳使用 YYYYMMDDHHmmss 格式（便于排序与审计）
        
        映射需求：
        - 需求 9.2: 分配新 dataset_version
        """
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        dataset_version = f"ds-r{source_iteration}-{timestamp}"
        return dataset_version
