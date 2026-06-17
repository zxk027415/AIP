/**
 * 人工标注审核 - 会话列表页
 * 
 * 显示所有审核会话(进行中/已完成),点击可进入继续审核。
 * 放在"行业数据管理"导航下。
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Table, Tag, Button, Space, Typography, Progress, Empty, Spin, message } from 'antd';
import { EditOutlined, CheckCircleOutlined, FileTextOutlined } from '@ant-design/icons';

const { Title } = Typography;

interface ReviewSessionSummary {
  review_id: string;
  status: string;
  reviewed_count: number;
  total_count: number;
  loop_id: string;
  prediction_batch_id: string;
}

const IterativeLabelingListPage: React.FC = () => {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<ReviewSessionSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const resp = await fetch(`/api/iterative-labeling/review-sessions`);
      if (!resp.ok) throw new Error('加载失败');
      const data = await resp.json();
      setSessions(data.sessions || []);
    } catch (e: any) {
      message.error(`加载审核会话列表失败: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadSessions(); }, []);

  const columns = [
    {
      title: '会话 ID',
      dataIndex: 'review_id',
      key: 'review_id',
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (v: string) => v === 'reviewed'
        ? <Tag color="success" icon={<CheckCircleOutlined />}>已完成</Tag>
        : <Tag color="processing" icon={<EditOutlined />}>审核中</Tag>,
    },
    {
      title: '进度',
      key: 'progress',
      width: 200,
      render: (_: unknown, r: ReviewSessionSummary) => (
        <Progress
          percent={r.total_count > 0 ? Math.round((r.reviewed_count / r.total_count) * 100) : 0}
          size="small"
          format={() => `${r.reviewed_count}/${r.total_count}`}
          status={r.status === 'reviewed' ? 'success' : 'active'}
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_: unknown, r: ReviewSessionSummary) => (
        <Button
          type="primary"
          size="small"
          icon={r.status === 'reviewed' ? <FileTextOutlined /> : <EditOutlined />}
          onClick={() => navigate(`/iterative-labeling/review?review_id=${encodeURIComponent(r.review_id)}`)}
        >
          {r.status === 'reviewed' ? '查看结果' : '继续审核'}
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <FileTextOutlined /> 人工标注审核
      </Title>

      <Space style={{ marginBottom: 16 }}>
        <Button onClick={loadSessions} size="small">刷新</Button>
      </Space>

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
        ) : sessions.length === 0 ? (
          <Empty description="暂无审核会话。请先在预测工作流结果中点击「人工审查打标」创建审核会话。" />
        ) : (
          <Table
            dataSource={sessions}
            columns={columns}
            rowKey="review_id"
            pagination={{ pageSize: 10 }}
            size="middle"
          />
        )}
      </Card>
    </div>
  );
};

export default IterativeLabelingListPage;
