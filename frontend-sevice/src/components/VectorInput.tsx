import { useState, useEffect } from 'react';
import { Input, Button, Space, Typography, message, Modal, Tooltip } from 'antd';
import { MinusOutlined, UndoOutlined, ExclamationCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface VectorInputProps {
  value?: number[];
  onChange?: (value: number[]) => void;
  length?: number;
  isMobile?: boolean;
}

interface HistoryState {
  vector: number[];
  action: string;
}

/**
 * 向量输入组件 - Excel 风格自动扩展
 * 
 * 功能：
 * - 显示实际向量 + 1个虚线框（扩展位置）
 * - 在虚线框中输入数据时自动扩展向量
 * - 顶部删除元素按钮
 * - 撤销功能
 */
const VectorInput: React.FC<VectorInputProps> = ({
  value,
  onChange,
  length = 3,
  isMobile = false,
}) => {
  const [vector, setVector] = useState<number[]>([]);
  const [history, setHistory] = useState<HistoryState[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [pendingDeleteIndex, setPendingDeleteIndex] = useState<number | null>(null);

  // 初始化向量
  useEffect(() => {
    if (value && value.length > 0) {
      setVector(value);
    } else {
      // 创建默认向量
      const defaultVector = Array(length).fill(0).map((_, i) => i + 1);
      setVector(defaultVector);
      onChange?.(defaultVector);
    }
  }, []);

  // 保存到历史记录
  const saveToHistory = (newVector: number[], action: string) => {
    setHistory(prev => [...prev, { vector: vector, action }]);
    setVector(newVector);
    onChange?.(newVector);
  };

  // 撤销
  const handleUndo = () => {
    if (history.length === 0) {
      message.info('没有可撤销的操作');
      return;
    }
    
    const lastState = history[history.length - 1];
    setVector(lastState.vector);
    onChange?.(lastState.vector);
    setHistory(prev => prev.slice(0, -1));
    message.success(`已撤销：${lastState.action}`);
  };

  // 更新元素值
  const handleElementChange = (index: number, val: string) => {
    const numValue = parseFloat(val);
    const finalValue = isNaN(numValue) ? 0 : numValue;
    
    let newVector = [...vector];
    let needsSave = false;
    
    // 如果是在扩展位置输入
    if (index >= vector.length) {
      newVector.push(finalValue);
      needsSave = true;
    } else {
      newVector[index] = finalValue;
    }
    
    if (needsSave) {
      saveToHistory(newVector, '添加新元素');
    } else {
      setVector(newVector);
      onChange?.(newVector);
    }
  };

  // 删除当前选中的元素
  const handleDeleteLastElement = () => {
    if (vector.length <= 1) {
      message.warning('至少需要保留一个元素');
      return;
    }
    
    // 如果没有选中元素，默认删除最后一个
    const indexToDelete = selectedIndex !== null ? selectedIndex : vector.length - 1;
    const elementNumber = indexToDelete + 1; // 显示给用户的元素号（从1开始）
    
    setPendingDeleteIndex(indexToDelete);
    
    Modal.confirm({
      title: '确认删除',
      icon: <ExclamationCircleOutlined />,
      content: `确定要删除第 ${elementNumber} 个元素吗？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => {
        const newVector = vector.filter((_, index) => index !== indexToDelete);
        saveToHistory(newVector, `删除第 ${elementNumber} 个元素`);
        setPendingDeleteIndex(null);
        
        // 删除后，选中前一个元素
        const newIndex = Math.max(0, indexToDelete - 1);
        setSelectedIndex(newIndex);
      },
      onCancel: () => {
        setPendingDeleteIndex(null);
      },
    });
  };

  const cellSize = isMobile ? 50 : 60;
  const inputSize = isMobile ? 'small' : 'middle';
  const currentLength = vector.length;

  // 渲染元素
  const renderElement = (index: number, isExpansion: boolean) => {
    const value = isExpansion ? '' : (vector[index] || 0);
    const isSelected = selectedIndex === index;
    const isPendingDelete = pendingDeleteIndex !== null && index === pendingDeleteIndex;
    
    // 确定边框样式
    let borderStyle = undefined;
    if (isSelected && isExpansion) {
      borderStyle = '2px dashed #1890ff'; // 蓝色虚线 - 选中扩展区域
    } else if (isSelected) {
      borderStyle = '2px solid #1890ff'; // 蓝色实线 - 选中实际元素
    } else if (isPendingDelete) {
      borderStyle = '2px solid #ff4d4f'; // 红色实线 - 待删除的元素
    } else if (isExpansion) {
      borderStyle = '2px dashed #d9d9d9'; // 灰色虚线 - 未选中扩展区域
    }
    
    return (
      <Input
        value={value}
        onChange={(e) => handleElementChange(index, e.target.value)}
        onFocus={() => setSelectedIndex(index)}
        style={{
          width: `${cellSize}px`,
          textAlign: 'center',
          fontFamily: 'monospace',
          border: borderStyle,
          backgroundColor: isExpansion ? '#fafafa' : undefined,
        }}
        size={inputSize}
      />
    );
  };

  return (
    <Space direction="vertical" size="small" style={{ width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            长度: {currentLength}
          </Text>
          {selectedIndex !== null && (
            <Text type="secondary" style={{ fontSize: '12px', color: '#1890ff' }}>
              [{selectedIndex + 1}]
            </Text>
          )}
        </div>
        <Space size="small">
          <Tooltip title="提示：在虚线框中输入数据自动扩展向量">
            <Button
              size="small"
              icon={<QuestionCircleOutlined />}
              type="text"
            />
          </Tooltip>
          <Button
            danger
            size="small"
            icon={<MinusOutlined />}
            onClick={handleDeleteLastElement}
            disabled={currentLength <= 1}
          >
            删除元素
          </Button>
          <Button
            size="small"
            icon={<UndoOutlined />}
            onClick={handleUndo}
            disabled={history.length === 0}
          >
            撤销
          </Button>
        </Space>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <Space size={4} wrap={isMobile}>
          {/* 实际向量元素 + 扩展位置 */}
          {Array(currentLength + 1).fill(0).map((_, index) => {
            const isExpansion = index === currentLength;
            
            return (
              <div key={index} style={{ display: 'inline-block' }}>
                {renderElement(index, isExpansion)}
              </div>
            );
          })}
        </Space>
      </div>
    </Space>
  );
};

export default VectorInput;
