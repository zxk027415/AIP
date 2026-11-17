// @AI_GENERATED
/**
 * 数据与兼容性阶段 - 数据接入 + 字段映射 / 画像 / 不可变版本发布（design §13）。
 *
 * 数据资产为项目级（可服务三条诊断路径）。提供上传 / 平台资产 / 连接器接入（只登记逻辑引用 + 描述，
 * 不接收服务器路径或凭据），以及字段映射 → 发布不可变数据版本（相对 artifact_ref + 稳定内容摘要，
 * 映射变化生成新版本）。三路径 readiness 见任务 2.5。
 *
 * requirements.md R13.5–R13.14、R13.25–R13.26、NFR1.*、NFR4.*。
 */

import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Form,
  Input,
  Modal,
  Segmented,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { useProjectScope } from '../../../contexts/ProjectScopeContext';
import { UPLOAD_ACCEPT, pvProjectsApi, uploadRefFromFileId } from '../../../services/pvProjectsApi';
import type { DatasetAsset, DatasetSourceKind, DatasetVersion } from '../../../services/pvProjectsApi';
import PathReadinessView from '../../components/PathReadinessView';

const { Title, Text } = Typography;

const SOURCE_OPTIONS = [
  // 平台上传端点（api/upload.py）的白名单是 csv/tsv/xlsx/xls，**不含 parquet** ——
  // 文案与实际能力对齐，避免用户选 Parquet 后被 400 拒绝。
  { label: '上传 CSV / TSV / Excel', value: 'upload' as DatasetSourceKind },
  { label: '平台数据资产', value: 'platform_asset' as DatasetSourceKind },
  { label: '授权连接器', value: 'connector' as DatasetSourceKind },
];

const STATUS_LABEL: Record<string, { color: string; label: string }> = {
  registered: { color: 'green', label: '已登记' },
  pending_materialization: { color: 'orange', label: '待物化' },
};

