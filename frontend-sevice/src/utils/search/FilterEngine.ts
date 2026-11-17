import { Node } from 'reactflow';

/**
 * 过滤条件
 */
export interface FilterCondition {
  type?: string[];
  status?: string[];
  tags?: string[];
}

/**
 * 过滤引擎
 */
export class FilterEngine {
  /**
   * 按类型过滤
   */
  static filterByType(nodes: Node[], types: string[]): Node[] {
    if (types.length === 0) {
      return nodes;
    }

    return nodes.filter(node => types.includes(node.type || 'default'));
  }

  /**
   * 按状态过滤
   */
  static filterByStatus(nodes: Node[], statuses: string[]): Node[] {
    if (statuses.length === 0) {
      return nodes;
    }

    return nodes.filter(node => {
      const status = node.data?.status || 'idle';
      return statuses.includes(status);
    });
  }

  /**
   * 按标签过滤
   */
  static filterByTags(nodes: Node[], tags: string[]): Node[] {
    if (tags.length === 0) {
      return nodes;
    }

    return nodes.filter(node => {
      const nodeTags = node.data?.tags || [];
      return tags.some(tag => nodeTags.includes(tag));
    });
  }

  /**
   * 组合过滤
   */
  static filter(nodes: Node[], condition: FilterCondition): Node[] {
    let filtered = nodes;

    if (condition.type && condition.type.length > 0) {
      filtered = this.filterByType(filtered, condition.type);
    }

    if (condition.status && condition.status.length > 0) {
      filtered = this.filterByStatus(filtered, condition.status);
    }

    if (condition.tags && condition.tags.length > 0) {
      filtered = this.filterByTags(filtered, condition.tags);
    }

    return filtered;
  }

  /**
   * 获取所有节点类型
   */
  static getNodeTypes(nodes: Node[]): string[] {
    const types = new Set<string>();
    nodes.forEach(node => {
      types.add(node.type || 'default');
    });
    return Array.from(types).sort();
  }

  /**
   * 获取所有节点状态
   */
  static getNodeStatuses(nodes: Node[]): string[] {
    const statuses = new Set<string>();
    nodes.forEach(node => {
      statuses.add(node.data?.status || 'idle');
    });
    return Array.from(statuses).sort();
  }

  /**
   * 获取所有标签
   */
  static getAllTags(nodes: Node[]): string[] {
    const tags = new Set<string>();
    nodes.forEach(node => {
      const nodeTags = node.data?.tags || [];
      nodeTags.forEach((tag: string) => tags.add(tag));
    });
    return Array.from(tags).sort();
  }
}
