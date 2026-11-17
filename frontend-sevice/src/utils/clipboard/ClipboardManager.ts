import { Node, Edge } from 'reactflow';

/**
 * 剪贴板数据类型
 */
export interface ClipboardData {
  nodes: Node[];
  edges: Edge[];
  timestamp: number;
}

/**
 * 剪贴板管理器
 */
export class ClipboardManager {
  private clipboardData: ClipboardData | null = null;
  private idCounter: number = 1;

  /**
   * 复制节点和边
   */
  copy(nodes: Node[], edges: Edge[]): void {
    // 只保留选中节点之间的边
    const nodeIds = new Set(nodes.map(n => n.id));
    const filteredEdges = edges.filter(
      e => nodeIds.has(e.source) && nodeIds.has(e.target)
    );

    this.clipboardData = {
      nodes: JSON.parse(JSON.stringify(nodes)), // 深拷贝
      edges: JSON.parse(JSON.stringify(filteredEdges)),
      timestamp: Date.now(),
    };

    // 尝试使用系统剪贴板API
    this.copyToSystemClipboard(this.clipboardData);
  }

  /**
   * 粘贴节点和边
   * @param offsetX X轴偏移量
   * @param offsetY Y轴偏移量
   * @returns 新创建的节点和边
   */
  paste(offsetX: number = 50, offsetY: number = 50): ClipboardData | null {
    if (!this.clipboardData) {
      return null;
    }

    // 创建ID映射表
    const idMap = new Map<string, string>();
    
    // 复制节点并生成新ID
    const newNodes = this.clipboardData.nodes.map(node => {
      const newId = this.generateId();
      idMap.set(node.id, newId);

      return {
        ...node,
        id: newId,
        position: {
          x: node.position.x + offsetX,
          y: node.position.y + offsetY,
        },
        selected: true, // 选中新粘贴的节点
      };
    });

    // 复制边并更新ID引用
    const newEdges = this.clipboardData.edges.map(edge => {
      const newSourceId = idMap.get(edge.source);
      const newTargetId = idMap.get(edge.target);

      if (!newSourceId || !newTargetId) {
        return null;
      }

      return {
        ...edge,
        id: `e${newSourceId}-${newTargetId}`,
        source: newSourceId,
        target: newTargetId,
      };
    }).filter(Boolean) as Edge[];

    return {
      nodes: newNodes,
      edges: newEdges,
      timestamp: Date.now(),
    };
  }

  /**
   * 剪切节点和边
   */
  cut(nodes: Node[], edges: Edge[]): void {
    this.copy(nodes, edges);
  }

  /**
   * 复制到系统剪贴板
   */
  private async copyToSystemClipboard(data: ClipboardData): Promise<void> {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        const text = JSON.stringify(data);
        await navigator.clipboard.writeText(text);
      }
    } catch (error) {
      console.warn('无法访问系统剪贴板:', error);
    }
  }

  /**
   * 从系统剪贴板读取
   */
  async pasteFromSystemClipboard(): Promise<ClipboardData | null> {
    try {
      if (navigator.clipboard && navigator.clipboard.readText) {
        const text = await navigator.clipboard.readText();
        const data = JSON.parse(text) as ClipboardData;
        
        // 验证数据格式
        if (data.nodes && data.edges && data.timestamp) {
          this.clipboardData = data;
          return this.paste();
        }
      }
    } catch (error) {
      console.warn('无法从系统剪贴板读取:', error);
    }
    
    return null;
  }

  /**
   * 检查剪贴板是否有数据
   */
  hasData(): boolean {
    return this.clipboardData !== null;
  }

  /**
   * 清空剪贴板
   */
  clear(): void {
    this.clipboardData = null;
  }

  /**
   * 生成唯一ID
   */
  private generateId(): string {
    return `node_${Date.now()}_${this.idCounter++}`;
  }

  /**
   * 获取剪贴板数据（用于预览）
   */
  getClipboardData(): ClipboardData | null {
    return this.clipboardData;
  }
}

// 全局剪贴板管理器实例
export const clipboardManager = new ClipboardManager();
