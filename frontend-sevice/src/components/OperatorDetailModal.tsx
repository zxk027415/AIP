// @AI_GENERATED
/**
 * OperatorDetailModal
 * 算子详情弹窗：展示基本信息、参数说明、使用示例、关键源码
 *
 * 使用方式：
 *   <OperatorDetailModal
 *     operatorId="load_csv"
 *     operatorName="CSV/Excel文件加载"
 *     open={true}
 *     onClose={() => {}}
 *   />
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Modal, Tabs, Typography, Table, Tag, Space, Spin, Alert,
  Tooltip, Button, message,
} from 'antd';
import {
  CodeOutlined,
  InfoCircleOutlined,
  UnorderedListOutlined,
  ExperimentOutlined,
  CopyOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import type { FunctionDefinition } from '../types/function';
import api from '../services/api';

const { Text, Paragraph } = Typography;

// ────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────

interface OperatorSourceInfo {
  operator_id: string;
  source_code: string;
  key_snippet: string;
  file_path: string;
  available: boolean;
}

interface Props {
  /** 算子 ID，对应 operator_backends/{id}.py */
  operatorId: string;
  /** 用于标题展示的可读名称 */
  operatorName?: string;
  open: boolean;
  onClose: () => void;
}

// ────────────────────────────────────────────────────────────
// 极简 Python 语法高亮（无外部依赖）
// ────────────────────────────────────────────────────────────

const KEYWORDS = new Set([
  'def', 'class', 'return', 'import', 'from', 'if', 'elif', 'else',
  'for', 'while', 'in', 'not', 'and', 'or', 'is', 'None', 'True', 'False',
  'try', 'except', 'finally', 'raise', 'with', 'as', 'pass', 'break',
  'continue', 'lambda', 'yield', 'async', 'await',
]);

function tokenizeLine(line: string): React.ReactNode[] {
  // 注释整行
  const commentIdx = line.indexOf('#');
  if (commentIdx === 0) {
    return [<span key="cmt" style={{ color: '#6a9955' }}>{line}</span>];
  }

  const tokens: React.ReactNode[] = [];
  // 分割：字符串、注释、标识符、数字、符号
  const re = /("""[\s\S]*?"""|'''[\s\S]*?'''|"[^"]*"|'[^']*'|#.*$|\b\w+\b|[^\w\s])/g;
  let match: RegExpExecArray | null;
  let last = 0;
  let i = 0;

  while ((match = re.exec(line)) !== null) {
    if (match.index > last) {
      tokens.push(<span key={`gap-${i}`}>{line.slice(last, match.index)}</span>);
    }
    const tok = match[0];
    let color: string | undefined;

    if (tok.startsWith('#')) {
      color = '#6a9955'; // comment
    } else if (tok.startsWith('"') || tok.startsWith("'")) {
      color = '#ce9178'; // string
    } else if (KEYWORDS.has(tok)) {
      color = '#569cd6'; // keyword
    } else if (/^\d+(\.\d+)?$/.test(tok)) {
      color = '#b5cea8'; // number
    } else if (/^[A-Z_][A-Z0-9_]{2,}$/.test(tok)) {
      color = '#4ec9b0'; // constant / type
    } else if (/^[a-z_]\w*$/.test(tok) && re.source && line[match.index + tok.length] === '(') {
      color = '#dcdcaa'; // function call
    }

    tokens.push(
      color
        ? <span key={`tok-${i}`} style={{ color }}>{tok}</span>
        : <span key={`tok-${i}`}>{tok}</span>
    );
    last = match.index + tok.length;
    i++;
  }

  if (last < line.length) {
    tokens.push(<span key="tail">{line.slice(last)}</span>);
  }
  return tokens;
}

interface CodeBlockProps {
  code: string;
  maxHeight?: number;
}

