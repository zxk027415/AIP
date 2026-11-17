// @AI_GENERATED
/**
 * 检测与回放阶段（wrap-first，design §11.4 / §17）。
 *
 * pv_tsc：内嵌 PvTscAccuracyOpsPanel（运行状态 / 观测，只读）。
 * pv_day / pv_point：生产观测 / Sandbox 回放的完整页面见任务 5.x/6.x；此处先给 scope 深链接到
 * 兼容部署页的观测面，并标注运行语义（day quickval、point 直连 predictor 事实保留）。
 */

import { useNavigate } from 'react-router-dom';
import { Alert, Button, Space } from 'antd';
import StageSlotGate from '../../components/StageSlotGate';
import PvTscAccuracyOpsPanel from '../../../components/slot/PvTscAccuracyOpsPanel';
import PointRunSessionPanel from '../../components/PointRunSessionPanel';
import DayGoldenPathPanel from '../../components/DayGoldenPathPanel';
import TscCanonicalPanel from '../../components/TscCanonicalPanel';
import ProjectPathModelAccuracySummary from '../../components/ProjectPathModelAccuracySummary';
import { useProjectScope } from '../../../contexts/ProjectScopeContext';
import { buildJourneyHref } from '../../../utils/journeyParams';

export function ProjectOperationsStagePage(): JSX.Element {
  const navigate = useNavigate();
  const { scope } = useProjectScope();

  return (
    <StageSlotGate prompt="选择一条诊断路径以查看检测与回放。">
      {(slot) => (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <ProjectPathModelAccuracySummary slot={slot} />
          {slot === 'pv_tsc' && (
            <>
              <Alert
                type="info"
                showIcon
                message="TSC 生产观测为只读"
                description="展示 canonical 打标入口、strict-10 证据、只读生产观测与候选评估；不提供手工推进一天 / 补检，也不写水位 / 游标 / 审核 / 精度。"
              />
              <TscCanonicalPanel slot={slot} />
              <PvTscAccuracyOpsPanel />
            </>
          )}
          {slot === 'pv_day' && <DayGoldenPathPanel slot={slot} />}
          {slot === 'pv_point' && <PointRunSessionPanel slot={slot} />}
          <Button
            type="link"
            style={{ paddingLeft: 0 }}
            onClick={() =>
              navigate(
                buildJourneyHref('/algorithm-deployment', {
                  projectId: scope.projectId,
                  slot,
                  datasetVersionId: scope.datasetVersionId,
                }),
              )
            }
          >
            打开生产观测（兼容页）
          </Button>
        </Space>
      )}
    </StageSlotGate>
  );
}

export default ProjectOperationsStagePage;
// @AI_GENERATED: end