export function ProjectDataStagePage(): JSX.Element {
  const { scope, generation } = useProjectScope();
  const projectId = scope.projectId;
  const [assets, setAssets] = useState<DatasetAsset[]>([]);
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sourceKind, setSourceKind] = useState<DatasetSourceKind>('upload');
  const [form] = Form.useForm();
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState<{ fileId: string; filename: string } | null>(null);

  const [publishAsset, setPublishAsset] = useState<DatasetAsset | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [publishForm] = Form.useForm();

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    Promise.all([pvProjectsApi.listDatasets(projectId), pvProjectsApi.listVersions(projectId)])
      .then(([assetRes, versionRes]) => {
        setAssets(assetRes.assets);
        setVersions(versionRes.versions);
      })
      .catch(() => setError('数据资产 / 版本列表读取失败'))
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load, generation]);

  /** 真实上传：调平台上传端点落盘，再用返回的 file_id 拼出 upload_ref 自动填表。 */
  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const info = await pvProjectsApi.uploadFile(file);
      const filename = info.filename || file.name;
      setUploaded({ fileId: info.file_id, filename });
      form.setFieldsValue({
        file_name: filename,
        upload_ref: uploadRefFromFileId(info.file_id, filename),
      });
      message.success('文件已上传');
    } catch (err) {
      const detail = (err as { payload?: { message?: string } })?.payload?.message;
      message.error(detail || '文件上传失败');
    } finally {
      setUploading(false);
    }
  };

  const handleRegister = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await pvProjectsApi.registerDataset(projectId, { source_kind: sourceKind, ...values });
      message.success('数据资产已登记');
      setOpen(false);
      form.resetFields();
      setUploaded(null);
      load();
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      const detail = (err as { payload?: { message?: string } })?.payload?.message;
      message.error(detail || '登记数据资产失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handlePublish = async () => {
    if (!publishAsset) return;
    try {
      const values = await publishForm.validateFields();
      setPublishing(true);
      const profile = await pvProjectsApi.saveProfile(projectId, publishAsset.dataset_id, {
        mapping: { time_col: values.time_col, device_col: values.device_col, value_col: values.value_col },
        ...(values.i_cal_col ? { ical_contract: { i_cal_col: values.i_cal_col, semantics: 'expected_current_reference' } } : {}),
      });
      const version = await pvProjectsApi.publishVersion(projectId, {
        dataset_id: publishAsset.dataset_id,
        dataset_profile_id: profile.dataset_profile_id,
      });
      message.success(version.idempotent_hit ? '已存在相同内容版本（幂等命中）' : '已发布不可变数据版本');
      setPublishAsset(null);
      publishForm.resetFields();
      load();
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      const detail = (err as { payload?: { message?: string } })?.payload?.message;
      message.error(detail || '发布数据版本失败');
    } finally {
      setPublishing(false);
    }
  };

  const assetColumns: ColumnsType<DatasetAsset> = [
    { title: '数据资产 ID', dataIndex: 'dataset_id', render: (v: string) => <Text code>{v}</Text> },
    {
      title: '来源',
      dataIndex: 'source_kind',
      render: (k: string) => SOURCE_OPTIONS.find((o) => o.value === k)?.label || k,
    },
    { title: '逻辑对象', dataIndex: 'logical_object', render: (v?: string) => v || <Text type="secondary">—</Text> },
    {
      title: '状态',
      dataIndex: 'status',
      render: (s: string) => {
        const meta = STATUS_LABEL[s] || { color: 'default', label: s };
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: '操作',
      render: (_: unknown, row) => (
        <Button size="small" type="link" onClick={() => setPublishAsset(row)}>
          映射并发布版本
        </Button>
      ),
    },
  ];

  const versionColumns: ColumnsType<DatasetVersion> = [
    { title: '数据版本 ID', dataIndex: 'dataset_version_id', render: (v: string) => <Text code>{v}</Text> },
    { title: '数据资产', dataIndex: 'dataset_id' },
    {
      title: '内容摘要',
      dataIndex: 'content_digest',
      render: (v: string) => <Text type="secondary">{v?.slice(0, 12)}…</Text>,
    },
    {
      title: '相对工件引用',
      dataIndex: 'artifact_ref',
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text>,
    },
    { title: '不可变', dataIndex: 'immutable', render: () => <Tag color="green">immutable</Tag> },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          数据与兼容性
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          接入数据
        </Button>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="数据接入 → 字段映射 → 发布不可变版本"
        description="只登记 asset_id / connector_id / 相对上传引用 + 逻辑描述，不接收服务器路径或凭据。发布的版本携带相对 artifact_ref 与稳定内容摘要，映射变化生成新版本。三路径 readiness 见任务 2.5。"
      />

      {error && (
        <Alert type="error" showIcon message={error} action={<Button size="small" onClick={load}>重试</Button>} style={{ marginBottom: 12 }} />
      )}

      {loading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div>
            <Title level={5}>数据资产</Title>
            {assets.length === 0 ? (
              <Alert type="info" showIcon message="还没有数据资产" description="点击「接入数据」上传 CSV / Parquet、选择平台资产或注册已授权连接器。" />
            ) : (
              <Table rowKey="dataset_id" columns={assetColumns} dataSource={assets} pagination={{ pageSize: 10, hideOnSinglePage: true }} size="middle" />
            )}
          </div>
          <div>
            <Title level={5}>已发布数据版本（不可变）</Title>
            {versions.length === 0 ? (
              <Alert type="info" showIcon message="还没有已发布数据版本" description="对某个数据资产完成字段映射后发布不可变版本。" />
            ) : (
              <Table
                rowKey="dataset_version_id"
                columns={versionColumns}
                dataSource={versions}
                pagination={{ pageSize: 10, hideOnSinglePage: true }}
                size="middle"
                expandable={{
                  expandedRowRender: (record) => (
                    <PathReadinessView projectId={projectId} versionId={record.dataset_version_id} />
                  ),
                  rowExpandable: () => true,
                }}
              />
            )}
          </div>
        </Space>
      )}

      {/* 接入数据 */}
      <Modal title="接入数据" open={open} onOk={handleRegister} confirmLoading={submitting} onCancel={() => { setOpen(false); setUploaded(null); }} okText="登记" cancelText="取消" destroyOnHidden>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Segmented block options={SOURCE_OPTIONS} value={sourceKind} onChange={(v) => setSourceKind(v as DatasetSourceKind)} />
          <Form form={form} layout="vertical" preserve={false}>
            {sourceKind === 'upload' && (
              <>
                <Form.Item label="数据文件" required>
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Upload
                      accept={UPLOAD_ACCEPT}
                      maxCount={1}
                      showUploadList={false}
                      beforeUpload={(file) => {
                        void handleUpload(file as File);
                        return false; // 阻止 antd 自动上传，改由 handleUpload 调平台端点
                      }}
                    >
                      <Button icon={<UploadOutlined />} loading={uploading}>
                        选择文件并上传
                      </Button>
                    </Upload>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      支持 {UPLOAD_ACCEPT}；上传后自动填充下方引用。
                      {uploaded ? ` 已上传：${uploaded.filename}` : ''}
                    </Text>
                  </Space>
                </Form.Item>
                <Form.Item name="file_name" label="文件名" rules={[{ required: true, message: '请先上传文件' }]}>
                  <Input readOnly placeholder="上传后自动填充" />
                </Form.Item>
                <Form.Item name="upload_ref" label="上传相对引用" rules={[{ required: true, message: '请先上传文件' }]}>
                  <Input readOnly placeholder="上传后自动填充（如 data/uploads/upload-….csv）" />
                </Form.Item>
              </>
            )}
            {sourceKind === 'platform_asset' && (
              <Form.Item name="asset_id" label="平台资产 ID" rules={[{ required: true, message: '请输入平台资产 ID' }]}>
                <Input placeholder="如：asset-1234" />
              </Form.Item>
            )}
            {sourceKind === 'connector' && (
              <>
                <Form.Item name="connector_id" label="连接器 ID" rules={[{ required: true, message: '请选择已授权连接器' }]}>
                  <Input placeholder="如：conn-mysql-prod（不填连接串 / 口令）" />
                </Form.Item>
                <Form.Item name="logical_object" label="逻辑对象">
                  <Input placeholder="如：pv.readings" />
                </Form.Item>
              </>
            )}
            <Form.Item name="logical_description" label="逻辑描述">
              <Input.TextArea rows={2} placeholder="数据说明（不含凭据 / 连接串）" />
            </Form.Item>
          </Form>
          <Text type="secondary" style={{ fontSize: 12 }}>只保存逻辑引用与描述；凭据 / 连接串 / 服务器绝对路径会被服务端拒绝。</Text>
        </Space>
      </Modal>

      {/* 映射并发布版本 */}
      <Modal
        title={`映射并发布版本 · ${publishAsset?.dataset_id || ''}`}
        open={!!publishAsset}
        onOk={handlePublish}
        confirmLoading={publishing}
        onCancel={() => setPublishAsset(null)}
        okText="发布不可变版本"
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={publishForm} layout="vertical" preserve={false}>
          <Form.Item name="time_col" label="时间列" rules={[{ required: true, message: '请指定时间列' }]}>
            <Input placeholder="如：ts" />
          </Form.Item>
          <Form.Item name="device_col" label="设备列" rules={[{ required: true, message: '请指定设备列' }]}>
            <Input placeholder="如：device_id" />
          </Form.Item>
          <Form.Item name="value_col" label="实测值列" rules={[{ required: true, message: '请指定实测电流列' }]}>
            <Input placeholder="如：value" />
          </Form.Item>
          <Form.Item name="i_cal_col" label="期望电流参照列 i_cal（可选）">
            <Input placeholder="i_cal 是期望电流参照，不是 ground truth" />
          </Form.Item>
        </Form>
        <Text type="secondary" style={{ fontSize: 12 }}>
          发布生成不可变版本；相同映射 + 相同资产会幂等命中，映射变化生成新版本。
        </Text>
      </Modal>
    </div>
  );
}

export default ProjectDataStagePage;
// @AI_GENERATED: end
