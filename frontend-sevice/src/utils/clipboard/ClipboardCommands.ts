import { Node, Edge } from 'reactflow';
import { BaseCommand } from '../commands/Command';

/**
 * 复制命令（不修改画布，只更新剪贴板）
 */
export class CopyCommand extends BaseCommand {
  private nodes: Node[];
  private edges: Edge[];
  private onCopy: (nodes: Node[], edges: Edge[]) => void;

  constructor(
    nodes: Node[],
    edges: Edge[],
    onCopy: (nodes: Node[], edges: Edge[]) => void
  ) {
    super();
    this.nodes = nodes;
    this.edges = edges;
    this.onCopy = onCopy;
  }

  execute(): void {
    this.onCopy(this.nodes, this.edges);
  }

  undo(): void {
    // 复制操作不需要撤销
  }

  getDescription(): string {
    return `复制 ${this.nodes.length} 个节点`;
  }
}

/**
 * 粘贴命令
 */
export class PasteCommand extends BaseCommand {
  private pastedNodes: Node[];
  private pastedEdges: Edge[];
  private onAdd: (nodes: Node[], edges: Edge[]) => void;
  private onRemove: (nodeIds: string[], edgeIds: string[]) => void;

  constructor(
    pastedNodes: Node[],
    pastedEdges: Edge[],
    onAdd: (nodes: Node[], edges: Edge[]) => void,
    onRemove: (nodeIds: string[], edgeIds: string[]) => void
  ) {
    super();
    this.pastedNodes = pastedNodes;
    this.pastedEdges = pastedEdges;
    this.onAdd = onAdd;
    this.onRemove = onRemove;
  }

  execute(): void {
    this.onAdd(this.pastedNodes, this.pastedEdges);
  }

  undo(): void {
    const nodeIds = this.pastedNodes.map(n => n.id);
    const edgeIds = this.pastedEdges.map(e => e.id);
    this.onRemove(nodeIds, edgeIds);
  }

  getDescription(): string {
    return `粘贴 ${this.pastedNodes.length} 个节点`;
  }
}

/**
 * 剪切命令（复制 + 删除）
 */
export class CutCommand extends BaseCommand {
  private nodes: Node[];
  private edges: Edge[];
  private onCopy: (nodes: Node[], edges: Edge[]) => void;
  private onRemove: (nodeIds: string[], edgeIds: string[]) => void;
  private onAdd: (nodes: Node[], edges: Edge[]) => void;

  constructor(
    nodes: Node[],
    edges: Edge[],
    onCopy: (nodes: Node[], edges: Edge[]) => void,
    onRemove: (nodeIds: string[], edgeIds: string[]) => void,
    onAdd: (nodes: Node[], edges: Edge[]) => void
  ) {
    super();
    this.nodes = nodes;
    this.edges = edges;
    this.onCopy = onCopy;
    this.onRemove = onRemove;
    this.onAdd = onAdd;
  }

  execute(): void {
    // 先复制到剪贴板
    this.onCopy(this.nodes, this.edges);
    
    // 然后删除节点
    const nodeIds = this.nodes.map(n => n.id);
    const edgeIds = this.edges.map(e => e.id);
    this.onRemove(nodeIds, edgeIds);
  }

  undo(): void {
    // 恢复删除的节点和边
    this.onAdd(this.nodes, this.edges);
  }

  getDescription(): string {
    return `剪切 ${this.nodes.length} 个节点`;
  }
}

/**
 * 复制命令（Duplicate - 直接复制并粘贴）
 */
export class DuplicateCommand extends BaseCommand {
  private originalNodes: Node[];
  private originalEdges: Edge[];
  private duplicatedNodes: Node[];
  private duplicatedEdges: Edge[];
  private onAdd: (nodes: Node[], edges: Edge[]) => void;
  private onRemove: (nodeIds: string[], edgeIds: string[]) => void;

  constructor(
    originalNodes: Node[],
    originalEdges: Edge[],
    duplicatedNodes: Node[],
    duplicatedEdges: Edge[],
    onAdd: (nodes: Node[], edges: Edge[]) => void,
    onRemove: (nodeIds: string[], edgeIds: string[]) => void
  ) {
    super();
    this.originalNodes = originalNodes;
    this.originalEdges = originalEdges;
    this.duplicatedNodes = duplicatedNodes;
    this.duplicatedEdges = duplicatedEdges;
    this.onAdd = onAdd;
    this.onRemove = onRemove;
  }

  execute(): void {
    this.onAdd(this.duplicatedNodes, this.duplicatedEdges);
  }

  undo(): void {
    const nodeIds = this.duplicatedNodes.map(n => n.id);
    const edgeIds = this.duplicatedEdges.map(e => e.id);
    this.onRemove(nodeIds, edgeIds);
  }

  getDescription(): string {
    return `复制 ${this.originalNodes.length} 个节点`;
  }
}
