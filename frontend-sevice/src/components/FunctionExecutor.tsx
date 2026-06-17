// @AI_GENERATED: Kiro v1.0
import { useState } from 'react';
import { Card, InputNumber, Button, Space, Typography, Alert, Divider, Input, Table, Select, Upload, Tag, Descriptions, Spin } from 'antd';
import { PlayCircleOutlined, ClearOutlined, DatabaseOutlined, UploadOutlined, InboxOutlined, CheckCircleOutlined } from '@ant-design/icons';
import type { FunctionDefinition } from '../types/function';
import api from '../services/api';
import { td } from '../utils/dataTranslation';

const { Title, Text } = Typography;
const { Option } = Select;
const { TextArea } = Input;
const { Dragger } = Upload;

interface FunctionExecutorProps {
  functionDef: FunctionDefinition;
  isMobile?: boolean;
}

interface ParameterValue {
  inputType: 'number' | 'string' | 'array' | 'matrix' | 'dataset';
  numberValue?: number;
  stringValue?: string;
  arrayValue?: number[];
  matrixValue?: number[][];
  datasetId?: string;
}

interface FileAnalysis {
  columns: Array<{
    name: string;
    dtype: string;
    non_null_count: number;
    total_count: number;
    sample_values: string[];
    is_numeric: boolean;
    is_datetime: boolean;
    timestamp_likelihood: number;
  }>;
  recommended_timestamp: string | null;
  numeric_columns: string[];
  total_rows: number;
  encoding: string;
}

interface UploadedFile {
  file_id: string;
  filename: string;
  file_size: number;
  analysis: FileAnalysis;
}
// @AI_GENERATED: end

// @AI_GENERATED: Kiro v1.0
/**
 * 函数执行器组件
 * 
 * 功能：
 * - 根据参数类型智能选择输入方式
 * - NUMBER: 数字输入框
 * - STRING: 文本输入框或下拉选择
 * - ARRAY: JSON数组输入或数据集选择
 * - MATRIX: 数据集选择（时序数据）
 * - 执行函数并显示结果
 */
