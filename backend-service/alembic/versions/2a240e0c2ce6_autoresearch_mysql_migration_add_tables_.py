# @AI_GENERATED
"""autoresearch mysql migration add tables and fields

Revision ID: 2a240e0c2ce6
Revises: 04407b778fbd
Create Date: 2026-07-09 11:37:49.568256

本迁移只做「新增」，不做任何 drop：
  - 新增 12 张表：autoresearch_job / candidate_promotion_log / candidate_verification /
    deployment_model_version / deployment_slot / experiment_decision / experiment_trial /
    feature_recipe / production_workflow_registry / scheduler_task /
    search_space_registry / switch_event
  - 扩展 experiment_run 加 10 个字段 + 2 个索引

autogenerate 检测到的「remove table」（users/workflows/algorithm_functions 等）都是平台
其他老表，ORM metadata 里没定义所以被误判，这里全部手动去除，绝对不能删。

注意 nullable=False 列的默认值：MySQL 加字段到已有数据的表时必须给 server_default，
否则回填现有行会失败。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a240e0c2ce6'
down_revision: Union[str, None] = '04407b778fbd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. AutoResearch 明细表
    # ------------------------------------------------------------------
    op.create_table(
        'autoresearch_job',
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('pid', sa.Integer(), nullable=True),
        sa.Column('host', sa.String(length=128), nullable=True),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
        sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.PrimaryKeyConstraint('run_id'),
    )
    op.create_index('ix_job_created', 'autoresearch_job', ['created_at'], unique=False)
    op.create_index('ix_job_status_hb', 'autoresearch_job', ['status', 'heartbeat_at'], unique=False)

    op.create_table(
        'candidate_promotion_log',
        sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column('slot', sa.String(length=64), nullable=False),
        sa.Column('candidate_id', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('actor', sa.String(length=64), nullable=True),
        sa.Column('reason', sa.String(length=2048), nullable=True),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_promo_slot_created', 'candidate_promotion_log', ['slot', 'created_at'], unique=False)

    op.create_table(
        'candidate_verification',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('candidate_id', sa.String(length=64), nullable=False),
        sa.Column('slot', sa.String(length=64), nullable=False),
        sa.Column('source_run_id', sa.String(length=64), nullable=True),
        sa.Column('source_iteration', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('config_json', sa.JSON(), nullable=True),
        sa.Column('evidence_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ver_candidate', 'candidate_verification', ['candidate_id'], unique=False)
    op.create_index('ix_ver_slot_status', 'candidate_verification', ['slot', 'status'], unique=False)

    op.create_table(
        'experiment_decision',
        sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('decision_type', sa.String(length=64), nullable=False),
        sa.Column('actor', sa.String(length=64), nullable=True),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_decision_run_seq', 'experiment_decision', ['run_id', 'seq'], unique=False)
    op.create_index('ix_decision_run_type', 'experiment_decision', ['run_id', 'decision_type'], unique=False)

    op.create_table(
        'experiment_trial',
        sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('iteration_no', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('override_json', sa.JSON(), nullable=True),
        sa.Column('evidence_json', sa.JSON(), nullable=True),
        sa.Column('mape_improvement', sa.Float(), nullable=True),
        sa.Column('baseline_mape', sa.Float(), nullable=True),
        sa.Column('challenger_mape', sa.Float(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'iteration_no', name='uq_trial_run_iter'),
    )
    op.create_index('ix_trial_run_iter', 'experiment_trial', ['run_id', 'iteration_no'], unique=False)
    op.create_index('ix_trial_run_status', 'experiment_trial', ['run_id', 'status'], unique=False)

    # ------------------------------------------------------------------
    # 2. 候选池扩展 & 复验
    # ------------------------------------------------------------------
    # candidate_verification 上面已建
    # candidate_promotion_log 上面已建

    # ------------------------------------------------------------------
    # 3. 部署链路表
    # ------------------------------------------------------------------
    op.create_table(
        'deployment_slot',
        sa.Column('slot', sa.String(length=64), nullable=False),
        sa.Column('production_workflow_id', sa.String(length=128), nullable=True),
        sa.Column('cooldown_days', sa.Integer(), nullable=False, server_default=sa.text('3')),
        sa.Column('max_shadow_slots', sa.Integer(), nullable=False, server_default=sa.text('3')),
        sa.Column('max_prelaunch_slots', sa.Integer(), nullable=False, server_default=sa.text('3')),
        sa.Column('training_window_days', sa.Integer(), nullable=True),
        sa.Column('switch_observation_days', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('slot'),
    )

    op.create_table(
        'deployment_model_version',
        sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column('slot', sa.String(length=64), nullable=False),
        sa.Column('workflow_id', sa.String(length=128), nullable=False),
        sa.Column('version_tag', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('accuracy_score', sa.Float(), nullable=True),
        sa.Column('consecutive_better_days', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('source_run_id', sa.String(length=64), nullable=True),
        sa.Column('source_candidate_id', sa.String(length=64), nullable=True),
        sa.Column('prelaunch_meta_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slot', 'workflow_id', name='uq_dmv_slot_wf'),
    )
    op.create_index('ix_dmv_slot_status', 'deployment_model_version', ['slot', 'status'], unique=False)

    op.create_table(
        'switch_event',
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('slot', sa.String(length=64), nullable=False),
        sa.Column('trigger_type', sa.String(length=32), nullable=False),
        sa.Column('from_workflow_id', sa.String(length=128), nullable=True),
        sa.Column('to_workflow_id', sa.String(length=128), nullable=False),
        sa.Column('from_mape', sa.Float(), nullable=True),
        sa.Column('to_mape', sa.Float(), nullable=True),
        sa.Column('actor', sa.String(length=64), nullable=True),
        sa.Column('reason', sa.String(length=2048), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('event_id'),
    )
    op.create_index('ix_switch_slot_ts', 'switch_event', ['slot', 'ts'], unique=False)

    op.create_table(
        'scheduler_task',
        sa.Column('task_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('task_type', sa.String(length=64), nullable=False),
        sa.Column('slot', sa.String(length=64), nullable=True),
        sa.Column('cron_expression', sa.String(length=64), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.Column('last_execution_time', sa.DateTime(), nullable=True),
        sa.Column('last_result_json', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('task_id'),
    )
    op.create_index('ix_task_slot_enabled', 'scheduler_task', ['slot', 'enabled'], unique=False)

    # ------------------------------------------------------------------
    # 4. B' 类静态配置镜像表（文件为源 + DB 镜像）
    # ------------------------------------------------------------------
    op.create_table(
        'search_space_registry',
        sa.Column('registry_id', sa.String(length=64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('description', sa.String(length=512), nullable=True),
        sa.Column('layers_json', sa.JSON(), nullable=True),
        sa.Column('actions_json', sa.JSON(), nullable=True),
        sa.Column('source_path', sa.String(length=512), nullable=True),
        sa.Column('content_hash', sa.CHAR(length=64), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('registry_id'),
    )

    op.create_table(
        'feature_recipe',
        sa.Column('recipe_id', sa.String(length=64), nullable=False),
        sa.Column('description', sa.String(length=512), nullable=True),
        sa.Column('patch_json', sa.JSON(), nullable=True),
        sa.Column('source_path', sa.String(length=512), nullable=True),
        sa.Column('content_hash', sa.CHAR(length=64), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('recipe_id'),
    )

    op.create_table(
        'production_workflow_registry',
        sa.Column('slot', sa.String(length=64), nullable=False),
        sa.Column('workflow_id', sa.String(length=128), nullable=False),
        sa.Column('version_tag', sa.String(length=128), nullable=True),
        sa.Column('meta_json', sa.JSON(), nullable=True),
        sa.Column('source_path', sa.String(length=512), nullable=True),
        sa.Column('content_hash', sa.CHAR(length=64), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('slot'),
    )

    # ------------------------------------------------------------------
    # 5. experiment_run 加字段与索引
    # NOTE: nullable=False 列必须给 server_default，否则已有行回填会挂
    # ------------------------------------------------------------------
    op.add_column('experiment_run', sa.Column('previous_status', sa.String(length=32), nullable=True))
    op.add_column('experiment_run', sa.Column(
        'recoverable', sa.Boolean(), nullable=False, server_default=sa.text('1')
    ))
    op.add_column('experiment_run', sa.Column('baseline_workflow_id', sa.String(length=128), nullable=True))
    op.add_column('experiment_run', sa.Column('current_iteration', sa.Integer(), nullable=True))
    op.add_column('experiment_run', sa.Column('total_iterations', sa.Integer(), nullable=True))
    op.add_column('experiment_run', sa.Column('snapshot_state', sa.JSON(), nullable=True))
    op.add_column('experiment_run', sa.Column('error_message', sa.String(length=2048), nullable=True))
    op.add_column('experiment_run', sa.Column('interrupted_at', sa.DateTime(), nullable=True))
    op.add_column('experiment_run', sa.Column('resumed_at', sa.DateTime(), nullable=True))
    op.add_column('experiment_run', sa.Column(
        'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')
    ))
    op.create_index('ix_experiment_run_slot_status', 'experiment_run', ['slot', 'status'], unique=False)
    op.create_index('ix_experiment_run_updated_at', 'experiment_run', ['updated_at'], unique=False)


def downgrade() -> None:
    """回滚只需删除本次新增的字段和表，不重建其他平台老表。"""
    # experiment_run 回滚字段与索引
    op.drop_index('ix_experiment_run_updated_at', table_name='experiment_run')
    op.drop_index('ix_experiment_run_slot_status', table_name='experiment_run')
    for col in [
        'updated_at', 'resumed_at', 'interrupted_at', 'error_message',
        'snapshot_state', 'total_iterations', 'current_iteration',
        'baseline_workflow_id', 'recoverable', 'previous_status',
    ]:
        op.drop_column('experiment_run', col)

    # 静态配置镜像表
    op.drop_table('production_workflow_registry')
    op.drop_table('feature_recipe')
    op.drop_table('search_space_registry')

    # 部署链路表
    op.drop_index('ix_task_slot_enabled', table_name='scheduler_task')
    op.drop_table('scheduler_task')
    op.drop_index('ix_switch_slot_ts', table_name='switch_event')
    op.drop_table('switch_event')
    op.drop_index('ix_dmv_slot_status', table_name='deployment_model_version')
    op.drop_table('deployment_model_version')
    op.drop_table('deployment_slot')

    # AutoResearch 明细表
    op.drop_index('ix_trial_run_status', table_name='experiment_trial')
    op.drop_index('ix_trial_run_iter', table_name='experiment_trial')
    op.drop_table('experiment_trial')
    op.drop_index('ix_decision_run_type', table_name='experiment_decision')
    op.drop_index('ix_decision_run_seq', table_name='experiment_decision')
    op.drop_table('experiment_decision')
    op.drop_index('ix_ver_slot_status', table_name='candidate_verification')
    op.drop_index('ix_ver_candidate', table_name='candidate_verification')
    op.drop_table('candidate_verification')
    op.drop_index('ix_promo_slot_created', table_name='candidate_promotion_log')
    op.drop_table('candidate_promotion_log')
    op.drop_index('ix_job_status_hb', table_name='autoresearch_job')
    op.drop_index('ix_job_created', table_name='autoresearch_job')
    op.drop_table('autoresearch_job')
# @AI_GENERATED: end