const CodeBlock: React.FC<CodeBlockProps> = ({ code, maxHeight = 420 }) => {
  const lines = code.split('\n');
  return (
    <div
      style={{
        background: '#1e1e1e',
        borderRadius: 6,
        padding: '12px 0',
        maxHeight,
        overflowY: 'auto',
        overflowX: 'auto',
        fontFamily: '"JetBrains Mono", "Fira Code", "Consolas", monospace',
        fontSize: 12.5,
        lineHeight: '20px',
      }}
    >
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <tbody>
          {lines.map((line, idx) => (
            <tr key={idx} style={{ verticalAlign: 'top' }}>
              <td
                style={{
                  userSelect: 'none',
                  color: '#6e7681',
                  textAlign: 'right',
                  paddingRight: 16,
                  paddingLeft: 12,
                  minWidth: 36,
                  fontSize: 11,
                  lineHeight: '20px',
                }}
              >
                {idx + 1}
              </td>
              <td style={{ paddingRight: 20, whiteSpace: 'pre', color: '#d4d4d4' }}>
                {tokenizeLine(line)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// ────────────────────────────────────────────────────────────
// 参数表格列定义
// ────────────────────────────────────────────────────────────

const PARAM_COLUMNS = [
  {
    title: '参数名',
    dataIndex: 'name',
    key: 'name',
    width: 140,
    render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
  },
  {
    title: '类型',
    dataIndex: 'type',
    key: 'type',
    width: 90,
    render: (v: string) => <Tag color="blue" style={{ fontSize: 11 }}>{v}</Tag>,
  },
  {
    title: '必填',
    dataIndex: 'required',
    key: 'required',
    width: 60,
    render: (v: boolean) =>
      v ? <Tag color="red">必填</Tag> : <Tag color="default">可选</Tag>,
  },
  {
    title: '默认值',
    dataIndex: 'defaultValue',
    key: 'defaultValue',
    width: 100,
    render: (v: unknown) =>
      v !== undefined && v !== null && v !== ''
        ? <Text code style={{ fontSize: 11 }}>{String(v)}</Text>
        : <Text type="secondary" style={{ fontSize: 11 }}>—</Text>,
  },
  {
    title: '描述',
    dataIndex: 'description',
    key: 'description',
    render: (v: string) => <Text style={{ fontSize: 12 }}>{v || '—'}</Text>,
  },
];

// ────────────────────────────────────────────────────────────
// Main component
// ────────────────────────────────────────────────────────────

const OperatorDetailModal: React.FC<Props> = ({
  operatorId,
  operatorName,
  open,
  onClose,
}) => {
  const [funcDef, setFuncDef] = useState<FunctionDefinition | null>(null);
  const [sourceInfo, setSourceInfo] = useState<OperatorSourceInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('info');
  const [showFull, setShowFull] = useState(false);
  const fetchedRef = useRef<string | null>(null);

  const fetchData = useCallback(async (id: string) => {
    if (fetchedRef.current === id) return;
    fetchedRef.current = id;
    setLoading(true);
    setError(null);
    try {
      const def = await (api as any).get(`/functions/${id}`) as FunctionDefinition;
      setFuncDef(def);
    } catch {
      // functions.json 里没有的算子不报错，降级展示
      setFuncDef(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSource = useCallback(async (id: string) => {
    setSourceLoading(true);
    try {
      const src = await (api as any).get(`/functions/${id}/source`) as OperatorSourceInfo;
      setSourceInfo(src);
    } catch (e: any) {
      setError(e?.message || '获取源码失败');
    } finally {
      setSourceLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) {
      // 关闭时重置，下次打开会重新加载
      fetchedRef.current = null;
      setFuncDef(null);
      setSourceInfo(null);
      setError(null);
      setActiveTab('info');
      setShowFull(false);
      return;
    }
    fetchData(operatorId);
    fetchSource(operatorId);
  }, [open, operatorId, fetchData, fetchSource]);

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code).then(
      () => message.success('已复制到剪贴板'),
      () => message.error('复制失败'),
    );
  };

  const title = operatorName || operatorId;

  // ── Tab items ──────────────────────────────────────────────

  const tabItems = [
    {
      key: 'info',
      label: (
        <Space size={4}>
          <InfoCircleOutlined />
          基本信息
        </Space>
      ),
      children: (
        <div style={{ padding: '4px 0' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 32 }}>
              <Spin tip="加载中..." />
            </div>
          ) : (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              {/* ID + 分类 */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: 12,
                }}
              >
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>算子 ID</Text>
                  <div>
                    <Text code style={{ fontSize: 13 }}>{operatorId}</Text>
                  </div>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>分类</Text>
                  <div>
                    <Tag color="purple" style={{ marginTop: 2 }}>
                      {funcDef?.category || '—'}
                    </Tag>
                  </div>
                </div>
              </div>

              {/* 描述 */}
              <div>
                <Text type="secondary" style={{ fontSize: 11 }}>描述</Text>
                <Paragraph style={{ marginTop: 4, marginBottom: 0 }}>
                  {funcDef?.description || <Text type="secondary">暂无描述</Text>}
                </Paragraph>
              </div>

              {/* 返回类型 */}
              <div>
                <Text type="secondary" style={{ fontSize: 11 }}>返回类型</Text>
                <div style={{ marginTop: 4 }}>
                  <Tag color="cyan">{funcDef?.returnType || funcDef?.return_type || '—'}</Tag>
                </div>
              </div>

              {/* 后端状态 */}
              <div>
                <Text type="secondary" style={{ fontSize: 11 }}>后端实现</Text>
                <div style={{ marginTop: 4 }}>
                  {sourceLoading ? (
                    <Spin size="small" />
                  ) : sourceInfo?.available ? (
                    <Space>
                      <Tag color="success">✓ 已实现</Tag>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {sourceInfo.file_path}
                      </Text>
                    </Space>
                  ) : (
                    <Tag color="default">仅定义</Tag>
                  )}
                </div>
              </div>
            </Space>
          )}
        </div>
      ),
    },
    {
      key: 'params',
      label: (
        <Space size={4}>
          <UnorderedListOutlined />
          参数说明
        </Space>
      ),
      children: (
        <div>
          {loading ? (
            <Spin />
          ) : funcDef?.parameters && funcDef.parameters.length > 0 ? (
            <Table
              size="small"
              dataSource={funcDef.parameters.map((p, i) => ({
                ...p,
                key: `${p.name}-${i}`,
                defaultValue: (p as any).default_value ?? (p as any).defaultValue,
              }))}
              columns={PARAM_COLUMNS}
              pagination={false}
              scroll={{ x: 600 }}
            />
          ) : (
            <Text type="secondary">该算子无参数定义</Text>
          )}
        </div>
      ),
    },
    {
      key: 'examples',
      label: (
        <Space size={4}>
          <ExperimentOutlined />
          使用示例
        </Space>
      ),
      children: (
        <div>
          {loading ? (
            <Spin />
          ) : funcDef?.examples && funcDef.examples.length > 0 ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              {funcDef.examples.map((ex, i) => (
                <div key={i} style={{ position: 'relative' }}>
                  <CodeBlock code={ex} maxHeight={200} />
                  <Tooltip title="复制">
                    <Button
                      size="small"
                      icon={<CopyOutlined />}
                      style={{
                        position: 'absolute',
                        top: 6,
                        right: 8,
                        opacity: 0.7,
                      }}
                      onClick={() => copyCode(ex)}
                    />
                  </Tooltip>
                </div>
              ))}
            </Space>
          ) : (
            <Text type="secondary">暂无使用示例</Text>
          )}
        </div>
      ),
    },
    {
      key: 'code',
      label: (
        <Space size={4}>
          <CodeOutlined />
          关键代码
        </Space>
      ),
      children: (
        <div>
          {sourceLoading ? (
            <div style={{ textAlign: 'center', padding: 32 }}>
              <Spin tip="加载源码..." />
            </div>
          ) : !sourceInfo?.available ? (
            <Alert
              type="info"
              showIcon
              message="该算子尚未有后端实现"
              description={`对应文件 ${sourceInfo?.file_path || `services/operator_backends/${operatorId}.py`} 不存在，当前仅有接口定义。`}
            />
          ) : (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              {/* 工具栏 */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <Space>
                  <FileTextOutlined style={{ color: '#aaa' }} />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {sourceInfo.file_path}
                  </Text>
                  <Tag color="default" style={{ fontSize: 10 }}>
                    {showFull ? '完整文件' : 'execute() 片段'}
                  </Tag>
                </Space>
                <Space>
                  <Button
                    size="small"
                    onClick={() => setShowFull(v => !v)}
                    style={{ fontSize: 11 }}
                  >
                    {showFull ? '只看 execute()' : '查看完整文件'}
                  </Button>
                  <Tooltip title="复制代码">
                    <Button
                      size="small"
                      icon={<CopyOutlined />}
                      onClick={() =>
                        copyCode(showFull ? sourceInfo.source_code : sourceInfo.key_snippet)
                      }
                    />
                  </Tooltip>
                </Space>
              </div>

              {/* 代码块 */}
              <CodeBlock
                code={showFull ? sourceInfo.source_code : sourceInfo.key_snippet}
                maxHeight={460}
              />
            </Space>
          )}
        </div>
      ),
    },
  ];

  return (
    <Modal
      title={
        <Space>
          <CodeOutlined style={{ color: '#722ed1' }} />
          <span style={{ fontWeight: 600 }}>{title}</span>
          <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
            算子详情
          </Text>
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={780}
      destroyOnClose
      styles={{ body: { padding: '0 24px 16px' } }}
    >
      {error && (
        <Alert
          type="warning"
          message={error}
          closable
          onClose={() => setError(null)}
          style={{ marginBottom: 12 }}
        />
      )}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        size="small"
        style={{ marginTop: 4 }}
      />
    </Modal>
  );
};

export default OperatorDetailModal;
// @AI_GENERATED: end
