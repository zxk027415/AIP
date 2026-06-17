import { Node, Edge } from 'reactflow';
import { ClipboardManager } from '../ClipboardManager';

describe('ClipboardManager', () => {
  let clipboardManager: ClipboardManager;

  beforeEach(() => {
    clipboardManager = new ClipboardManager();
  });

  describe('copy', () => {
    it('should copy nodes and edges', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: { label: 'Node 1' }, position: { x: 0, y: 0 } },
        { id: '2', type: 'default', data: { label: 'Node 2' }, position: { x: 100, y: 100 } },
      ];

      const edges: Edge[] = [
        { id: 'e1-2', source: '1', target: '2' },
      ];

      clipboardManager.copy(nodes, edges);

      expect(clipboardManager.hasData()).toBe(true);
    });

    it('should filter edges to only include selected nodes', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: {}, position: { x: 0, y: 0 } },
      ];

      const edges: Edge[] = [
        { id: 'e1-2', source: '1', target: '2' }, // Should be filtered out
        { id: 'e1-3', source: '1', target: '3' }, // Should be filtered out
      ];

      clipboardManager.copy(nodes, edges);

      const data = clipboardManager.getClipboardData();
      expect(data?.edges.length).toBe(0);
    });

    it('should deep copy nodes', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: { label: 'Original' }, position: { x: 0, y: 0 } },
      ];

      clipboardManager.copy(nodes, []);

      // Modify original
      nodes[0].data.label = 'Modified';

      const data = clipboardManager.getClipboardData();
      expect(data?.nodes[0].data.label).toBe('Original');
    });
  });

  describe('paste', () => {
    it('should paste with offset', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: {}, position: { x: 0, y: 0 } },
      ];

      clipboardManager.copy(nodes, []);
      const pasted = clipboardManager.paste(50, 50);

      expect(pasted).not.toBeNull();
      expect(pasted!.nodes[0].position.x).toBe(50);
      expect(pasted!.nodes[0].position.y).toBe(50);
    });

    it('should generate new IDs', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: {}, position: { x: 0, y: 0 } },
      ];

      clipboardManager.copy(nodes, []);
      const pasted = clipboardManager.paste();

      expect(pasted).not.toBeNull();
      expect(pasted!.nodes[0].id).not.toBe('1');
    });

    it('should update edge references', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: {}, position: { x: 0, y: 0 } },
        { id: '2', type: 'default', data: {}, position: { x: 100, y: 100 } },
      ];

      const edges: Edge[] = [
        { id: 'e1-2', source: '1', target: '2' },
      ];

      clipboardManager.copy(nodes, edges);
      const pasted = clipboardManager.paste();

      expect(pasted).not.toBeNull();
      expect(pasted!.edges.length).toBe(1);
      expect(pasted!.edges[0].source).toBe(pasted!.nodes[0].id);
      expect(pasted!.edges[0].target).toBe(pasted!.nodes[1].id);
    });

    it('should select pasted nodes', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: {}, position: { x: 0, y: 0 } },
      ];

      clipboardManager.copy(nodes, []);
      const pasted = clipboardManager.paste();

      expect(pasted).not.toBeNull();
      expect(pasted!.nodes[0].selected).toBe(true);
    });

    it('should return null when clipboard is empty', () => {
      const pasted = clipboardManager.paste();
      expect(pasted).toBeNull();
    });

    it('should generate unique IDs on multiple pastes', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: {}, position: { x: 0, y: 0 } },
      ];

      clipboardManager.copy(nodes, []);
      const pasted1 = clipboardManager.paste();
      const pasted2 = clipboardManager.paste();

      expect(pasted1!.nodes[0].id).not.toBe(pasted2!.nodes[0].id);
    });
  });

  describe('clear', () => {
    it('should clear clipboard data', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: {}, position: { x: 0, y: 0 } },
      ];

      clipboardManager.copy(nodes, []);
      expect(clipboardManager.hasData()).toBe(true);

      clipboardManager.clear();
      expect(clipboardManager.hasData()).toBe(false);
    });
  });

  describe('hasData', () => {
    it('should return false initially', () => {
      expect(clipboardManager.hasData()).toBe(false);
    });

    it('should return true after copy', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: {}, position: { x: 0, y: 0 } },
      ];

      clipboardManager.copy(nodes, []);
      expect(clipboardManager.hasData()).toBe(true);
    });
  });

  describe('getClipboardData', () => {
    it('should return clipboard data', () => {
      const nodes: Node[] = [
        { id: '1', type: 'default', data: { label: 'Test' }, position: { x: 0, y: 0 } },
      ];

      clipboardManager.copy(nodes, []);
      const data = clipboardManager.getClipboardData();

      expect(data).not.toBeNull();
      expect(data!.nodes.length).toBe(1);
      expect(data!.nodes[0].data.label).toBe('Test');
    });

    it('should return null when empty', () => {
      const data = clipboardManager.getClipboardData();
      expect(data).toBeNull();
    });
  });
});
