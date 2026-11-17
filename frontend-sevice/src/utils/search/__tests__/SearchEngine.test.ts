import { Node } from 'reactflow';
import { SearchEngine, SearchHistory } from '../SearchEngine';

describe('SearchEngine', () => {
  const createNode = (id: string, label: string, type = 'default', data = {}): Node => ({
    id,
    type,
    position: { x: 0, y: 0 },
    data: { label, ...data },
  });

  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();
  });

  describe('search', () => {
    it('should return empty array for empty query', () => {
      const nodes = [createNode('1', 'Test Node')];
      const results = SearchEngine.search(nodes, '');

      expect(results).toEqual([]);
    });

    it('should search by node ID', () => {
      const nodes = [
        createNode('node-1', 'First'),
        createNode('node-2', 'Second'),
        createNode('test-3', 'Third'),
      ];

      const results = SearchEngine.search(nodes, 'node');

      expect(results).toHaveLength(2);
      expect(results[0].node.id).toMatch(/node/);
      expect(results[1].node.id).toMatch(/node/);
    });

    it('should search by node label', () => {
      const nodes = [
        createNode('1', 'Calculate Sum'),
        createNode('2', 'Display Result'),
        createNode('3', 'Calculate Average'),
      ];

      const results = SearchEngine.search(nodes, 'calculate');

      expect(results).toHaveLength(2);
      expect(results[0].matches.some(m => m.field === 'label')).toBe(true);
    });

    it('should search by node type', () => {
      const nodes = [
        createNode('1', 'Node 1', 'function'),
        createNode('2', 'Node 2', 'matrix'),
        createNode('3', 'Node 3', 'function'),
      ];

      const results = SearchEngine.search(nodes, 'function');

      expect(results).toHaveLength(2);
      expect(results.every(r => r.node.type === 'function')).toBe(true);
    });

    it('should search in node data', () => {
      const nodes = [
        createNode('1', 'Node 1', 'default', { description: 'Process data' }),
        createNode('2', 'Node 2', 'default', { description: 'Display output' }),
        createNode('3', 'Node 3', 'default', { description: 'Process input' }),
      ];

      const results = SearchEngine.search(nodes, 'process');

      expect(results).toHaveLength(2);
    });

    it('should be case insensitive', () => {
      const nodes = [
        createNode('1', 'Calculate Sum'),
        createNode('2', 'CALCULATE AVERAGE'),
      ];

      const results = SearchEngine.search(nodes, 'CALCULATE');

      expect(results).toHaveLength(2);
    });

    it('should calculate scores correctly', () => {
      const nodes = [
        createNode('1', 'Test'),
        createNode('test-node', 'Node'),
        createNode('3', 'Other', 'test'),
      ];

      const results = SearchEngine.search(nodes, 'test');

      // Label matches should have higher score than ID matches
      expect(results[0].score).toBeGreaterThan(results[1].score);
    });

    it('should sort results by score', () => {
      const nodes = [
        createNode('1', 'Other', 'default', { info: 'test' }),
        createNode('test-id', 'Node'),
        createNode('3', 'Test Label'),
      ];

      const results = SearchEngine.search(nodes, 'test');

      // Results should be sorted by score (descending)
      for (let i = 0; i < results.length - 1; i++) {
        expect(results[i].score).toBeGreaterThanOrEqual(results[i + 1].score);
      }
    });

    it('should find multiple matches in same node', () => {
      const nodes = [
        createNode('test-1', 'Test Node', 'test', { description: 'test data' }),
      ];

      const results = SearchEngine.search(nodes, 'test');

      expect(results).toHaveLength(1);
      expect(results[0].matches.length).toBeGreaterThan(1);
    });

    it('should handle special characters in query', () => {
      const nodes = [
        createNode('1', 'Node (test)'),
        createNode('2', 'Node [test]'),
      ];

      const results = SearchEngine.search(nodes, '(test)');

      expect(results).toHaveLength(1);
    });
  });

  describe('fuzzySearch', () => {
    it('should return empty array for empty query', () => {
      const nodes = [createNode('1', 'Test Node')];
      const results = SearchEngine.fuzzySearch(nodes, '');

      expect(results).toEqual([]);
    });

    it('should find exact matches', () => {
      const nodes = [
        createNode('1', 'Calculate'),
        createNode('2', 'Display'),
      ];

      const results = SearchEngine.fuzzySearch(nodes, 'calculate');

      expect(results).toHaveLength(1);
      expect(results[0].score).toBe(100);
    });

    it('should find similar strings', () => {
      const nodes = [
        createNode('1', 'Calculate'),
        createNode('2', 'Calcuate'), // typo
        createNode('3', 'Display'),
      ];

      const results = SearchEngine.fuzzySearch(nodes, 'calculate');

      // Should find both Calculate and Calcuate
      expect(results.length).toBeGreaterThanOrEqual(1);
      expect(results[0].node.data.label.toLowerCase()).toContain('calc');
    });

    it('should filter out low similarity matches', () => {
      const nodes = [
        createNode('1', 'Calculate'),
        createNode('2', 'xyz'), // very different
      ];

      const results = SearchEngine.fuzzySearch(nodes, 'calculate');

      // Should only find Calculate, not xyz
      expect(results).toHaveLength(1);
      expect(results[0].node.id).toBe('1');
    });

    it('should sort by similarity score', () => {
      const nodes = [
        createNode('1', 'Calcuate'), // 1 char different
        createNode('2', 'Calculate'), // exact match
        createNode('3', 'Calc'), // shorter but similar
      ];

      const results = SearchEngine.fuzzySearch(nodes, 'calculate');

      // Exact match should have highest score
      expect(results[0].score).toBe(100);
    });

    it('should be case insensitive', () => {
      const nodes = [
        createNode('1', 'CALCULATE'),
        createNode('2', 'calculate'),
      ];

      const results = SearchEngine.fuzzySearch(nodes, 'Calculate');

      expect(results).toHaveLength(2);
    });
  });

  describe('levenshteinDistance', () => {
    it('should calculate distance correctly', () => {
      const nodes = [
        createNode('1', 'kitten'),
        createNode('2', 'sitting'),
      ];

      // Test through fuzzySearch which uses levenshteinDistance internally
      const results1 = SearchEngine.fuzzySearch(nodes, 'kitten');
      const results2 = SearchEngine.fuzzySearch(nodes, 'sitting');

      expect(results1[0].node.id).toBe('1');
      expect(results2[0].node.id).toBe('2');
    });

    it('should handle empty strings', () => {
      const nodes = [createNode('1', '')];
      const results = SearchEngine.fuzzySearch(nodes, 'test');

      // Empty string should have low similarity
      expect(results).toHaveLength(0);
    });
  });

  describe('findIndices', () => {
    it('should find all match positions', () => {
      const nodes = [
        createNode('1', 'test test test'),
      ];

      const results = SearchEngine.search(nodes, 'test');

      expect(results).toHaveLength(1);
      const labelMatch = results[0].matches.find(m => m.field === 'label');
      expect(labelMatch?.indices).toHaveLength(3);
    });

    it('should find overlapping matches', () => {
      const nodes = [
        createNode('1', 'aaa'),
      ];

      const results = SearchEngine.search(nodes, 'aa');

      expect(results).toHaveLength(1);
      const labelMatch = results[0].matches.find(m => m.field === 'label');
      expect(labelMatch?.indices.length).toBeGreaterThan(0);
    });
  });

  describe('edge cases', () => {
    it('should handle empty node array', () => {
      const results = SearchEngine.search([], 'test');
      expect(results).toEqual([]);
    });

    it('should handle nodes without labels', () => {
      const nodes: Node[] = [
        {
          id: '1',
          type: 'default',
          position: { x: 0, y: 0 },
          data: {},
        },
      ];

      const results = SearchEngine.search(nodes, 'test');
      expect(results).toEqual([]);
    });

    it('should handle nodes with null/undefined data', () => {
      const nodes: Node[] = [
        {
          id: '1',
          type: 'default',
          position: { x: 0, y: 0 },
          data: null as any,
        },
      ];

      expect(() => SearchEngine.search(nodes, 'test')).not.toThrow();
    });

    it('should handle very long queries', () => {
      const nodes = [createNode('1', 'Test')];
      const longQuery = 'a'.repeat(1000);

      expect(() => SearchEngine.search(nodes, longQuery)).not.toThrow();
    });

    it('should handle unicode characters', () => {
      const nodes = [
        createNode('1', '测试节点'),
        createNode('2', 'Test Node'),
      ];

      const results = SearchEngine.search(nodes, '测试');
      expect(results).toHaveLength(1);
      expect(results[0].node.id).toBe('1');
    });
  });
});

