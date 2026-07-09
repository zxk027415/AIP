"""create_load_forecast_and_pv_fault_diag

Revision ID: 04407b778fbd
Revises: 
Create Date: 2026-06-25 14:58:02.778100

已调整：所有表建在 aip_algo_platform 库（无 schema= 参数），
不再需要 CREATE DATABASE 权限。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04407b778fbd'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 所有表建在 aip_algo_platform，无需跨库权限
    op.create_table('accuracy_metric',
    sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
    sa.Column('slot', sa.String(length=64), nullable=False),
    sa.Column('workflow_id', sa.String(length=128), nullable=False),
    sa.Column('rolling_mape', sa.Float(), nullable=True),
    sa.Column('rolling_mae', sa.Float(), nullable=True),
    sa.Column('valid_cycle_count', sa.Integer(), nullable=True),
    sa.Column('total_cycle_count', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('last_evaluated_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slot', 'workflow_id', name='uq_accuracy_metric_slot_wf'),
    )
    op.create_table('candidate_pool',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('slot', sa.String(length=64), nullable=False),
    sa.Column('run_id', sa.String(length=64), nullable=False),
    sa.Column('workflow_id', sa.String(length=128), nullable=False),
    sa.Column('patch_signature', sa.String(length=256), nullable=False),
    sa.Column('best_mape', sa.Float(), nullable=True),
    sa.Column('evidence', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_candidate_pool_slot_patch_sig', 'candidate_pool', ['slot', 'patch_signature'], unique=False)
    op.create_table('experiment_run',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('slot', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('config', sa.JSON(), nullable=True),
    sa.Column('runtime_patch', sa.JSON(), nullable=True),
    sa.Column('run_insight', sa.JSON(), nullable=True),
    sa.Column('terminal_status', sa.String(length=32), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('knowledge_claim',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('slot', sa.String(length=64), nullable=False),
    sa.Column('scenario_fingerprint', sa.String(length=256), nullable=False),
    sa.Column('claim_type', sa.String(length=64), nullable=False),
    sa.Column('claim_data', sa.JSON(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('source_run_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('decayed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('prediction_result',
    sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
    sa.Column('slot', sa.String(length=64), nullable=False),
    sa.Column('workflow_id', sa.String(length=128), nullable=False),
    sa.Column('version_tag', sa.String(length=128), nullable=False),
    sa.Column('prediction_cycle_id', sa.String(length=128), nullable=False),
    sa.Column('forecast_timestamp', sa.DateTime(), nullable=False),
    sa.Column('predicted_value', sa.Float(), nullable=False),
    sa.Column('actual_value', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('is_shadow', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('evaluated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pred_result_slot_cycle', 'prediction_result', ['slot', 'prediction_cycle_id'], unique=False)
    op.create_index('ix_pred_result_slot_wf_ts', 'prediction_result', ['slot', 'workflow_id', 'forecast_timestamp'], unique=False)
    op.create_table('prelaunch_queue',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('slot', sa.String(length=64), nullable=False),
    sa.Column('candidate_id', sa.String(length=64), nullable=False),
    sa.Column('workflow_id', sa.String(length=128), nullable=False),
    sa.Column('version_tag', sa.String(length=128), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('observation_days', sa.Integer(), nullable=False),
    sa.Column('graduate_tolerance_pct', sa.Float(), nullable=False),
    sa.Column('current_rolling_mape', sa.Float(), nullable=True),
    sa.Column('production_rolling_mape', sa.Float(), nullable=True),
    sa.Column('evaluated_cycles', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('graduated_at', sa.DateTime(), nullable=True),
    sa.Column('failed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('station_data',
    sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
    sa.Column('station_id', sa.String(length=128), nullable=False),
    sa.Column('timestamp_utc', sa.DateTime(), nullable=False),
    sa.Column('feature_name', sa.String(length=128), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('slot', sa.String(length=64), nullable=False),
    sa.Column('ingested_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_station_data_slot_station_ts', 'station_data', ['slot', 'station_id', 'timestamp_utc'], unique=False)
    op.create_table('version_registry',
    sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
    sa.Column('slot', sa.String(length=64), nullable=False),
    sa.Column('workflow_id', sa.String(length=128), nullable=False),
    sa.Column('version_tag', sa.String(length=128), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('source_run_id', sa.String(length=64), nullable=True),
    sa.Column('source_candidate_id', sa.String(length=64), nullable=True),
    sa.Column('baseline_mape', sa.Float(), nullable=True),
    sa.Column('registered_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slot', 'workflow_id', 'version_tag', name='uq_version_registry_slot_wf_tag'),
    )
    op.create_table('model_versions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('version_tag', sa.String(length=128), nullable=True),
    sa.Column('training_sample_count', sa.Integer(), nullable=True),
    sa.Column('label_space_version', sa.String(length=64), nullable=True),
    sa.Column('artifact_path', sa.String(length=512), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('training_samples',
    sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
    sa.Column('time', sa.DateTime(), nullable=False),
    sa.Column('site_id', sa.String(length=128), nullable=False),
    sa.Column('device_id', sa.String(length=128), nullable=False),
    sa.Column('branch_id', sa.String(length=128), nullable=False),
    sa.Column('value', sa.Float(), nullable=True),
    sa.Column('i_cal', sa.Float(), nullable=True),
    sa.Column('label', sa.Integer(), nullable=True),
    sa.Column('ingested_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('time', 'site_id', 'device_id', 'branch_id', name='uq_training_samples_composite_key'),
    )
    op.create_index('ix_training_samples_site_time_label', 'training_samples', ['site_id', 'time', 'label'], unique=False)
    op.create_table('prediction_records',
    sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
    sa.Column('model_version_id', sa.String(length=64), nullable=True),
    sa.Column('site_id', sa.String(length=128), nullable=True),
    sa.Column('device_id', sa.String(length=128), nullable=True),
    sa.Column('branch_id', sa.String(length=128), nullable=True),
    sa.Column('input_feature_json', sa.JSON(), nullable=True),
    sa.Column('predicted_label', sa.Integer(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('executed_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint('confidence >= 0.0 AND confidence <= 1.0', name='ck_prediction_records_confidence'),
    sa.ForeignKeyConstraint(['model_version_id'], ['model_versions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('diagnosis_results',
    sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
    sa.Column('prediction_record_id', sa.BIGINT(), nullable=True),
    sa.Column('fault_type_name', sa.String(length=128), nullable=True),
    sa.Column('severity', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['prediction_record_id'], ['prediction_records.id'], ),
    sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('diagnosis_results')
    op.drop_table('prediction_records')
    op.drop_index('ix_training_samples_site_time_label', table_name='training_samples')
    op.drop_table('training_samples')
    op.drop_table('model_versions')
    op.drop_table('version_registry')
    op.drop_index('ix_station_data_slot_station_ts', table_name='station_data')
    op.drop_table('station_data')
    op.drop_table('prelaunch_queue')
    op.drop_index('ix_pred_result_slot_wf_ts', table_name='prediction_result')
    op.drop_index('ix_pred_result_slot_cycle', table_name='prediction_result')
    op.drop_table('prediction_result')
    op.drop_table('knowledge_claim')
    op.drop_table('experiment_run')
    op.drop_index('ix_candidate_pool_slot_patch_sig', table_name='candidate_pool')
    op.drop_table('candidate_pool')
    op.drop_table('accuracy_metric')
