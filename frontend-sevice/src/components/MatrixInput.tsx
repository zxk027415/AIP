import { useState, useEffect } from 'react';
import { Input, Button, Space, Typography, message, Modal, Tooltip } from 'antd';
import { MinusOutlined, UndoOutlined, ExclamationCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface MatrixInputProps {
  value?: number[][];
  onChange?: (value: number[][]) => void;
  rows?: number;
  cols?: number;
  isMobile?: boolean;
}

interface HistoryState {
  matrix: number[][];
  action: string;
}

/**
 * 矩阵输入组件 - Excel 风格自动扩展
 * 
 * 功能：
 * - 显示实际矩阵 + 1行1列的虚线框（扩展区域）
 * - 在虚线框中输入数据时自动扩展矩阵
 * - 顶部删除行/列按钮
 * - 撤销功能
 */
const MatrixInput: React.FC<MatrixInputProps> = ({
  value,
  onChange,
  rows = 2,
  cols = 2,
  isMobile = false,
}) => {
  const [matrix, setMatrix] = useState<number[][]>([]);
  const [history, setHistory] = useState<HistoryState[]>([]);
  const [selectedCell, setSelectedCell] = useState<{ row: number; col: number } | null>(null);
  const [pendingDeleteRow, setPendingDeleteRow] = useState<number | null>(null);
  const [pendingDeleteCol, setPendingDeleteCol] = useState<number | null>(null);

  // 初始化矩阵
  useEffect(() => {
    if (value && value.length > 0) {
      setMatrix(value);
    } else {
      // 创建默认矩阵
      const defaultMatrix = Array(rows).fill(0).map((_, i) =>
        Array(cols).fill(0).map((_, j) => i === j ? 1 : 0)
      );
      setMatrix(defaultMatrix);
      onChange?.(defaultMatrix);
    }
  }, []);

  // 保存到历史记录
  const saveToHistory = (newMatrix: number[][], action: string) => {
    setHistory(prev => [...prev, { matrix: matrix, action }]);
    setMatrix(newMatrix);
    onChange?.(newMatrix);
  };

  // 撤销
  const handleUndo = () => {
    if (history.length === 0) {
      message.info('没有可撤销的操作');
      return;
    }
    
    const lastState = history[history.length - 1];
    setMatrix(lastState.matrix);
    onChange?.(lastState.matrix);
    setHistory(prev => prev.slice(0, -1));
    message.success(`已撤销：${lastState.action}`);
  };

  // 更新单元格值
  const handleCellChange = (rowIndex: number, colIndex: number, val: string) => {
    const numValue = parseFloat(val);
    const finalValue = isNaN(numValue) ? 0 : numValue;
    
    // 检查是否需要扩展矩阵
    const currentRows = matrix.length;
    const currentCols = matrix[0]?.length || 0;
    
    let newMatrix = [...matrix];
    let needsSave = false;
    let action = '';
    
    // 如果是在扩展行中输入
    if (rowIndex >= currentRows) {
      const newRow = Array(currentCols).fill(0);
      newMatrix.push(newRow);
      needsSave = true;
      action = '添加新行';
    }
    
    // 如果是在扩展列中输入
    if (colIndex >= currentCols) {
      newMatrix = newMatrix.map(row => [...row, 0]);
      needsSave = true;
      action = action ? '添加新行和新列' : '添加新列';
    }
    
    // 更新值
    newMatrix = newMatrix.map((row, i) =>
      row.map((cell, j) => {
        if (i === rowIndex && j === colIndex) {
          return finalValue;
        }
        return cell;
      })
    );
    
    if (needsSave) {
      saveToHistory(newMatrix, action);
    } else {
      setMatrix(newMatrix);
      onChange?.(newMatrix);
    }
  };

  // 删除当前选中的行
  const handleDeleteLastRow = () => {
    if (matrix.length <= 1) {
      message.warning('至少需要保留一行');
      return;
    }
    
    // 如果没有选中单元格，默认删除最后一行
    const rowToDelete = selectedCell ? selectedCell.row : matrix.length - 1;
    const rowNumber = rowToDelete + 1; // 显示给用户的行号（从1开始）
    
    setPendingDeleteRow(rowToDelete);
    
    Modal.confirm({
      title: '确认删除',
      icon: <ExclamationCircleOutlined />,
      content: `确定要删除第 ${rowNumber} 行吗？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => {
        const newMatrix = matrix.filter((_, index) => index !== rowToDelete);
        saveToHistory(newMatrix, `删除第 ${rowNumber} 行`);
        setPendingDeleteRow(null);
        
        // 删除后，选中前一行的相同列
        const newRow = Math.max(0, rowToDelete - 1);
        const col = selectedCell ? selectedCell.col : 0;
        setSelectedCell({ row: newRow, col });
      },
      onCancel: () => {
        setPendingDeleteRow(null);
      },
    });
  };

  // 删除当前选中的列
  const handleDeleteLastCol = () => {
    if (matrix[0]?.length <= 1) {
      message.warning('至少需要保留一列');
      return;
    }
    
    // 如果没有选中单元格，默认删除最后一列
    const colToDelete = selectedCell ? selectedCell.col : (matrix[0]?.length || 1) - 1;
    const colNumber = colToDelete + 1; // 显示给用户的列号（从1开始）
    
    setPendingDeleteCol(colToDelete);
    
    Modal.confirm({
      title: '确认删除',
      icon: <ExclamationCircleOutlined />,
      content: `确定要删除第 ${colNumber} 列吗？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => {
        const newMatrix = matrix.map(row => row.filter((_, index) => index !== colToDelete));
        saveToHistory(newMatrix, `删除第 ${colNumber} 列`);
        setPendingDeleteCol(null);
        
        // 删除后，选中相同行的前一列
        const row = selectedCell ? selectedCell.row : 0;
        const newCol = Math.max(0, colToDelete - 1);
        setSelectedCell({ row, col: newCol });
      },
      onCancel: () => {
        setPendingDeleteCol(null);
      },
    });
  };

  const cellSize = isMobile ? 50 : 60;
  const inputSize = isMobile ? 'small' : 'middle';
  
  const currentRows = matrix.length;
  const currentCols = matrix[0]?.length || 0;

  // 渲染单元格
  const renderCell = (rowIndex: number, colIndex: number, isExpansion: boolean) => {
    const value = isExpansion ? '' : (matrix[rowIndex]?.[colIndex] || 0);
    const isSelected = selectedCell?.row === rowIndex && selectedCell?.col === colIndex;
    const isPendingDeleteRow = pendingDeleteRow !== null && rowIndex === pendingDeleteRow;
    const isPendingDeleteCol = pendingDeleteCol !== null && colIndex === pendingDeleteCol;
    
    // 确定边框样式
    let borderStyle = undefined;
    if (isSelected && isExpansion) {
      borderStyle = '2px dashed #1890ff'; // 蓝色虚线 - 选中扩展区域
    } else if (isSelected) {
      borderStyle = '2px solid #1890ff'; // 蓝色实线 - 选中实际单元格
    } else if (isPendingDeleteRow || isPendingDeleteCol) {
      borderStyle = '2px solid #ff4d4f'; // 红色实线 - 待删除的行/列
    } else if (isExpansion) {
      borderStyle = '2px dashed #d9d9d9'; // 灰色虚线 - 未选中扩展区域
    }
    
    return (
      <Input
        value={value}
        onChange={(e) => handleCellChange(rowIndex, colIndex, e.target.value)}
        onFocus={() => setSelectedCell({ row: rowIndex, col: colIndex })}
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
            矩阵维度（m × n）：{currentRows} × {currentCols}
          </Text>
          {selectedCell && (
            <Text type="secondary" style={{ fontSize: '12px', color: '#1890ff' }}>
              当前选择：[{selectedCell.row + 1}, {selectedCell.col + 1}]
            </Text>
          )}
        </div>
        <Space size="small">
          <Tooltip title="提示：在虚线框中输入数据自动扩展矩阵">
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
            onClick={handleDeleteLastRow}
            disabled={currentRows <= 1}
          >
            删除行
          </Button>
          <Button
            danger
            size="small"
            icon={<MinusOutlined />}
            onClick={handleDeleteLastCol}
            disabled={currentCols <= 1}
          >
            删除列
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
        <table style={{ borderCollapse: 'separate', borderSpacing: '4px' }}>
          <tbody>
            {/* 实际矩阵行 + 扩展行 */}
            {Array(currentRows + 1).fill(0).map((_, rowIndex) => {
              const isExpansionRow = rowIndex === currentRows;
              
              return (
                <tr key={rowIndex}>
                  {/* 实际矩阵列 + 扩展列 */}
                  {Array(currentCols + 1).fill(0).map((_, colIndex) => {
                    const isExpansionCol = colIndex === currentCols;
                    const isExpansionCell = isExpansionRow || isExpansionCol;
                    
                    return (
                      <td key={colIndex}>
                        {renderCell(rowIndex, colIndex, isExpansionCell)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Space>
  );
};

export default MatrixInput;
