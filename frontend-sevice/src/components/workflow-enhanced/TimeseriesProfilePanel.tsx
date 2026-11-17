import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Descriptions, Select, Space, Spin, Tag, Typography } from 'antd';
import { timeseriesProfileApi } from '../../services/timeseriesProfileApi';
import type { DatasetProfileSummary, ProfilePreflightReport } from '../../types/timeseriesProfile';

const { Text } = Typography;

interface TimeseriesProfilePanelProps {
  slot?: string;
  value?: string;
  onChange?: (profileRef: string | undefined) => void;
}

const TimeseriesProfilePanel: React.FC<TimeseriesProfilePanelProps> = ({ slot, value, onChange }) => {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<DatasetProfileSummary[]>([]);
  const [report, setReport] = useState<ProfilePreflightReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    timeseriesProfileApi
      .listDatasetProfiles()
      .then((resp) => {
        const filtered = slot
          ? resp.items.filter((item) => item.slot === slot)
          : resp.items;
        setItems(filtered);
      })
      .catch((err) => setError(String(err?.message || err)))
      .finally(() => setLoading(false));
  }, [slot]);

  const selectedId = value?.split('@')[0];

  const runPreflight = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await timeseriesProfileApi.preflightDatasetProfile(selectedId, 'local_validation');
      setReport(resp.report);
    } catch (err: any) {
      setReport(null);
      setError(String(err?.response?.data?.detail || err?.message || err));
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div>
          <Text type="secondary">Dataset Profile</Text>
          <Select
            style={{ width: '100%', marginTop: 8 }}
            placeholder={items.length ? '选择 dataset profile' : '暂无 profile'}
            value={selectedId}
            options={items.map((item) => ({
              value: item.profile_id,
              label: `${item.profile_id}@${item.profile_version}`,
            }))}
            onChange={(profileId) => {
              const hit = items.find((item) => item.profile_id === profileId);
              onChange?.(hit ? `${hit.profile_id}@${hit.profile_version}` : undefined);
              setReport(null);
            }}
            allowClear
          />
        </div>
        <Button type="primary" disabled={!selectedId} onClick={() => void runPreflight()}>
          运行 Preflight
        </Button>
        {error && <Alert type="error" showIcon message={error} />}
        {report && (
          <>
            <Alert
              type={report.ready ? 'success' : 'error'}
              showIcon
              message={report.ready ? 'Preflight 通过' : 'Preflight 阻断'}
            />
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="行数">{report.row_count ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="实体数">{report.entity_count ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="时间范围">
                {report.time_range_start && report.time_range_end
                  ? `${report.time_range_start} ~ ${report.time_range_end}`
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="source_digest">
                <Text code copyable>{report.source_digest ?? '—'}</Text>
              </Descriptions.Item>
            </Descriptions>
            {report.issues?.length > 0 && (
              <Space direction="vertical" style={{ width: '100%' }}>
                {report.issues.map((issue) => (
                  <Alert
                    key={`${issue.code}-${issue.field}-${issue.message}`}
                    type={issue.severity === 'warning' ? 'warning' : 'error'}
                    showIcon
                    message={
                      <Space>
                        <Tag>{issue.code}</Tag>
                        <span>{issue.message}</span>
                      </Space>
                    }
                    description={issue.hint}
                  />
                ))}
              </Space>
            )}
          </>
        )}
      </Space>
    </Spin>
  );
};

export default TimeseriesProfilePanel;
