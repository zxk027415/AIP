import { Node, Edge } from 'reactflow';
import { BaseCommand } from './Command';

/**
 * 添加节点命令
 */
export class AddNodeCommand extends BaseCommand {
  private node: Node;
  private onAdd: (node: Node) => void;
  private onRemove: (nodeId: string) => void;

  constructor(
    node: Node,
    onAdd: (node: Node) => void,
    onRemove: (nodeId: string) => void
  ) {
    super();
    this.node = node;
    this.onAdd = onAdd;
    this.onRemove = onRemove;
  }

  execute(): void {
    this.onAdd(this.node);
  }

  undo(): void {
    this.onRemove(this.node.id);
  }

  getDescription(): string {
    return `添加节点: ${this.node.data.label || this.node.id}`;
  }
}

/**
 * 删除节点命令
 */
export class DeleteNodeCommand extends BaseCommand {
  private node: Node;
  private edges: Edge[];
  private onAdd: (node: Node) => void;
  private onRemove: (nodeId: string) => void;
  private onAddEdge: (edge: Edge) => void;

  constructor(
    node: Node,
    edges: Edge[],
    onAdd: (node: Node) => void,
    onRemove: (nodeId: string) => void,
    onAddEdge: (edge: Edge) => void
  ) {
    super();
    this.node = node;
    this.edges = edges;
    this.onAdd = onAdd;
    this.onRemove = onRemove;
    this.onAddEdge = onAddEdge;
  }

  execute(): void {
    this.onRemove(this.node.id);
  }

  undo(): void {
    this.onAdd(this.node);
    // 恢复相关的边
    this.edges.forEach(edge => this.onAddEdge(edge));
  }

  getDescription(): string {
    return `删除节点: ${this.node.data.label || this.node.id}`;
  }
}

/**
 * 移动节点命令（支持合并）
 */
export class MoveNodeCommand extends BaseCommand {
  private nodeId: string;
  private oldPosition: { x: number; y: number };
  private newPosition: { x: number; y: number };
  private onMove: (nodeId: string, position: { x: number; y: number }) => void;

  constructor(
    nodeId: string,
    oldPosition: { x: number; y: number },
    newPosition: { x: number; y: number },
    onMove: (nodeId: string, position: { x: number; y: number }) => void
  ) {
    super();
    this.nodeId = nodeId;
    this.oldPosition = oldPosition;
    this.newPosition = newPosition;
    this.onMove = onMove;
  }

  execute(): void {
    this.onMove(this.nodeId, this.newPosition);
  }

  undo(): void {
    this.onMove(this.nodeId, this.oldPosition);
  }

  getDescription(): string {
    return `移动节点: ${this.nodeId}`;
  }

  canMergeWith(command: BaseCommand): boolean {
    if (!(command instanceof MoveNodeCommand)) {
      return false;
    }
    return this.nodeId === command.nodeId;
  }

  mergeWith(command: BaseCommand): void {
    if (command instanceof MoveNodeCommand) {
      this.newPosition = command.newPosition;
    }
  }
}

/**
 * 更新节点数据命令
 */
export class UpdateNodeCommand extends BaseCommand {
  private nodeId: string;
  private oldData: any;
  private newData: any;
  private onUpdate: (nodeId: string, data: any) => void;

  constructor(
    nodeId: string,
    oldData: any,
    newData: any,
    onUpdate: (nodeId: string, data: any) => void
  ) {
    super();
    this.nodeId = nodeId;
    this.oldData = oldData;
    this.newData = newData;
    this.onUpdate = onUpdate;
  }

  execute(): void {
    this.onUpdate(this.nodeId, this.newData);
  }

  undo(): void {
    this.onUpdate(this.nodeId, this.oldData);
  }

  getDescription(): string {
    return `更新节点: ${this.nodeId}`;
  }
}

/**
 * 添加边命令
 */
export class AddEdgeCommand extends BaseCommand {
  private edge: Edge;
  private onAdd: (edge: Edge) => void;
  private onRemove: (edgeId: string) => void;

  constructor(
    edge: Edge,
    onAdd: (edge: Edge) => void,
    onRemove: (edgeId: string) => void
  ) {
    super();
    this.edge = edge;
    this.onAdd = onAdd;
    this.onRemove = onRemove;
  }

  execute(): void {
    this.onAdd(this.edge);
  }

  undo(): void {
    this.onRemove(this.edge.id);
  }

  getDescription(): string {
    return `添加连接: ${this.edge.source} → ${this.edge.target}`;
  }
}

/**
 * 删除边命令
 */
export class DeleteEdgeCommand extends BaseCommand {
  private edge: Edge;
  private onAdd: (edge: Edge) => void;
  private onRemove: (edgeId: string) => void;

  constructor(
    edge: Edge,
    onAdd: (edge: Edge) => void,
    onRemove: (edgeId: string) => void
  ) {
    super();
    this.edge = edge;
    this.onAdd = onAdd;
    this.onRemove = onRemove;
  }

  execute(): void {
    this.onRemove(this.edge.id);
  }

  undo(): void {
    this.onAdd(this.edge);
  }

  getDescription(): string {
    return `删除连接: ${this.edge.source} → ${this.edge.target}`;
  }
}

/**
 * 批量命令
 */
export class BatchCommand extends BaseCommand {
  private commands: BaseCommand[];
  private description: string;

  constructor(commands: BaseCommand[], description: string = '批量操作') {
    super();
    this.commands = commands;
    this.description = description;
  }

  execute(): void {
    this.commands.forEach(cmd => cmd.execute());
  }

  undo(): void {
    // 反向撤销
    for (let i = this.commands.length - 1; i >= 0; i--) {
      this.commands[i].undo();
    }
  }

  getDescription(): string {
    return `${this.description} (${this.commands.length}个操作)`;
  }
}
