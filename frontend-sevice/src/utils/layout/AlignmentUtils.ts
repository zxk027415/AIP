import { Node } from 'reactflow';

/**
 * 对齐类型
 */
export enum AlignmentType {
  LEFT = 'left',
  RIGHT = 'right',
  TOP = 'top',
  BOTTOM = 'bottom',
  CENTER_HORIZONTAL = 'center-horizontal',
  CENTER_VERTICAL = 'center-vertical',
}

/**
 * 分布类型
 */
export enum DistributionType {
  HORIZONTAL = 'horizontal',
  VERTICAL = 'vertical',
}

/**
 * 节点对齐工具类
 */
export class AlignmentUtils {
  /**
   * 左对齐
   */
  static alignLeft(nodes: Node[]): Node[] {
    if (nodes.length < 2) return nodes;

    const minX = Math.min(...nodes.map(n => n.position.x));

    return nodes.map(node => ({
      ...node,
      position: {
        ...node.position,
        x: minX,
      },
    }));
  }

  /**
   * 右对齐
   */
  static alignRight(nodes: Node[]): Node[] {
    if (nodes.length < 2) return nodes;

    const maxX = Math.max(...nodes.map(n => n.position.x + (n.width || 150)));

    return nodes.map(node => ({
      ...node,
      position: {
        ...node.position,
        x: maxX - (node.width || 150),
      },
    }));
  }

  /**
   * 顶部对齐
   */
  static alignTop(nodes: Node[]): Node[] {
    if (nodes.length < 2) return nodes;

    const minY = Math.min(...nodes.map(n => n.position.y));

    return nodes.map(node => ({
      ...node,
      position: {
        ...node.position,
        y: minY,
      },
    }));
  }

  /**
   * 底部对齐
   */
  static alignBottom(nodes: Node[]): Node[] {
    if (nodes.length < 2) return nodes;

    const maxY = Math.max(...nodes.map(n => n.position.y + (n.height || 40)));

    return nodes.map(node => ({
      ...node,
      position: {
        ...node.position,
        y: maxY - (node.height || 40),
      },
    }));
  }

  /**
   * 水平居中对齐
   */
  static alignCenterHorizontal(nodes: Node[]): Node[] {
    if (nodes.length < 2) return nodes;

    const centerX = nodes.reduce((sum, n) => sum + n.position.x + (n.width || 150) / 2, 0) / nodes.length;

    return nodes.map(node => ({
      ...node,
      position: {
        ...node.position,
        x: centerX - (node.width || 150) / 2,
      },
    }));
  }

  /**
   * 垂直居中对齐
   */
  static alignCenterVertical(nodes: Node[]): Node[] {
    if (nodes.length < 2) return nodes;

    const centerY = nodes.reduce((sum, n) => sum + n.position.y + (n.height || 40) / 2, 0) / nodes.length;

    return nodes.map(node => ({
      ...node,
      position: {
        ...node.position,
        y: centerY - (node.height || 40) / 2,
      },
    }));
  }

  /**
   * 水平均匀分布
   */
  static distributeHorizontally(nodes: Node[]): Node[] {
    if (nodes.length < 3) return nodes;

    // 按X坐标排序
    const sortedNodes = [...nodes].sort((a, b) => a.position.x - b.position.x);

    const firstNode = sortedNodes[0];
    const lastNode = sortedNodes[sortedNodes.length - 1];

    const totalWidth = lastNode.position.x - firstNode.position.x;
    const spacing = totalWidth / (sortedNodes.length - 1);

    return sortedNodes.map((node, index) => ({
      ...node,
      position: {
        ...node.position,
        x: firstNode.position.x + spacing * index,
      },
    }));
  }

  /**
   * 垂直均匀分布
   */
  static distributeVertically(nodes: Node[]): Node[] {
    if (nodes.length < 3) return nodes;

    // 按Y坐标排序
    const sortedNodes = [...nodes].sort((a, b) => a.position.y - b.position.y);

    const firstNode = sortedNodes[0];
    const lastNode = sortedNodes[sortedNodes.length - 1];

    const totalHeight = lastNode.position.y - firstNode.position.y;
    const spacing = totalHeight / (sortedNodes.length - 1);

    return sortedNodes.map((node, index) => ({
      ...node,
      position: {
        ...node.position,
        y: firstNode.position.y + spacing * index,
      },
    }));
  }

  /**
   * 网格对齐（吸附）
   */
  static snapToGrid(nodes: Node[], gridSize: number = 20): Node[] {
    return nodes.map(node => ({
      ...node,
      position: {
        x: Math.round(node.position.x / gridSize) * gridSize,
        y: Math.round(node.position.y / gridSize) * gridSize,
      },
    }));
  }

  /**
   * 执行对齐
   */
  static align(nodes: Node[], type: AlignmentType): Node[] {
    switch (type) {
      case AlignmentType.LEFT:
        return this.alignLeft(nodes);
      case AlignmentType.RIGHT:
        return this.alignRight(nodes);
      case AlignmentType.TOP:
        return this.alignTop(nodes);
      case AlignmentType.BOTTOM:
        return this.alignBottom(nodes);
      case AlignmentType.CENTER_HORIZONTAL:
        return this.alignCenterHorizontal(nodes);
      case AlignmentType.CENTER_VERTICAL:
        return this.alignCenterVertical(nodes);
      default:
        return nodes;
    }
  }

  /**
   * 执行分布
   */
  static distribute(nodes: Node[], type: DistributionType): Node[] {
    switch (type) {
      case DistributionType.HORIZONTAL:
        return this.distributeHorizontally(nodes);
      case DistributionType.VERTICAL:
        return this.distributeVertically(nodes);
      default:
        return nodes;
    }
  }
}
