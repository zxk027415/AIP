/**
 * Node Library Data
 * 节点库共享数据 - 用于左侧面板和画布菜单
 */

import React from 'react';
import {
  FunctionOutlined,
  BarChartOutlined,
  BranchesOutlined,
  RobotOutlined,
  FolderOutlined,
  FileOutlined,
} from '@ant-design/icons';
import type { EnhancedNodeData } from '../types/workflow-enhanced';

// 节点库树节点接口
export interface NodeLibraryItem {
  id: string;
  name: string;
  type: 'category' | 'function' | 'visualization' | 'control' | 'llm';
  icon?: React.ReactNode;
  children?: NodeLibraryItem[];
  nodeData?: EnhancedNodeData; // 叶子节点的数据
}

// 构建节点库数据（不包含从 API 加载的函数）
export const buildStaticNodeLibrary = (): NodeLibraryItem[] => {
  return [
    {
      id: 'function',
      name: '函数节点',
      type: 'category',
      icon: <FunctionOutlined />,
      children: [
        {
          id: 'function-linear-algebra',
          name: '线性代数',
          type: 'category',
          icon: <FolderOutlined />,
          children: [
            {
              id: 'function-linear-algebra-add',
              name: '矩阵加法',
              type: 'function',
              icon: <FileOutlined />,
              nodeData: {
                label: '矩阵加法',
                type: 'function',
                description: '两个矩阵相加',
                inputs: [
                  { id: 'input-0', name: '矩阵A', type: 'input', dataType: 'matrix', required: true },
                  { id: 'input-1', name: '矩阵B', type: 'input', dataType: 'matrix', required: true },
                ],
                outputs: [
                  { id: 'output-0', name: '结果', type: 'output', dataType: 'matrix' },
                ],
                config: { operation: 'add', subject: 'linear-algebra' },
              },
            },
            {
              id: 'function-linear-algebra-multiply',
              name: '矩阵乘法',
              type: 'function',
              icon: <FileOutlined />,
              nodeData: {
                label: '矩阵乘法',
                type: 'function',
                description: '两个矩阵相乘',
                inputs: [
                  { id: 'input-0', name: '矩阵A', type: 'input', dataType: 'matrix', required: true },
                  { id: 'input-1', name: '矩阵B', type: 'input', dataType: 'matrix', required: true },
                ],
                outputs: [
                  { id: 'output-0', name: '结果', type: 'output', dataType: 'matrix' },
                ],
                config: { operation: 'multiply', subject: 'linear-algebra' },
              },
            },
            {
              id: 'function-linear-algebra-transpose',
              name: '矩阵转置',
              type: 'function',
              icon: <FileOutlined />,
              nodeData: {
                label: '矩阵转置',
                type: 'function',
                description: '矩阵转置',
                inputs: [
                  { id: 'input-0', name: '矩阵', type: 'input', dataType: 'matrix', required: true },
                ],
                outputs: [
                  { id: 'output-0', name: '结果', type: 'output', dataType: 'matrix' },
                ],
                config: { operation: 'transpose', subject: 'linear-algebra' },
              },
            },
            {
              id: 'function-linear-algebra-inverse',
              name: '矩阵求逆',
              type: 'function',
              icon: <FileOutlined />,
              nodeData: {
                label: '矩阵求逆',
                type: 'function',
                description: '计算矩阵的逆',
                inputs: [
                  { id: 'input-0', name: '矩阵', type: 'input', dataType: 'matrix', required: true },
                ],
                outputs: [
                  { id: 'output-0', name: '逆矩阵', type: 'output', dataType: 'matrix' },
                ],
                config: { operation: 'inverse', subject: 'linear-algebra' },
              },
            },
            {
              id: 'function-linear-algebra-determinant',
              name: '行列式',
              type: 'function',
              icon: <FileOutlined />,
              nodeData: {
                label: '行列式',
                type: 'function',
                description: '计算矩阵的行列式',
                inputs: [
                  { id: 'input-0', name: '矩阵', type: 'input', dataType: 'matrix', required: true },
                ],
                outputs: [
                  { id: 'output-0', name: '行列式值', type: 'output', dataType: 'number' },
                ],
                config: { operation: 'determinant', subject: 'linear-algebra' },
              },
            },
          ],
        },
        {
          id: 'function-calculus',
          name: '微积分',
          type: 'category',
          icon: <FolderOutlined />,
          children: [
            {
              id: 'function-calculus-integrate',
              name: '数值积分',
              type: 'function',
              icon: <FileOutlined />,
              nodeData: {
                label: '数值积分',
                type: 'function',
                description: '计算定积分',
                inputs: [
                  { id: 'input-0', name: '函数', type: 'input', dataType: 'any', required: true },
                  { id: 'input-1', name: '下限', type: 'input', dataType: 'number', required: true },
                  { id: 'input-2', name: '上限', type: 'input', dataType: 'number', required: true },
                ],
                outputs: [
                  { id: 'output-0', name: '积分值', type: 'output', dataType: 'number' },
                ],
                config: { operation: 'integrate', subject: 'calculus' },
              },
            },
            {
              id: 'function-calculus-differentiate',
              name: '数值微分',
              type: 'function',
              icon: <FileOutlined />,
              nodeData: {
                label: '数值微分',
                type: 'function',
                description: '计算导数',
                inputs: [
                  { id: 'input-0', name: '函数', type: 'input', dataType: 'any', required: true },
                  { id: 'input-1', name: '点', type: 'input', dataType: 'number', required: true },
                ],
                outputs: [
                  { id: 'output-0', name: '导数值', type: 'output', dataType: 'number' },
                ],
                config: { operation: 'differentiate', subject: 'calculus' },
              },
            },
          ],
        },
        {
          id: 'function-statistics',
          name: '统计分析',
          type: 'category',
          icon: <FolderOutlined />,
          children: [
            {
              id: 'function-statistics-mean',
              name: '均值',
              type: 'function',
              icon: <FileOutlined />,
              nodeData: {
                label: '均值',
                type: 'function',
                description: '计算数据的平均值',
                inputs: [
                  { id: 'input-0', name: '数据', type: 'input', dataType: 'array', required: true },
                ],
                outputs: [
                  { id: 'output-0', name: '均值', type: 'output', dataType: 'number' },
                ],
                config: { operation: 'mean', subject: 'statistics' },
              },
            },
            {
              id: 'function-statistics-std',
              name: '标准差',
              type: 'function',
              icon: <FileOutlined />,
              nodeData: {
                label: '标准差',
                type: 'function',
                description: '计算数据的标准差',
                inputs: [
                  { id: 'input-0', name: '数据', type: 'input', dataType: 'array', required: true },
                ],
                outputs: [
                  { id: 'output-0', name: '标准差', type: 'output', dataType: 'number' },
                ],
                config: { operation: 'std', subject: 'statistics' },
              },
            },
            {
              id: 'function-statistics-variance',
              name: '方差',
              type: 'function',
              icon: <FileOutlined />,
              nodeData: {
                label: '方差',
                type: 'function',
                description: '计算数据的方差',
                inputs: [
                  { id: 'input-0', name: '数据', type: 'input', dataType: 'array', required: true },
                ],
                outputs: [
                  { id: 'output-0', name: '方差', type: 'output', dataType: 'number' },
                ],
                config: { operation: 'variance', subject: 'statistics' },
              },
            },
          ],
        },
      ],
    },
    {
      id: 'visualization',
      name: '数据可视化',
      type: 'category',
      icon: <BarChartOutlined />,
      children: [
        {
          id: 'visualization-line',
          name: '折线图',
          type: 'visualization',
          icon: <FileOutlined />,
          nodeData: {
            label: '折线图',
            type: 'visualization',
            description: '绘制折线图',
            inputs: [
              { id: 'input-0', name: 'X数据', type: 'input', dataType: 'array', required: true },
              { id: 'input-1', name: 'Y数据', type: 'input', dataType: 'array', required: true },
            ],
            outputs: [],
            config: { chartType: 'line' },
          },
        },
        {
          id: 'visualization-bar',
          name: '柱状图',
          type: 'visualization',
          icon: <FileOutlined />,
          nodeData: {
            label: '柱状图',
            type: 'visualization',
            description: '绘制柱状图',
            inputs: [
              { id: 'input-0', name: 'X数据', type: 'input', dataType: 'array', required: true },
              { id: 'input-1', name: 'Y数据', type: 'input', dataType: 'array', required: true },
            ],
            outputs: [],
            config: { chartType: 'bar' },
          },
        },
        {
          id: 'visualization-scatter',
          name: '散点图',
          type: 'visualization',
          icon: <FileOutlined />,
          nodeData: {
            label: '散点图',
            type: 'visualization',
            description: '绘制散点图',
            inputs: [
              { id: 'input-0', name: 'X数据', type: 'input', dataType: 'array', required: true },
              { id: 'input-1', name: 'Y数据', type: 'input', dataType: 'array', required: true },
            ],
            outputs: [],
            config: { chartType: 'scatter' },
          },
        },
      ],
    },
    {
      id: 'control',
      name: '控制流节点',
      type: 'category',
      icon: <BranchesOutlined />,
      children: [
        {
          id: 'control-if',
          name: '条件判断',
          type: 'control',
          icon: <FileOutlined />,
          nodeData: {
            label: '条件判断',
            type: 'control',
            description: '根据条件选择分支',
            inputs: [
              { id: 'input-0', name: '条件', type: 'input', dataType: 'boolean', required: true },
            ],
            outputs: [
              { id: 'output-0', name: '真分支', type: 'output', dataType: 'any' },
              { id: 'output-1', name: '假分支', type: 'output', dataType: 'any' },
            ],
            config: { conditionType: 'boolean' },
          },
        },
      ],
    },
    {
      id: 'llm',
      name: 'LLM节点',
      type: 'category',
      icon: <RobotOutlined />,
      children: [
        {
          id: 'llm-generate',
          name: '文本生成',
          type: 'llm',
          icon: <FileOutlined />,
          nodeData: {
            label: '文本生成',
            type: 'llm',
            description: '使用LLM生成文本',
            inputs: [
              { id: 'input-0', name: '提示词', type: 'input', dataType: 'string', required: true },
            ],
            outputs: [
              { id: 'output-0', name: '生成文本', type: 'output', dataType: 'string' },
            ],
            config: { model: 'gpt-3.5-turbo', temperature: 0.7 },
          },
        },
      ],
    },
  ];
};

// 获取分类图标
export const getCategoryIcon = (type: string): React.ReactNode => {
  switch (type) {
    case 'function':
      return <FunctionOutlined />;
    case 'visualization':
      return <BarChartOutlined />;
    case 'control':
      return <BranchesOutlined />;
    case 'llm':
      return <RobotOutlined />;
    default:
      return <FolderOutlined />;
  }
};

// 获取叶子节点图标
export const getLeafIcon = (): React.ReactNode => {
  return <FileOutlined />;
};
