import { Node, Edge } from 'reactflow';
import dagre from 'dagre';

/**
 * 布局方向
 */
export enum LayoutDirection {
  TB = 'TB', // 从上到下
  BT = 'BT', // 从下到上
  LR = 'LR', // 从左到右
  RL = 'RL', // 从右到左
}

/**
 * 自动布局配置
 */
export interface AutoLayoutConfig {
  direction: LayoutDirection;
  nodeWidth: number;
  nodeHeight: number;
  rankSep: number; // 层级间距
  nodeSep: number; // 节点间距
}

/**
 * 默认配置
 */
const DEFAULT_CONFIG: AutoLayoutConfig = {
  direction: LayoutDirection.TB,
  nodeWidth: 150,
  nodeHeight: 40,
  rankSep: 100,
  nodeSep: 50,
};

/**
 * 自动布局工具类
 */
export class AutoLayoutUtils {
  /**
   * 使用Dagre算法进行自动布局
   */
  static autoLayout(
    nodes: Node[],
    edges: Edge[],
    config: Partial<AutoLayoutConfig> = {}
  ): Node[] {
    const finalConfig = { ...DEFAULT_CONFIG, ...config };

    // 创建Dagre图
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    dagreGraph.setGraph({
      rankdir: finalConfig.direction,
      ranksep: finalConfig.rankSep,
      nodesep: finalConfig.nodeSep,
    });

    // 添加节点
    nodes.forEach(node => {
      dagreGraph.setNode(node.id, {
        width: node.width || finalConfig.nodeWidth,
        height: node.height || finalConfig.nodeHeight,
      });
    });

    // 添加边
    edges.forEach(edge => {
      dagreGraph.setEdge(edge.source, edge.target);
    });

    // 执行布局
    dagre.layout(dagreGraph);

    // 更新节点位置
    return nodes.map(node => {
      const nodeWithPosition = dagreGraph.node(node.id);
      return {
        ...node,
        position: {
          x: nodeWithPosition.x - (node.width || finalConfig.nodeWidth) / 2,
          y: nodeWithPosition.y - (node.height || finalConfig.nodeHeight) / 2,
        },
      };
    });
  }

  /**
   * 网格布局
   */
  static gridLayout(
    nodes: Node[],
    columns: number = 4,
    spacing: { x: number; y: number } = { x: 200, y: 100 }
  ): Node[] {
    return nodes.map((node, index) => {
      const row = Math.floor(index / columns);
      const col = index % columns;

      return {
        ...node,
        position: {
          x: col * spacing.x,
          y: row * spacing.y,
        },
      };
    });
  }

  /**
   * 圆形布局
   */
  static circleLayout(
    nodes: Node[],
    radius: number = 300,
    center: { x: number; y: number } = { x: 400, y: 300 }
  ): Node[] {
    const angleStep = (2 * Math.PI) / nodes.length;

    return nodes.map((node, index) => {
      const angle = index * angleStep - Math.PI / 2; // 从顶部开始

      return {
        ...node,
        position: {
          x: center.x + radius * Math.cos(angle) - (node.width || 150) / 2,
          y: center.y + radius * Math.sin(angle) - (node.height || 40) / 2,
        },
      };
    });
  }

  /**
   * 层级布局（树形）
   */
  static treeLayout(
    nodes: Node[],
    edges: Edge[],
    spacing: { x: number; y: number } = { x: 200, y: 100 }
  ): Node[] {
    // 找到根节点（没有入边的节点）
    const targetIds = new Set(edges.map(e => e.target));
    const rootNodes = nodes.filter(n => !targetIds.has(n.id));

    if (rootNodes.length === 0) {
      return nodes;
    }

    // 构建邻接表
    const adjacencyList = new Map<string, string[]>();
    edges.forEach(edge => {
      if (!adjacencyList.has(edge.source)) {
        adjacencyList.set(edge.source, []);
      }
      adjacencyList.get(edge.source)!.push(edge.target);
    });

    // 计算每个节点的层级和位置
    const nodePositions = new Map<string, { x: number; y: number; level: number }>();
    const levelWidths = new Map<number, number>();

    const traverse = (nodeId: string, level: number, parentX: number = 0) => {
      const children = adjacencyList.get(nodeId) || [];
      const levelWidth = levelWidths.get(level) || 0;

      const x = parentX + levelWidth * spacing.x;
      const y = level * spacing.y;

      nodePositions.set(nodeId, { x, y, level });
      levelWidths.set(level, levelWidth + 1);

      children.forEach(childId => {
        traverse(childId, level + 1, x);
      });
    };

    rootNodes.forEach((root, index) => {
      traverse(root.id, 0, index * spacing.x * 3);
    });

    // 更新节点位置
    return nodes.map(node => {
      const pos = nodePositions.get(node.id);
      if (!pos) return node;

      return {
        ...node,
        position: {
          x: pos.x,
          y: pos.y,
        },
      };
    });
  }
}