describe('SearchHistory', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe('add', () => {
    it('should add search query to history', () => {
      SearchHistory.add('test query');

      const history = SearchHistory.get();
      expect(history).toContain('test query');
    });

    it('should not add empty queries', () => {
      SearchHistory.add('');
      SearchHistory.add('   ');

      const history = SearchHistory.get();
      expect(history).toEqual([]);
    });

    it('should add new queries to the beginning', () => {
      SearchHistory.add('first');
      SearchHistory.add('second');

      const history = SearchHistory.get();
      expect(history[0]).toBe('second');
      expect(history[1]).toBe('first');
    });

    it('should remove duplicates', () => {
      SearchHistory.add('test');
      SearchHistory.add('other');
      SearchHistory.add('test');

      const history = SearchHistory.get();
      expect(history.filter(q => q === 'test')).toHaveLength(1);
      expect(history[0]).toBe('test');
    });

    it('should limit history to MAX_HISTORY items', () => {
      for (let i = 0; i < 15; i++) {
        SearchHistory.add(`query ${i}`);
      }

      const history = SearchHistory.get();
      expect(history.length).toBeLessThanOrEqual(10);
    });
  });

  describe('get', () => {
    it('should return empty array when no history', () => {
      const history = SearchHistory.get();
      expect(history).toEqual([]);
    });

    it('should return all history items', () => {
      SearchHistory.add('first');
      SearchHistory.add('second');
      SearchHistory.add('third');

      const history = SearchHistory.get();
      expect(history).toHaveLength(3);
    });

    it('should handle corrupted localStorage data', () => {
      localStorage.setItem('workflow_search_history', 'invalid json');

      const history = SearchHistory.get();
      expect(history).toEqual([]);
    });
  });

  describe('clear', () => {
    it('should clear all history', () => {
      SearchHistory.add('first');
      SearchHistory.add('second');

      SearchHistory.clear();

      const history = SearchHistory.get();
      expect(history).toEqual([]);
    });

    it('should handle clearing empty history', () => {
      expect(() => SearchHistory.clear()).not.toThrow();
    });
  });

  describe('persistence', () => {
    it('should persist across instances', () => {
      SearchHistory.add('test query');

      // Simulate new instance by reading from localStorage
      const stored = localStorage.getItem('workflow_search_history');
      expect(stored).toBeTruthy();

      const history = SearchHistory.get();
      expect(history).toContain('test query');
    });
  });
});
