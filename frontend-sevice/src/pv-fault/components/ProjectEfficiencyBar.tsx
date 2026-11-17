// @AI_GENERATED
/**
 * 效率层：继续上次 + 最近访问 + 命令面板提示（design §35；任务 10.7）。
 *
 * 数据来自 journeyContextStore（lastHref / recents）；纯导航，不写业务状态。
 * 与 CommandPalette 配合：此处给可见入口，Ctrl/Cmd+K 给键盘入口。
 */

import { useNavigate } from 'react-router-dom';
import { Button, Space, Tag, Typography } from 'antd';
import { useJourneyContextStore } from '../../stores/journeyContextStore';

const { Text } = Typography;

export function ProjectEfficiencyBar(): JSX.Element | null {
  const navigate = useNavigate();
  const lastHref = useJourneyContextStore((s) => s.lastHref);
  const recents = useJourneyContextStore((s) => s.recents);

  const projectRecents = recents.filter((r) => r.kind === 'project').slice(0, 6);

  if (!lastHref && projectRecents.length === 0) return null;

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 8,
        padding: '10px 12px',
        marginBottom: 16,
        background: '#fafafa',
        border: '1px solid #f0f0f0',
        borderRadius: 8,
      }}
    >
      {lastHref && (
        <Button size="small" type="primary" ghost onClick={() => navigate(lastHref)}>
          继续上次
        </Button>
      )}
      {projectRecents.length > 0 && (
        <>
          <Text type="secondary" style={{ fontSize: 12 }}>
            最近：
          </Text>
          <Space size={6} wrap>
            {projectRecents.map((r) => (
              <Tag
                key={`${r.kind}-${r.id}`}
                style={{ cursor: 'pointer', marginInlineEnd: 0 }}
                onClick={() => navigate(r.href)}
              >
                {r.label}
              </Tag>
            ))}
          </Space>
        </>
      )}
      <Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
        按 Ctrl/Cmd + K 打开命令面板
      </Text>
    </div>
  );
}

export default ProjectEfficiencyBar;
// @AI_GENERATED: end