const FunctionExecutor: React.FC<FunctionExecutorProps> = ({ functionDef, isMobile = false }) => {
  const [parameterValues, setParameterValues] = useState<Record<string, ParameterValue>>({});
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<UploadedFile | null>(null);
  const [uploading, setUploading] = useState(false);
  const [selectedTimestampCol, setSelectedTimestampCol] = useState<string | undefined>(undefined);
  const [selectedValueCols, setSelectedValueCols] = useState<string[]>([]);

  // 根据参数类型和名称判断最佳输入方式
  const determineInputType = (param: any): 'number' | 'string' | 'array' | 'matrix' | 'dataset' => {
    const paramType = param.type.toUpperCase();
    const paramName = param.name.toLowerCase();
    
    // 数据源相关参数使用数据集选择
    if (paramName.includes('data') || paramName.includes('train') || paramName.includes('features') || paramName.includes('target')) {
      if (paramType === 'MATRIX') return 'dataset';
      if (paramType === 'ARRAY') return 'dataset';
    }
    
    // 根据参数类型
    if (paramType === 'NUMBER') return 'number';
    if (paramType === 'STRING') return 'string';
    if (paramType === 'ARRAY') return 'array';
    if (paramType === 'MATRIX') return 'matrix';
    
    return 'string';
  };

  // 初始化参数值
  const initializeParameter = (param: any) => {
    const paramName = param.name;
    if (!parameterValues[paramName]) {
      const inputType = determineInputType(param);
      
      const defaultValue: ParameterValue = {
        inputType,
        numberValue: 1,
        stringValue: '',
        arrayValue: [],
        matrixValue: [[]],
        datasetId: undefined,
      };
      
      setParameterValues(prev => ({
        ...prev,
        [paramName]: defaultValue
      }));
    }
  };

  // 处理参数值变化
  const handleParameterChange = (paramName: string, field: keyof ParameterValue, value: any) => {
    setParameterValues(prev => ({
      ...prev,
      [paramName]: {
        ...prev[paramName],
        [field]: value,
      }
    }));
  };
// @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 执行函数
  const handleExecute = async () => {
    setExecuting(true);
    setError(null);
    setResult(null);

    try {
      // 验证所有必需参数都已填写
      const missingParams = functionDef.parameters
        .filter(p => p.required && !parameterValues[p.name])
        .map(p => p.name);

      if (missingParams.length > 0) {
        throw new Error(`${td('缺少必需参数')}: ${missingParams.join(', ')}`);
      }

      // 解析参数值
      const parsedParams: Record<string, any> = {};
      for (const [paramName, paramValue] of Object.entries(parameterValues)) {
        switch (paramValue.inputType) {
          case 'number':
            parsedParams[paramName] = paramValue.numberValue || 0;
            break;
          case 'string':
            parsedParams[paramName] = paramValue.stringValue || '';
            break;
          case 'array':
            parsedParams[paramName] = paramValue.arrayValue || [];
            break;
          case 'matrix':
            parsedParams[paramName] = paramValue.matrixValue || [[]];
            break;
          case 'dataset':
            // 数据集ID，后端需要根据ID加载数据
            parsedParams[paramName] = paramValue.datasetId || '';
            break;
        }
      }

      // 调用后端 API 执行函数
      const response = await fetch('/api/functions/execute', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          function_id: functionDef.id,
          parameters: parsedParams,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(td(data.detail || data.error || '执行失败'));
      }

      if (!data.success) {
        throw new Error(td(data.error || '执行失败'));
      }

      setResult({
        success: true,
        output: data.result,
        executionTime: `${data.execution_time}s`,
      });
    } catch (err: any) {
      setError(td(err.message || '执行失败'));
    } finally {
      setExecuting(false);
    }
  };
  // @AI_GENERATED: end

  // 清空输入
  const handleClear = () => {
    setParameterValues({});
    setResult(null);
    setError(null);
    setUploadedFile(null);
    setUploading(false);
    setSelectedTimestampCol(undefined);
    setSelectedValueCols([]);
  };

  // @AI_GENERATED: Kiro v1.0
  // 渲染输出结果
  const renderOutput = (output: any) => {
    // 尝试解析输出
    let parsedOutput = output;
    if (typeof output === 'string') {
      try {
        parsedOutput = JSON.parse(output);
      } catch {
        return (
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {output}
          </pre>
        );
      }
    }

    // 单个数值
    if (typeof parsedOutput === 'number') {
      return (
        <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#1890ff', textAlign: 'center', padding: '20px' }}>
          {parsedOutput.toFixed(4)}
        </div>
      );
    }

    // 数组 - 使用表格展示
    if (Array.isArray(parsedOutput) && parsedOutput.length > 0) {
      // 检查是否是二维数组（矩阵）
      if (Array.isArray(parsedOutput[0])) {
        const matrix = parsedOutput as number[][];
        const columns = [
          { title: td('行'), dataIndex: 'row', key: 'row', width: 60 },
          ...matrix[0].map((_, colIndex) => ({
            title: `${td('列')}${colIndex + 1}`,
            dataIndex: `col${colIndex}`,
            key: `col${colIndex}`,
          }))
        ];
        
        const dataSource = matrix.map((row, rowIndex) => {
          const rowData: any = { key: rowIndex, row: rowIndex + 1 };
          row.forEach((value, colIndex) => {
            rowData[`col${colIndex}`] = typeof value === 'number' ? value.toFixed(4) : value;
          });
          return rowData;
        });

        return (
          <Table
            dataSource={dataSource}
            columns={columns}
            pagination={false}
            size="small"
            scroll={{ x: true, y: 400 }}
          />
        );
      }

      // 一维数组
      const tableData = parsedOutput.map((value, index) => ({
        key: index,
        index: index + 1,
        value: typeof value === 'number' ? value.toFixed(4) : value,
      }));

      const columns = [
        { title: td('索引'), dataIndex: 'index', key: 'index', width: '30%' },
        { title: td('值'), dataIndex: 'value', key: 'value', width: '70%' },
      ];

      return (
        <Table
          dataSource={tableData}
          columns={columns}
          pagination={{ pageSize: 10 }}
          size="small"
          scroll={{ y: 300 }}
        />
      );
    }

    // 对象或其他类型
    return (
      <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
        {JSON.stringify(parsedOutput, null, 2)}
      </pre>
    );
  };
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 渲染参数输入
  const renderParameterInput = (param: any) => {
    // 确保参数已初始化
    if (!parameterValues[param.name]) {
      initializeParameter(param);
      return null;
    }

    const paramValue = parameterValues[param.name];
    const inputType = paramValue.inputType;

    // 获取预定义选项（如果有）
    const getStringOptions = (paramName: string, description: string) => {
      const lowerName = paramName.toLowerCase();
      const lowerDesc = description.toLowerCase();
      
      if (lowerName.includes('method') || lowerDesc.includes('方法')) {
        if (lowerDesc.includes('填充')) return ['linear', 'ffill', 'bfill', 'mean'];
        if (lowerDesc.includes('检测')) return ['zscore', 'iqr', 'isolation_forest'];
        if (lowerDesc.includes('归一化')) return ['minmax', 'zscore', 'robust'];
        if (lowerDesc.includes('聚合')) return ['mean', 'sum', 'max', 'min'];
        if (lowerDesc.includes('平均')) return ['binary', 'micro', 'macro', 'weighted'];
      }
      if (lowerName.includes('kernel')) return ['linear', 'rbf', 'poly'];
      if (lowerName.includes('frequency')) return ['1H', '15min', '30min', '1D'];
      
      return null;
    };

    const stringOptions = inputType === 'string' ? getStringOptions(param.name, param.description || '') : null;

    return (
      <Card 
        key={param.name} 
        size="small" 
        title={
          <Space>
            <Text strong>{param.name}</Text>
            {param.required && <Text type="danger">*</Text>}
            {param.description && (
              <Text type="secondary" style={{ fontSize: '12px' }}>
                - {param.description}
              </Text>
            )}
          </Space>
        }
        style={{ marginBottom: '12px' }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="small">
          {/* NUMBER 类型 */}
          {inputType === 'number' && (
            <InputNumber
              value={paramValue.numberValue}
              onChange={(value) => handleParameterChange(param.name, 'numberValue', value)}
              style={{ width: '100%' }}
              placeholder={td('请输入数值')}
              size={isMobile ? 'large' : 'middle'}
            />
          )}

          {/* STRING 类型 */}
          {inputType === 'string' && (
            <>
              {/* file_path 参数使用文件上传组件 */}
              {param.name === 'file_path' ? (
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  {!uploadedFile ? (
                    <Dragger
                      name="file"
                      multiple={false}
                      accept=".csv,.xlsx,.xls,.tsv"
                      showUploadList={false}
                      customRequest={async ({ file, onSuccess, onError }) => {
                        setUploading(true);
                        try {
                          const formData = new FormData();
                          formData.append('file', file as File);
                          const res: any = await api.post('/upload/file', formData, {
                            headers: { 'Content-Type': 'multipart/form-data' },
                          });
                          setUploadedFile(res);
                          handleParameterChange(param.name, 'stringValue', res.file_id);
                          // 自动设置推荐的时间列
                          if (res.analysis?.recommended_timestamp) {
                            setSelectedTimestampCol(res.analysis.recommended_timestamp);
                            // 自动填充 timestamp_column 参数
                            setParameterValues(prev => ({
                              ...prev,
                              timestamp_column: {
                                inputType: 'string',
                                stringValue: res.analysis.recommended_timestamp,
                              },
                            }));
                          }
                          // 自动设置数值列
                          if (res.analysis?.numeric_columns?.length > 0) {
                            setSelectedValueCols(res.analysis.numeric_columns);
                            setParameterValues(prev => ({
                              ...prev,
                              value_columns: {
                                inputType: 'array',
                                arrayValue: res.analysis.numeric_columns,
                              },
                            }));
                          }
                          onSuccess?.(res);
                        } catch (err: any) {
                          onError?.(err);
                          setError(`${td('文件上传失败')}: ${td(err?.message || '未知错误')}`);
                        } finally {
                          setUploading(false);
                        }
                      }}
                    >
                      {uploading ? (
                        <div style={{ padding: '20px' }}>
                          <Spin />
                          <p style={{ marginTop: 8 }}>{td('正在上传并分析文件...')}</p>
                        </div>
                      ) : (
                        <>
                          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                          <p className="ant-upload-text">{td('点击或拖拽文件到此区域上传')}</p>
                          <p className="ant-upload-hint">{td('支持 CSV、Excel (.xlsx/.xls)、TSV 文件，最大 100MB')}</p>
                        </>
                      )}
                    </Dragger>
                  ) : (
                    <Card size="small" style={{ background: '#f6ffed', borderColor: '#b7eb8f' }}>
                      <Space direction="vertical" style={{ width: '100%' }} size="small">
                        <Space>
                          <CheckCircleOutlined style={{ color: '#52c41a' }} />
                          <Text strong>{uploadedFile.filename}</Text>
                          <Tag color="blue">{(uploadedFile.file_size / 1024).toFixed(1)} KB</Tag>
                          <Tag>{uploadedFile.analysis?.total_rows} {td('行')}</Tag>
                          <Tag>{uploadedFile.analysis?.columns?.length} {td('列')}</Tag>
                          <Button size="small" type="link" danger onClick={() => {
                            setUploadedFile(null);
                            setSelectedTimestampCol(undefined);
                            setSelectedValueCols([]);
                            handleParameterChange(param.name, 'stringValue', '');
                          }}>{td('重新上传')}</Button>
                        </Space>

                        {/* 列信息摘要 */}
                        <Descriptions size="small" bordered column={1} style={{ marginTop: 4 }}>
                          <Descriptions.Item label={td('编码')}>{uploadedFile.analysis?.encoding}</Descriptions.Item>
                          <Descriptions.Item label={td('数值列')}>
                            {uploadedFile.analysis?.numeric_columns?.map(c => (
                              <Tag key={c} color="blue" style={{ marginBottom: 2 }}>{c}</Tag>
                            ))}
                          </Descriptions.Item>
                          <Descriptions.Item label={td('推荐时间列')}>
                            {uploadedFile.analysis?.recommended_timestamp
                              ? <Tag color="green">{uploadedFile.analysis.recommended_timestamp}</Tag>
                              : <Text type="secondary">{td('未检测到时间列')}</Text>}
                          </Descriptions.Item>
                        </Descriptions>
                      </Space>
                    </Card>
                  )}
                </Space>
              ) : param.name === 'timestamp_column' && uploadedFile ? (
                /* 时间列选择 - 上传文件后显示下拉 */
                <Select
                  value={selectedTimestampCol}
                  onChange={(value) => {
                    setSelectedTimestampCol(value);
                    handleParameterChange(param.name, 'stringValue', value);
                  }}
                  style={{ width: '100%' }}
                  placeholder={td('选择时间列（可选）')}
                  allowClear
                  size={isMobile ? 'large' : 'middle'}
                >
                  {uploadedFile.analysis?.columns?.map(col => (
                    <Option key={col.name} value={col.name}>
                      <Space>
                        {col.name}
                        {col.is_datetime && <Tag color="green" style={{ fontSize: 10 }}>{td('时间')}</Tag>}
                        {col.timestamp_likelihood > 0 && (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {td('匹配度')} {Math.round(col.timestamp_likelihood * 100)}%
                          </Text>
                        )}
                      </Space>
                    </Option>
                  ))}
                </Select>
              ) : stringOptions ? (
                <Select
                  value={paramValue.stringValue}
                  onChange={(value) => handleParameterChange(param.name, 'stringValue', value)}
                  style={{ width: '100%' }}
                  placeholder={td('请选择')}
                  size={isMobile ? 'large' : 'middle'}
                >
                  {stringOptions.map(opt => (
                    <Option key={opt} value={opt}>{opt}</Option>
                  ))}
                </Select>
              ) : (
                <Input
                  value={paramValue.stringValue}
                  onChange={(e) => handleParameterChange(param.name, 'stringValue', e.target.value)}
                  placeholder={td('请输入文本')}
                  size={isMobile ? 'large' : 'middle'}
                />
              )}
            </>
          )}

          {/* ARRAY 类型 */}
          {inputType === 'array' && (
            <>
              {param.name === 'value_columns' && uploadedFile ? (
                /* 数值列多选 - 上传文件后显示下拉 */
                <Select
                  mode="multiple"
                  value={selectedValueCols}
                  onChange={(values) => {
                    setSelectedValueCols(values);
                    handleParameterChange(param.name, 'arrayValue', values);
                  }}
                  style={{ width: '100%' }}
                  placeholder={td('选择数值列（可选，默认全部数值列）')}
                  size={isMobile ? 'large' : 'middle'}
                >
                  {uploadedFile.analysis?.columns?.filter(c => c.is_numeric).map(col => (
                    <Option key={col.name} value={col.name}>
                      <Space>
                        {col.name}
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          ({col.dtype})
                        </Text>
                      </Space>
                    </Option>
                  ))}
                </Select>
              ) : (
                <TextArea
                  value={JSON.stringify(paramValue.arrayValue || [])}
                  onChange={(e) => {
                    try {
                      const parsed = JSON.parse(e.target.value);
                      if (Array.isArray(parsed)) {
                        handleParameterChange(param.name, 'arrayValue', parsed);
                      }
                    } catch {
                      // 忽略解析错误，等待用户输入完整
                    }
                  }}
                  placeholder={td('请输入JSON数组，例如: [1, 2, 3]')}
                  rows={3}
                  size={isMobile ? 'large' : 'middle'}
                />
              )}
            </>
          )}

          {/* MATRIX 类型 */}
          {inputType === 'matrix' && (
            <TextArea
              value={JSON.stringify(paramValue.matrixValue || [[]])}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value);
                  if (Array.isArray(parsed) && Array.isArray(parsed[0])) {
                    handleParameterChange(param.name, 'matrixValue', parsed);
                  }
                } catch {
                  // 忽略解析错误
                }
              }}
              placeholder={td('请输入JSON矩阵，例如: [[1, 2], [3, 4]]')}
              rows={4}
              size={isMobile ? 'large' : 'middle'}
            />
          )}

          {/* DATASET 类型 - 数据集选择 */}
          {inputType === 'dataset' && (
            <Space direction="vertical" style={{ width: '100%' }} size="small">
              <Alert
                message={td('数据集功能')}
                description={td('数据集管理功能正在开发中，当前请使用JSON格式输入数据')}
                type="info"
                showIcon
                icon={<DatabaseOutlined />}
              />
              <Select
                value={paramValue.datasetId}
                onChange={(value) => handleParameterChange(param.name, 'datasetId', value)}
                style={{ width: '100%' }}
                placeholder={td('选择数据集（功能开发中）')}
                disabled
                size={isMobile ? 'large' : 'middle'}
              >
                <Option value="dataset1">{td('示例数据集1')}</Option>
                <Option value="dataset2">{td('示例数据集2')}</Option>
              </Select>
              <Text type="secondary" style={{ fontSize: '12px' }}>
                {td('提示：您也可以在上方切换为JSON输入模式')}
              </Text>
            </Space>
          )}
        </Space>
      </Card>
    );
  };
  // @AI_GENERATED: end

  return (
    <Space direction="vertical" size="small" style={{ width: '100%' }}>
      <Title level={5} style={{ fontSize: isMobile ? '14px' : '16px', margin: 0 }}>
        {td('输入')}
      </Title>

      {/* 参数输入区域 */}
      {functionDef.parameters.length > 0 ? (
        <div>
          {functionDef.parameters.map(renderParameterInput)}
        </div>
      ) : (
        <Alert message={td('此函数无需参数')} type="info" showIcon />
      )}

      {/* 执行按钮 */}
      <Space style={{ width: '100%', justifyContent: 'flex-end', marginTop: '4px' }}>
        <Button
          icon={<ClearOutlined />}
          onClick={handleClear}
          size="small"
        >
          {td('清空')}
        </Button>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          onClick={handleExecute}
          loading={executing}
          size="small"
        >
          {td('执行函数')}
        </Button>
      </Space>

      {/* 错误信息 */}
      {error && (
        <Alert
          message={td('执行错误')}
          description={error}
          type="error"
          showIcon
          closable
          onClose={() => setError(null)}
          style={{ marginTop: '8px' }}
        />
      )}

      {/* 执行结果 */}
      {result && (
        <>
          <Divider style={{ margin: '12px 0' }} />
          <Title level={5} style={{ fontSize: isMobile ? '14px' : '16px', margin: '0 0 8px 0' }}>
            {td('输出')}
          </Title>
          <Card 
            title={td('执行结果')} 
            size="small"
            extra={<Text type="secondary" style={{ fontSize: '12px' }}>{td('耗时')}: {result.executionTime}</Text>}
          >
            <div style={{
              backgroundColor: '#f5f5f5',
              padding: '12px',
              borderRadius: '4px',
              fontFamily: 'monospace',
              fontSize: isMobile ? '12px' : '13px',
              overflowX: 'auto',
            }}>
              {renderOutput(result.output)}
            </div>
          </Card>
        </>
      )}
    </Space>
  );
};

export default FunctionExecutor;
