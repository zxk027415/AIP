/**
 * Node Library Panel
 * 节点库面板 - 树形结构
 */

import React, { useState } from 'react';
import { Card, Tree, Input, Empty } from 'antd';
import type { TreeDataNode } from 'antd';
import { SearchOutlined, FunctionOutlined, CalculatorOutlined, BarChartOutlined, BranchesOutlined, RobotOutlined, FolderOutlined, FileOutlined } from '@ant-design/icons';
import type { EnhancedNodeData } from '../../types/workflow-enhanced';
import './NodeLibraryPanel.css';

interface NodeTemplate {
  label: string;
  description: string;
  data: EnhancedNodeData;
}

interface NodeLibraryPanelProps {
  onNodeDragStart?: (event: React.DragEvent, nodeData: EnhancedNodeData) => void;
}

const NodeLibraryPanel: React.FC<NodeLibraryPanelProps> = ({ onNodeDragStart }) => {
  const [searchText, setSearchText] = useState('');
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>(['function', 'function-linear-algebra']);

  // 构建树形数据结构
  const buildTreeData = (): TreeDataNode[] => {
    return [
      {
        title: <span className="tree-category-title"><FunctionOutlined /> 函数节点</span>,
        key: 'function',
        selectable: false,
        children: [
          {
            title: <span className="tree-subject-title"><FolderOutlined /> 线性代数</span>,
            key: 'function-linear-algebra',
            selectable: false,
            children: [
              {
                title: '矩阵加法',
                key: 'function-linear-algebra-add',
                icon: <FileOutlined />,
                isLeaf: true,
                data: {
                  label: '矩阵加法',
                  type: 'function' as const,
                  inputs: [
                    { id: 'input-0', name: '矩阵A', type: 'input' as const, dataType: 'matrix', required: true },
                    { id: 'input-1', name: '矩阵B', type: 'input' as const, dataType: 'matrix', required: true },
                  ],
                  outputs: [
                    { id: 'output-0', name: '结果', type: 'output' as const, dataType: 'matrix', required: true },
                  ],
                  config: { operation: 'add', subject: 'linear-algebra' },
                  description: '两个矩阵相加',
                },
              },
              {
                title: '矩阵乘法',
                key: 'function-linear-algebra-multiply',
                icon: <FileOutlined />,
                isLeaf: true,
                data: {
                  label: '矩阵乘法',
                  type: 'function' as const,
                  inputs: [
                    { id: 'input-0', name: '矩阵A', type: 'input' as const, dataType: 'matrix', required: true },
                    { id: 'input-1', name: '矩阵B', type: 'input' as const, dataType: 'matrix', required: true },
                  ],
                  outputs: [
                    { id: 'output-0', name: '结果', type: 'output' as const, dataType: 'matrix', required: true },
                  ],
                  config: { operation: 'multiply', subject: 'linear-algebra' },
                  description: '两个矩阵相乘',
                },
              },
              {
                title: '矩阵转置',
                key: 'function-linear-algebra-transpose',
                icon: <FileOutlined />,
                isLeaf: true,
                data: {
                  label: '矩阵转置',
                  type: 'function' as const,
                  inputs: [
                    { id: 'input-0', name: '矩阵', type: 'input' as const, dataType: 'matrix', required: true },
                  ],
                  outputs: [
                    { id: 'output-0', name: '结果', type: 'output' as const, dataType: 'matrix', required: true },
                  ],
                  config: { operation: 'transpose', subject: 'linear-algebra' },
                  description: '矩阵转置',
                },
              },
              {
                title: '矩阵求逆',
                key: 'function-linear-algebra-inverse',
                icon: <FileOutlined />,
                isLeaf: true,
                data: {
                  label: '矩阵求逆',
                  type: 'function' as const,
                  inputs: [
                    { id: 'input-0', name: '矩阵', type: 'input' as const, dataType: 'matrix', required: true },
                  ],
                  outputs: [
                    { id: 'output-0', name: '逆矩阵', type: 'output' as const, dataType: 'matrix', required: true },
                  ],
                  config: { operation: 'inverse', subject: 'linear-algebra' },
                  description: '计算矩阵的逆',
                },
              },
              {
                title: '行列式',
                key: 'function-linear-algebra-determinant',
                icon: <FileOutlined />,
                isLeaf: true,
                data: {
                  label: '行列式',
                  type: 'function' as const,
                  inputs: [
                    { id: 'input-0', name: '矩阵', type: 'input' as const, dataType: 'matrix', required: true },
                  ],
                  outputs: [
                    { id: 'output-0', name: '行列式值', type: 'output' as const, dataType: 'number', required: true },
                  ],
                  config: { operation: 'determinant', subject: 'linear-algebra' },
                  description: '计算矩阵的行列式',
                },
              },
            ],
          },
          {
            title: <span className="tree-subject-title"><FolderOutlined /> 微积分</span>,
            key: 'function-calculus',
            selectable: false,
            children: [
              {
                title: '数值积分',
                key: 'function-calculus-integrate',
                icon: <FileOutlined />,
                isLeaf: true,
                data: {
                  label: '数值积分',
                  type: 'function' as const,
                  inputs: [
                    { id: 'input-0', name: '函数', type: 'input' as const, dataType: 'any', required: true },
                    { id: 'input-1', name: '下限', type: 'input' as const, dataType: 'number', required: true },
                    { id: 'input-2', name: '上限', type: 'input' as const, dataType: 'number', required: true },
                  ],
                  outputs: [
                    { id: 'output-0', name: '积分值', type: 'output' as const, dataType: 'number', required: true },
                  ],
                  config: { operation: 'integrate', subject: 'calculus' },
                  description: '计算定积分',
                },
              },
              {
                title: '数值微分',
                key: 'function-calculus-differentiate',
                icon: <FileOutlined />,
                isLeaf: true,
                data: {
                  label: '数值微分',
                  type: 'function' as const,
                  inputs: [
                    { id: 'input-0', name: '函数', type: 'input' as const, dataType: 'any', required: true },
                    { id: 'input-1', name: '点', type: 'input' as const, dataType: 'number', required: true },
                  ],
                  outputs: [
                    { id: 'output-0', name: '导数值', type: 'output' as const, dataType: 'number', required: true },
                  ],
                  config: { operation: 'differentiate', subject: 'calculus' },
                  description: '计算导数',
                },
              },
            ],
          },
          {
            title: <span className="tree-subject-title"><FolderOutlined /> 统计分析</span>,
            key: 'function-statistics',
            selectable: false,
            children: [
              {
                title: '均值',
                key: 'function-statistics-mean',
                icon: <FileOutlined />,
                isLeaf: true,
                data: {
                  label: '均值',
                  type: 'function' as const,
                  inputs: [
                    { id: 'input-0', name: '数据', type: 'input' as const, dataType: 'array', required: true },
                  ],
                  outputs: [
                    { id: 'output-0', name: '均值', type: 'output' as const, dataType: 'number', required: true },
                  ],
                  config: { operation: 'mean', subject: 'statistics' },
                  description: '计算数据的平均值',
                },
              },
              {
                title: '标准差',
                key: 'function-statistics-std',
                icon: <FileOutlined />,
                isLeaf: true,
                data: {
                  label: '标准差',
                  type: 'function' as const,
                  inputs: [
                    { id: 'input-0', name: '数据', type: 'input' as const, dataType: 'array', required: true },
                  ],
                  outputs: [
                    { id: 'output-0', name: '标准差', type: 'output' as const, dataType: 'number', required: true },
                  ],
                  config: { operation: 'std', subject: 'statistics' },
                  description: '计算数据的标准差',
                },
              },
              {
                title: '方差',
                key: 'function-statistics-variance',
                icon: <FileOutlined />,
                isLeaf: true,
                data: {
                  label: '方差',
                  type: 'function' as const,
                  inputs: [
                    { id: 'input-0', name: '数据', type: 'input' as const, dataType: 'array', required: true },
                  ],
                  outputs: [
                    { id: 'output-0', name: '方差', type: 'output' as const, dataType: 'number', required: true },
                  ],
                  config: { operation: 'variance', subject: 'statistics' },
                  description: '计算数据的方差',
                },
              },
            ],
          },
        ],
      },
      {
        title: <span className="tree-category-title"><BarChartOutlined /> 数据可视化</span>,
        key: 'visualization',
        selectable: false,
        children: [
          {
            title: '折线图',
            key: 'visualization-line',
            icon: <FileOutlined />,
            isLeaf: true,
            data: {
              label: '折线图',
              type: 'visualization' as const,
              inputs: [
                { id: 'input-0', name: '数据', type: 'input' as const, dataType: 'array', required: true },
              ],
              outputs: [
                { id: 'output-0', name: '图表', type: 'output' as const, dataType: 'any', required: true },
              ],
              config: { chartType: 'line' },
              description: '绘制折线图',
            },
          },
          {
            title: '柱状图',
            key: 'visualization-bar',
            icon: <FileOutlined />,
            isLeaf: true,
            data: {
              label: '柱状图',
              type: 'visualization' as const,
              inputs: [
                { id: 'input-0', name: '数据', type: 'input' as const, dataType: 'array', required: true },
              ],
              outputs: [
                { id: 'output-0', name: '图表', type: 'output' as const, dataType: 'any', required: true },
              ],
              config: { chartType: 'bar' },
              description: '绘制柱状图',
            },
          },
          {
            title: '散点图',
            key: 'visualization-scatter',
            icon: <FileOutlined />,
            isLeaf: true,
            data: {
              label: '散点图',
              type: 'visualization' as const,
              inputs: [
                { id: 'input-0', name: 'X数据', type: 'input' as const, dataType: 'array', required: true },
                { id: 'input-1', name: 'Y数据', type: 'input' as const, dataType: 'array', required: true },
              ],
              outputs: [
                { id: 'output-0', name: '图表', type: 'output' as const, dataType: 'any', required: true },
              ],
              config: { chartType: 'scatter' },
              description: '绘制散点图',
            },
          },
        ],
      },
      {
        title: <span className="tree-category-title"><BranchesOutlined /> 控制流</span>,
        key: 'control',
        selectable: false,
        children: [
          {
            title: '条件判断',
            key: 'control-if',
            icon: <FileOutlined />,
            isLeaf: true,
            data: {
              label: '条件判断',
              type: 'control' as const,
              inputs: [
                { id: 'input-0', name: '条件', type: 'input' as const, dataType: 'boolean', required: true },
                { id: 'input-1', name: '真值', type: 'input' as const, dataType: 'any', required: false },
                { id: 'input-2', name: '假值', type: 'input' as const, dataType: 'any', required: false },
              ],
              outputs: [
                { id: 'output-0', name: '结果', type: 'output' as const, dataType: 'any', required: true },
              ],
              config: {},
              description: '根据条件选择分支',
            },
          },
        ],
      },
      {
        title: <span className="tree-category-title"><RobotOutlined /> LLM 节点</span>,
        key: 'llm',
        selectable: false,
        children: [
          {
            title: 'LLM 对话',
            key: 'llm-chat',
            icon: <FileOutlined />,
            isLeaf: true,
            data: {
              label: 'LLM 对话',
              type: 'llm' as const,
              inputs: [
                { id: 'input-0', name: '提示词', type: 'input' as const, dataType: 'string', required: true },
              ],
              outputs: [
                { id: 'output-0', name: '响应', type: 'output' as const, dataType: 'string', required: true },
              ],
              config: {},
              description: '调用大语言模型',
            },
          },
        ],
      },
    ];
  };

  // 获取所有节点数据（用于搜索）
  const getAllNodes = (nodes: TreeDataNode[]): Array<TreeDataNode & { data?: EnhancedNodeData }> => {
    const result: Array<TreeDataNode & { data?: EnhancedNodeData }> = [];
    const traverse = (nodeList: TreeDataNode[]) => {
      nodeList.forEach((node) => {
        if (node.isLeaf && 'data' in node) {
          result.push(node as TreeDataNode & { data: EnhancedNodeData });
        }
        if (node.children) {
          traverse(node.children);
        }
      });
    };
    traverse(nodes);
    return result;
  };

  // 过滤树节点
  const filterTreeData = (nodes: TreeDataNode[], searchValue: string): TreeDataNode[] => {
    if (!searchValue) return nodes;

    const filtered: TreeDataNode[] = [];
    
    nodes.forEach((node) => {
      const newNode = { ...node };
      
      if (node.children) {
        const filteredChildren = filterTreeData(node.children, searchValue);
        if (filteredChildren.length > 0) {
          newNode.children = filteredChildren;
          filtered.push(newNode);
        }
      } else if (node.isLeaf) {
        const title = typeof node.title === 'string' ? node.title : '';
        const nodeData = 'data' in node ? (node as any).data : null;
        const description = nodeData?.description || '';
        
        if (
          title.toLowerCase().includes(searchValue.toLowerCase()) ||
          description.toLowerCase().includes(searchValue.toLowerCase())
        ) {
          filtered.push(newNode);
        }
      }
    });
    
    return filtered;
  };

  // 处理拖拽开始
  const handleDragStart = (info: any) => {
    const node = info.node;
    if (node.isLeaf && node.data) {
      // 创建一个不可见的拖拽元素
      const dragElement = document.createElement('div');
      dragElement.style.position = 'absolute';
      dragElement.style.top = '-9999px';
      document.body.appendChild(dragElement);
      
      // 设置拖拽数据
      info.event.dataTransfer.setData('application/reactflow', JSON.stringify(node.data));
      info.event.dataTransfer.effectAllowed = 'copy';
      
      // 清理
      setTimeout(() => {
        document.body.removeChild(dragElement);
      }, 0);
    }
  };

  const treeData = buildTreeData();
  const filteredTreeData = filterTreeData(treeData, searchText);
  
  // 搜索时自动展开所有节点
  const allKeys = searchText ? getAllKeys(filteredTreeData) : expandedKeys;
  
  function getAllKeys(nodes: TreeDataNode[]): React.Key[] {
    const keys: React.Key[] = [];
    const traverse = (nodeList: TreeDataNode[]) => {
      nodeList.forEach((node) => {
        if (!node.isLeaf) {
          keys.push(node.key);
        }
        if (node.children) {
          traverse(node.children);
        }
      });
    };
    traverse(nodes);
    return keys;
  }

  return (
    <Card 
      title="节点库" 
      className="node-library-panel"
      bodyStyle={{ padding: 0 }}
    >
      <div className="node-library-search">
        <Input
          placeholder="搜索节点..."
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          allowClear
        />
      </div>

      <div className="node-library-tree-container">
        {filteredTreeData.length === 0 ? (
          <Empty 
            image={Empty.PRESENTED_IMAGE_SIMPLE} 
            description="未找到匹配的节点" 
            style={{ padding: '40px 0' }}
          />
        ) : (
          <Tree
            treeData={filteredTreeData}
            expandedKeys={searchText ? allKeys : expandedKeys}
            onExpand={(keys) => setExpandedKeys(keys)}
            draggable={{
              icon: false,
              nodeDraggable: (node) => node.isLeaf === true,
            }}
            onDragStart={handleDragStart}
            showIcon
            className="node-library-tree"
          />
        )}
      </div>
    </Card>
  );
};

export default NodeLibraryPanel;
