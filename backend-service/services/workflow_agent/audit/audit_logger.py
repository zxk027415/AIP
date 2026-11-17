# @AI_GENERATED: Kiro v1.0
"""
审计日志服务 — 记录 Skill 调用、算法模板状态变更、模板操作
"""
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from database import SessionLocal
from models.workflow_agent_db import WorkflowAgentAuditLog
from models.workflow_agent_models import AuditLogEntry, AuditLogQuery, SkillStatus

logger = logging.getLogger(__name__)

# 默认日志保留天数
DEFAULT_RETENTION_DAYS = 365


class AuditLogger:
    """审计日志记录与查询服务"""

    def __init__(self, retention_days: int = DEFAULT_RETENTION_DAYS):
        self.retention_days = retention_days

    def log(
        self,
        user_id: int,
        skill_name: str,
        action: str,
        status: str,
        execution_duration_ms: int = 0,
        workflow_id: Optional[str] = None,
        template_id: Optional[str] = None,
        input_summary: Optional[str] = None,
        output_summary: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """写入一条审计日志，返回日志 ID"""
        db: Session = SessionLocal()
        try:
            record = WorkflowAgentAuditLog(
                timestamp=datetime.utcnow(),
                user_id=user_id,
                skill_name=skill_name,
                action=action,
                workflow_id=workflow_id,
                template_id=template_id,
                input_summary=_truncate(input_summary, 500),
                output_summary=_truncate(output_summary, 500),
                execution_duration_ms=execution_duration_ms,
                status=status,
                error_message=error_message,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record.id
        except Exception as e:
            db.rollback()
            logger.error(f"审计日志写入失败: {e}", exc_info=True)
            return None
        finally:
            db.close()

    def query(self, params: AuditLogQuery) -> List[AuditLogEntry]:
        """按条件查询审计日志"""
        db: Session = SessionLocal()
        try:
            q = db.query(WorkflowAgentAuditLog)
            filters = []

            if params.user_id is not None:
                filters.append(WorkflowAgentAuditLog.user_id == params.user_id)
            if params.skill_name:
                filters.append(WorkflowAgentAuditLog.skill_name == params.skill_name)
            if params.workflow_id:
                filters.append(WorkflowAgentAuditLog.workflow_id == params.workflow_id)
            if params.start_time:
                try:
                    st = datetime.fromisoformat(params.start_time)
                    filters.append(WorkflowAgentAuditLog.timestamp >= st)
                except ValueError:
                    pass
            if params.end_time:
                try:
                    et = datetime.fromisoformat(params.end_time)
                    filters.append(WorkflowAgentAuditLog.timestamp <= et)
                except ValueError:
                    pass

            if filters:
                q = q.filter(and_(*filters))

            q = q.order_by(desc(WorkflowAgentAuditLog.timestamp))

            offset = (params.page - 1) * params.page_size
            rows = q.offset(offset).limit(params.page_size).all()

            return [
                AuditLogEntry(
                    id=r.id,
                    timestamp=r.timestamp.isoformat() if r.timestamp else "",
                    user_id=r.user_id,
                    skill_name=r.skill_name,
                    action=r.action,
                    workflow_id=r.workflow_id,
                    status=r.status,
                    execution_duration_ms=r.execution_duration_ms,
                    error_message=r.error_message,
                )
                for r in rows
            ]
        except Exception as e:
            logger.error(f"审计日志查询失败: {e}", exc_info=True)
            return []
        finally:
            db.close()

    def get_skill_stats(self, skill_name: str, days: int = 7) -> Dict[str, Any]:
        """获取指定 Skill 的统计数据（最近 N 天）"""
        db: Session = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            rows = (
                db.query(WorkflowAgentAuditLog)
                .filter(
                    WorkflowAgentAuditLog.skill_name == skill_name,
                    WorkflowAgentAuditLog.timestamp >= cutoff,
                )
                .all()
            )
            total = len(rows)
            if total == 0:
                return {
                    "recent_execution_count": 0,
                    "avg_execution_time_ms": 0,
                    "error_rate": 0,
                }
            errors = sum(1 for r in rows if r.status == "failed")
            durations = [r.execution_duration_ms for r in rows if r.execution_duration_ms]
            avg_ms = sum(durations) / len(durations) if durations else 0
            return {
                "recent_execution_count": total,
                "avg_execution_time_ms": round(avg_ms, 1),
                "error_rate": round(errors / total, 4),
            }
        except Exception as e:
            logger.error(f"Skill 统计查询失败: {e}", exc_info=True)
            return {"recent_execution_count": 0, "avg_execution_time_ms": 0, "error_rate": 0}
        finally:
            db.close()

    def cleanup_old_logs(self) -> int:
        """清理过期日志，返回删除条数"""
        db: Session = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=self.retention_days)
            count = (
                db.query(WorkflowAgentAuditLog)
                .filter(WorkflowAgentAuditLog.timestamp < cutoff)
                .delete()
            )
            db.commit()
            return count
        except Exception as e:
            db.rollback()
            logger.error(f"审计日志清理失败: {e}", exc_info=True)
            return 0
        finally:
            db.close()


def _truncate(s: Optional[str], max_len: int) -> Optional[str]:
    """截断字符串"""
    if s is None:
        return None
    return s[:max_len] if len(s) > max_len else s
# @AI_GENERATED: end
