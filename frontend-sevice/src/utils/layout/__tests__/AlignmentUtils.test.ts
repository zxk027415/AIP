import { Node } from 'reactflow';
import { AlignmentUtils, AlignmentType, DistributionType } from '../AlignmentUtils';

describe('AlignmentUtils', () => {
  const createNode = (id: string, x: number, y: number, width = 150, height = 40): Node => ({
    id,
    type: 'default',
    position: { x, y },
    data: { label: id },
    width,
    height,
  });

  describe('alignLeft', () => {
    it('should align nodes to the left', () => {
      const nodes = [
        createNode('1', 100, 50),
        createNode('2', 200, 100),
        createNode('3', 150, 150),
      ];

      const aligned = AlignmentUtils.alignLeft(nodes);

      expect(aligned[0].position.x).toBe(100);
      expect(aligned[1].position.x).toBe(100);
      expect(aligned[2].position.x).toBe(100);

      // Y positions should remain unchanged
      expect(aligned[0].position.y).toBe(50);
      expect(aligned[1].position.y).toBe(100);
      expect(aligned[2].position.y).toBe(150);
    });

    it('should return unchanged for single node', () => {
      const nodes = [createNode('1', 100, 50)];
      const aligned = AlignmentUtils.alignLeft(nodes);

      expect(aligned[0].position.x).toBe(100);
    });

    it('should return unchanged for empty array', () => {
      const nodes: Node[] = [];
      const aligned = AlignmentUtils.alignLeft(nodes);

      expect(aligned).toEqual([]);
    });
  });

  describe('alignRight', () => {
    it('should align nodes to the right', () => {
      const nodes = [
        createNode('1', 100, 50, 150, 40),
        createNode('2', 200, 100, 150, 40),
        createNode('3', 150, 150, 150, 40),
      ];

      const aligned = AlignmentUtils.alignRight(nodes);

      // All nodes should align to the rightmost edge (200 + 150 = 350)
      expect(aligned[0].position.x).toBe(200);
      expect(aligned[1].position.x).toBe(200);
      expect(aligned[2].position.x).toBe(200);
    });
  });

  describe('alignTop', () => {
    it('should align nodes to the top', () => {
      const nodes = [
        createNode('1', 100, 100),
        createNode('2', 200, 50),
        createNode('3', 150, 150),
      ];

      const aligned = AlignmentUtils.alignTop(nodes);

      expect(aligned[0].position.y).toBe(50);
      expect(aligned[1].position.y).toBe(50);
      expect(aligned[2].position.y).toBe(50);

      // X positions should remain unchanged
      expect(aligned[0].position.x).toBe(100);
      expect(aligned[1].position.x).toBe(200);
      expect(aligned[2].position.x).toBe(150);
    });
  });

  describe('alignBottom', () => {
    it('should align nodes to the bottom', () => {
      const nodes = [
        createNode('1', 100, 100, 150, 40),
        createNode('2', 200, 50, 150, 40),
        createNode('3', 150, 150, 150, 40),
      ];

      const aligned = AlignmentUtils.alignBottom(nodes);

      // All nodes should align to the bottom edge (150 + 40 = 190)
      expect(aligned[0].position.y).toBe(150);
      expect(aligned[1].position.y).toBe(150);
      expect(aligned[2].position.y).toBe(150);
    });
  });

  describe('alignCenterHorizontal', () => {
    it('should align nodes to horizontal center', () => {
      const nodes = [
        createNode('1', 0, 50, 100, 40),
        createNode('2', 200, 100, 100, 40),
        createNode('3', 100, 150, 100, 40),
      ];

      const aligned = AlignmentUtils.alignCenterHorizontal(nodes);

      // Calculate expected center: (50 + 250 + 150) / 3 = 150
      // Each node should be centered at x = 150 - 50 = 100
      const centerX = (50 + 250 + 150) / 3;

      aligned.forEach(node => {
        const nodeCenterX = node.position.x + (node.width || 150) / 2;
        expect(nodeCenterX).toBeCloseTo(centerX, 5);
      });
    });
  });

  describe('alignCenterVertical', () => {
    it('should align nodes to vertical center', () => {
      const nodes = [
        createNode('1', 100, 0, 150, 40),
        createNode('2', 200, 100, 150, 40),
        createNode('3', 150, 50, 150, 40),
      ];

      const aligned = AlignmentUtils.alignCenterVertical(nodes);

      // Calculate expected center: (20 + 120 + 70) / 3 = 70
      const centerY = (20 + 120 + 70) / 3;

      aligned.forEach(node => {
        const nodeCenterY = node.position.y + (node.height || 40) / 2;
        expect(nodeCenterY).toBeCloseTo(centerY, 5);
      });
    });
  });

  describe('distributeHorizontally', () => {
    it('should distribute nodes horizontally with equal spacing', () => {
      const nodes = [
        createNode('1', 0, 50),
        createNode('2', 100, 50),
        createNode('3', 400, 50),
      ];

      const distributed = AlignmentUtils.distributeHorizontally(nodes);

      // Nodes should be evenly spaced between 0 and 400
      expect(distributed[0].position.x).toBe(0);
      expect(distributed[1].position.x).toBe(200);
      expect(distributed[2].position.x).toBe(400);
    });

    it('should return unchanged for less than 3 nodes', () => {
      const nodes = [
        createNode('1', 0, 50),
        createNode('2', 100, 50),
      ];

      const distributed = AlignmentUtils.distributeHorizontally(nodes);

      expect(distributed[0].position.x).toBe(0);
      expect(distributed[1].position.x).toBe(100);
    });

    it('should sort nodes by x position before distributing', () => {
      const nodes = [
        createNode('1', 400, 50),
        createNode('2', 0, 50),
        createNode('3', 100, 50),
      ];

      const distributed = AlignmentUtils.distributeHorizontally(nodes);

      // Should be sorted: 0, 200, 400
      const sortedByX = distributed.sort((a, b) => a.position.x - b.position.x);
      expect(sortedByX[0].position.x).toBe(0);
      expect(sortedByX[1].position.x).toBe(200);
      expect(sortedByX[2].position.x).toBe(400);
    });
  });

  describe('distributeVertically', () => {
    it('should distribute nodes vertically with equal spacing', () => {
      const nodes = [
        createNode('1', 50, 0),
        createNode('2', 50, 100),
        createNode('3', 50, 400),
      ];

      const distributed = AlignmentUtils.distributeVertically(nodes);

      // Nodes should be evenly spaced between 0 and 400
      expect(distributed[0].position.y).toBe(0);
      expect(distributed[1].position.y).toBe(200);
      expect(distributed[2].position.y).toBe(400);
    });

    it('should return unchanged for less than 3 nodes', () => {
      const nodes = [
        createNode('1', 50, 0),
        createNode('2', 50, 100),
      ];

      const distributed = AlignmentUtils.distributeVertically(nodes);

      expect(distributed[0].position.y).toBe(0);
      expect(distributed[1].position.y).toBe(100);
    });
  });

  describe('snapToGrid', () => {
    it('should snap nodes to grid with default size 20', () => {
      const nodes = [
        createNode('1', 15, 27),
        createNode('2', 43, 58),
        createNode('3', 91, 112),
      ];

      const snapped = AlignmentUtils.snapToGrid(nodes);

      expect(snapped[0].position.x).toBe(20);
      expect(snapped[0].position.y).toBe(20);
      expect(snapped[1].position.x).toBe(40);
      expect(snapped[1].position.y).toBe(60);
      expect(snapped[2].position.x).toBe(100);
      expect(snapped[2].position.y).toBe(120);
    });

    it('should snap nodes to custom grid size', () => {
      const nodes = [
        createNode('1', 15, 27),
        createNode('2', 43, 58),
      ];

      const snapped = AlignmentUtils.snapToGrid(nodes, 10);

      expect(snapped[0].position.x).toBe(20);
      expect(snapped[0].position.y).toBe(30);
      expect(snapped[1].position.x).toBe(40);
      expect(snapped[1].position.y).toBe(60);
    });

    it('should handle nodes already on grid', () => {
      const nodes = [
        createNode('1', 20, 40),
        createNode('2', 60, 80),
      ];

      const snapped = AlignmentUtils.snapToGrid(nodes, 20);

      expect(snapped[0].position.x).toBe(20);
      expect(snapped[0].position.y).toBe(40);
      expect(snapped[1].position.x).toBe(60);
      expect(snapped[1].position.y).toBe(80);
    });
  });

  describe('align', () => {
    it('should call correct alignment method', () => {
      const nodes = [
        createNode('1', 100, 50),
        createNode('2', 200, 100),
      ];

      const leftAligned = AlignmentUtils.align(nodes, AlignmentType.LEFT);
      expect(leftAligned[0].position.x).toBe(100);
      expect(leftAligned[1].position.x).toBe(100);

      const topAligned = AlignmentUtils.align(nodes, AlignmentType.TOP);
      expect(topAligned[0].position.y).toBe(50);
      expect(topAligned[1].position.y).toBe(50);
    });

    it('should handle all alignment types', () => {
      const nodes = [
        createNode('1', 100, 50),
        createNode('2', 200, 100),
      ];

      expect(() => AlignmentUtils.align(nodes, AlignmentType.LEFT)).not.toThrow();
      expect(() => AlignmentUtils.align(nodes, AlignmentType.RIGHT)).not.toThrow();
      expect(() => AlignmentUtils.align(nodes, AlignmentType.TOP)).not.toThrow();
      expect(() => AlignmentUtils.align(nodes, AlignmentType.BOTTOM)).not.toThrow();
      expect(() => AlignmentUtils.align(nodes, AlignmentType.CENTER_HORIZONTAL)).not.toThrow();
      expect(() => AlignmentUtils.align(nodes, AlignmentType.CENTER_VERTICAL)).not.toThrow();
    });
  });

  describe('distribute', () => {
    it('should call correct distribution method', () => {
      const nodes = [
        createNode('1', 0, 50),
        createNode('2', 100, 50),
        createNode('3', 400, 50),
      ];

      const horizontalDist = AlignmentUtils.distribute(nodes, DistributionType.HORIZONTAL);
      expect(horizontalDist[1].position.x).toBe(200);

      const verticalNodes = [
        createNode('1', 50, 0),
        createNode('2', 50, 100),
        createNode('3', 50, 400),
      ];

      const verticalDist = AlignmentUtils.distribute(verticalNodes, DistributionType.VERTICAL);
      expect(verticalDist[1].position.y).toBe(200);
    });
  });

  describe('edge cases', () => {
    it('should handle nodes with missing width/height', () => {
      const nodes: Node[] = [
        {
          id: '1',
          type: 'default',
          position: { x: 100, y: 50 },
          data: { label: '1' },
        },
        {
          id: '2',
          type: 'default',
          position: { x: 200, y: 100 },
          data: { label: '2' },
        },
      ];

      expect(() => AlignmentUtils.alignLeft(nodes)).not.toThrow();
      expect(() => AlignmentUtils.alignRight(nodes)).not.toThrow();
    });

    it('should handle negative positions', () => {
      const nodes = [
        createNode('1', -100, -50),
        createNode('2', -200, -100),
      ];

      const aligned = AlignmentUtils.alignLeft(nodes);
      expect(aligned[0].position.x).toBe(-200);
      expect(aligned[1].position.x).toBe(-200);
    });

    it('should preserve node data', () => {
      const nodes = [
        {
          ...createNode('1', 100, 50),
          data: { label: 'Node 1', custom: 'data' },
        },
        {
          ...createNode('2', 200, 100),
          data: { label: 'Node 2', custom: 'data' },
        },
      ];

      const aligned = AlignmentUtils.alignLeft(nodes);

      expect(aligned[0].data).toEqual({ label: 'Node 1', custom: 'data' });
      expect(aligned[1].data).toEqual({ label: 'Node 2', custom: 'data' });
    });
  });
});
