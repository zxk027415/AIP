/**
 * useNodeLibraryData Hook
 * 共享的节点库数据 Hook - 用于左侧面板和画布菜单
 */

import { useState, useEffect, useMemo } from 'react';
import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  FunctionOutlined,
  BarChartOutlined,
  BranchesOutlined,
  RobotOutlined,
  FolderOutlined,
  FileOutlined,
} from '@ant-design/icons';
import { functionLibraryApi } from '../services/workflowEnhancedApi';
import type { FunctionDefinition, Category } from '../types/function';
import type { EnhancedNodeData } from '../types/workflow-enhanced';
import type { NodeLibraryItem } from '../utils/nodeLibraryData';
import { td } from '../utils/dataTranslation';

const CHINESE_CHAR_RE = /[\u4e00-\u9fff]/;
const humanizeIdentifier = (value: string): string =>
  value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b[a-z]/g, (ch) => ch.toUpperCase());

export const useNodeLibraryData = () => {
  const { i18n } = useTranslation();
  void i18n.language;
  const [loading, setLoading] = useState(true);
  const [functions, setFunctions] = useState<FunctionDefinition[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);

  // 加载AI算法库数据
  useEffect(() => {
    loadFunctionLibrary();
  }, []);

  const loadFunctionLibrary = async () => {
    try {
      setLoading(true);
      const [functionsData, categoriesData] = await Promise.all([
        functionLibraryApi.getAllFunctions(),
        functionLibraryApi.getCategories(),
      ]);
      setFunctions(functionsData);
      setCategories(categoriesData);
    } catch (error) {
      console.error('Failed to load function library:', error);
    } finally {
      setLoading(false);
    }
  };

  // 将函数转换为节点数据
  const displayText = React.useCallback(
    (text: string | null | undefined, fallbackId?: string) => {
      const original = String(text ?? '');
      const translated = td(original);
      if ((i18n.language || '').toLowerCase().startsWith('zh')) return original;
      if (!translated || CHINESE_CHAR_RE.test(translated)) {
        return humanizeIdentifier(fallbackId || original);
      }
      return translated;
    },
    [i18n.language],
  );

  const functionToNodeData = (func: FunctionDefinition): EnhancedNodeData => {
    return {
      label: displayText(func.name, func.id),
      type: 'function',
      description: displayText(func.description, func.id),
      inputs: func.parameters.map((param, index) => ({
        id: `input-${index}`,
        name: displayText(param.name, `input-${index + 1}`),
        type: 'input' as const,
        dataType: param.type.toLowerCase() as any,
        required: param.required,
        description: displayText(param.description, param.name),
      })),
      outputs: [
        {
          id: 'output-0',
          name: displayText('结果', 'result'),
          type: 'output' as const,
          dataType: (func.return_type || 'any').toLowerCase() as any,
        },
      ],
      config: {
        functionId: func.id,
        category: func.category,
      },
    };
  };

  // 构建函数节点树
  const buildFunctionTree = (): NodeLibraryItem[] => {
    const categoryMap = new Map<string, NodeLibraryItem>();

    // 创建分类节点
    categories.forEach((category) => {
      categoryMap.set(category.id, {
        id: `function-${category.id}`,
        name: category.name,
        type: 'category',
        icon: <FolderOutlined />,
        children: [],
      });
    });

    // 将函数添加到对应分类
    functions.forEach((func) => {
      const categoryNode = categoryMap.get(func.category);
      if (categoryNode && categoryNode.children) {
        const nodeData = functionToNodeData(func);
        categoryNode.children.push({
          id: `function-${func.category}-${func.id}`,
          name: func.name,
          type: 'function',
          icon: <FileOutlined />,
          nodeData: nodeData,
        });
      }
    });

    return Array.from(categoryMap.values()).filter(
      (node) => node.children && node.children.length > 0
    );
  };

  // 构建完整树形数据
  const nodeLibraryData: NodeLibraryItem[] = useMemo(() => {
    const functionChildren = buildFunctionTree();

    return [
      {
        id: 'function',
        name: displayText('函数节点', 'function'),
        type: 'category',
        icon: <FunctionOutlined />,
        children: functionChildren,
      },
      {
        id: 'visualization',
        name: displayText('可视化节点', 'visualization'),
        type: 'category',
        icon: <BarChartOutlined />,
        children: [
          {
            id: 'visualization-line',
            name: displayText('折线图', 'line_chart'),
            type: 'visualization',
            icon: <FileOutlined />,
            nodeData: {
              label: displayText('折线图', 'line_chart'),
              type: 'visualization',
              description: displayText('绘制折线图', 'draw_line_chart'),
              inputs: [
                { id: 'input-0', name: displayText('X数据', 'x_data'), type: 'input', dataType: 'array', required: true },
                { id: 'input-1', name: displayText('Y数据', 'y_data'), type: 'input', dataType: 'array', required: true },
              ],
              outputs: [],
              config: { chartType: 'line' },
            },
          },
          {
            id: 'visualization-bar',
            name: displayText('柱状图', 'bar_chart'),
            type: 'visualization',
            icon: <FileOutlined />,
            nodeData: {
              label: displayText('柱状图', 'bar_chart'),
              type: 'visualization',
              description: displayText('绘制柱状图', 'draw_bar_chart'),
              inputs: [
                { id: 'input-0', name: displayText('X数据', 'x_data'), type: 'input', dataType: 'array', required: true },
                { id: 'input-1', name: displayText('Y数据', 'y_data'), type: 'input', dataType: 'array', required: true },
              ],
              outputs: [],
              config: { chartType: 'bar' },
            },
          },
          {
            id: 'visualization-scatter',
            name: displayText('散点图', 'scatter_chart'),
            type: 'visualization',
            icon: <FileOutlined />,
            nodeData: {
              label: displayText('散点图', 'scatter_chart'),
              type: 'visualization',
              description: displayText('绘制散点图', 'draw_scatter_plot'),
              inputs: [
                { id: 'input-0', name: displayText('X数据', 'x_data'), type: 'input', dataType: 'array', required: true },
                { id: 'input-1', name: displayText('Y数据', 'y_data'), type: 'input', dataType: 'array', required: true },
              ],
              outputs: [],
              config: { chartType: 'scatter' },
            },
          },
        ],
      },
      {
        id: 'control',
        name: displayText('控制流节点', 'control_flow'),
        type: 'category',
        icon: <BranchesOutlined />,
        children: [
          {
            id: 'control-if',
            name: displayText('条件判断', 'condition'),
            type: 'control',
            icon: <FileOutlined />,
            nodeData: {
              label: displayText('条件判断', 'condition'),
              type: 'control',
              description: displayText('根据条件选择分支', 'branch_by_condition'),
              inputs: [
                { id: 'input-0', name: displayText('条件', 'condition'), type: 'input', dataType: 'boolean', required: true },
              ],
              outputs: [
                { id: 'output-0', name: displayText('真分支', 'true_branch'), type: 'output', dataType: 'any' },
                { id: 'output-1', name: displayText('假分支', 'false_branch'), type: 'output', dataType: 'any' },
              ],
              config: { conditionType: 'boolean' },
            },
          },
        ],
      },
      {
        id: 'llm',
        name: displayText('LLM节点', 'llm_nodes'),
        type: 'category',
        icon: <RobotOutlined />,
        children: [
          {
            id: 'llm-generate',
            name: displayText('文本生成', 'text_generation'),
            type: 'llm',
            icon: <FileOutlined />,
            nodeData: {
              label: displayText('文本生成', 'text_generation'),
              type: 'llm',
              description: displayText('使用LLM生成文本', 'llm_text_generation'),
              inputs: [
                { id: 'input-0', name: displayText('提示词', 'prompt'), type: 'input', dataType: 'string', required: true },
              ],
              outputs: [
                { id: 'output-0', name: displayText('生成文本', 'generated_text'), type: 'output', dataType: 'string' },
              ],
              config: { model: 'gpt-3.5-turbo', temperature: 0.7 },
            },
          },
        ],
      },
    ];
  }, [functions, categories, i18n.language, displayText]);

  return {
    loading,
    nodeLibraryData,
  };
};
