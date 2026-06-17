// @AI_GENERATED
import React from 'react';
import { Tooltip, Tag, Typography, Space } from 'antd';
import type { DataContract } from '../../types/pipeline';
import { PORT_TYPE_COLORS } from '../../types/pipeline';

const { Text } = Typography;

interface DataContractTooltipProps {
  contract?: DataContract;
  children: React.ReactNode;
}

const DataContractTooltip: React.FC<DataContractTooltipProps> = ({ contract, children }) => {
  if (!contract) return <>{children}</>;

  const content = (
    <div style={{ maxWidth: 280 }}>
      <Space direction="vertical" size={2}>
        <Space>
          <Text strong style={{ color: '#fff' }}>数据类型:</Text>
          <Tag color={PORT_TYPE_COLORS[contract.dataType] || '#999'}>{contract.dataType}</Tag>
        </Space>
        {contract.requiredColumns.length > 0 && (
          <div>
            <Text style={{ color: '#ccc' }}>必需列: </Text>
            {contract.requiredColumns.map((c) => (
              <Tag key={c} style={{ marginBottom: 2 }}>{c}</Tag>
            ))}
          </div>
        )}
        {contract.constraints.length > 0 && (
          <div>
            <Text style={{ color: '#ccc' }}>约束: </Text>
            {contract.constraints.map((c) => (
              <Tag key={c} color="orange" style={{ marginBottom: 2 }}>{c}</Tag>
            ))}
          </div>
        )}
        {contract.description && (
          <Text style={{ color: '#aaa', fontSize: 12 }}>{contract.description}</Text>
        )}
      </Space>
    </div>
  );

  return (
    <Tooltip title={content} placement="top" overlayStyle={{ maxWidth: 320 }}>
      {children}
    </Tooltip>
  );
};

export default DataContractTooltip;
// @AI_GENERATED: end
