import { Node } from 'reactflow';

/**
 * 搜索结果
 */
export interface SearchResult {
  node: Node;
  score: number;
  matches: SearchMatch[];
}

/**
 * 搜索匹配
 */
export interface SearchMatch {
  field: string;
  value: string;
  indices: [number, number][];
}

/**
 * 搜索引擎
 */
export class SearchEngine {
  /**
   * 全文搜索
   */
  static search(nodes: Node[], query: string): SearchResult[] {
    if (!query.trim()) {
      return [];
    }

    const lowerQuery = query.toLowerCase();
    const results: SearchResult[] = [];

    nodes.forEach(node => {
      const matches: SearchMatch[] = [];
      let score = 0;

      // 搜索节点ID
      if (node.id.toLowerCase().includes(lowerQuery)) {
        matches.push({
          field: 'id',
          value: node.id,
          indices: this.findIndices(node.id.toLowerCase(), lowerQuery),
        });
        score += 10;
      }

      // 搜索节点标签
      const label = node.data?.label || '';
      if (label.toLowerCase().includes(lowerQuery)) {
        matches.push({
          field: 'label',
          value: label,
          indices: this.findIndices(label.toLowerCase(), lowerQuery),
        });
        score += 20;
      }

      // 搜索节点类型
      if (node.type?.toLowerCase().includes(lowerQuery)) {
        matches.push({
          field: 'type',
          value: node.type,
          indices: this.findIndices(node.type.toLowerCase(), lowerQuery),
        });
        score += 5;
      }

      // 搜索节点数据
      const dataStr = JSON.stringify(node.data).toLowerCase();
      if (dataStr.includes(lowerQuery)) {
        matches.push({
          field: 'data',
          value: JSON.stringify(node.data),
          indices: this.findIndices(dataStr, lowerQuery),
        });
        score += 3;
      }

      if (matches.length > 0) {
        results.push({ node, score, matches });
      }
    });

    // 按分数排序
    return results.sort((a, b) => b.score - a.score);
  }

  /**
   * 模糊搜索
   */
  static fuzzySearch(nodes: Node[], query: string): SearchResult[] {
    if (!query.trim()) {
      return [];
    }

    const results: SearchResult[] = [];

    nodes.forEach(node => {
      const label = node.data?.label || '';
      const score = this.fuzzyMatch(label.toLowerCase(), query.toLowerCase());

      if (score > 0) {
        results.push({
          node,
          score,
          matches: [{
            field: 'label',
            value: label,
            indices: [],
          }],
        });
      }
    });

    return results.sort((a, b) => b.score - a.score);
  }

  /**
   * 查找所有匹配位置
   */
  private static findIndices(text: string, query: string): [number, number][] {
    const indices: [number, number][] = [];
    let index = text.indexOf(query);

    while (index !== -1) {
      indices.push([index, index + query.length]);
      index = text.indexOf(query, index + 1);
    }

    return indices;
  }

  /**
   * 模糊匹配算法（Levenshtein距离）
   */
  private static fuzzyMatch(text: string, query: string): number {
    if (text.includes(query)) {
      return 100;
    }

    const distance = this.levenshteinDistance(text, query);
    const maxLength = Math.max(text.length, query.length);
    const similarity = (1 - distance / maxLength) * 100;

    return similarity > 50 ? similarity : 0;
  }

  /**
   * 计算Levenshtein距离
   */
  private static levenshteinDistance(a: string, b: string): number {
    const matrix: number[][] = [];

    for (let i = 0; i <= b.length; i++) {
      matrix[i] = [i];
    }

    for (let j = 0; j <= a.length; j++) {
      matrix[0][j] = j;
    }

    for (let i = 1; i <= b.length; i++) {
      for (let j = 1; j <= a.length; j++) {
        if (b.charAt(i - 1) === a.charAt(j - 1)) {
          matrix[i][j] = matrix[i - 1][j - 1];
        } else {
          matrix[i][j] = Math.min(
            matrix[i - 1][j - 1] + 1,
            matrix[i][j - 1] + 1,
            matrix[i - 1][j] + 1
          );
        }
      }
    }

    return matrix[b.length][a.length];
  }
}

/**
 * 搜索历史管理
 */
export class SearchHistory {
  private static readonly MAX_HISTORY = 10;
  private static readonly STORAGE_KEY = 'workflow_search_history';

  /**
   * 添加搜索历史
   */
  static add(query: string): void {
    if (!query.trim()) return;

    const history = this.get();
    const filtered = history.filter(q => q !== query);
    filtered.unshift(query);

    const limited = filtered.slice(0, this.MAX_HISTORY);
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(limited));
  }

  /**
   * 获取搜索历史
   */
  static get(): string[] {
    try {
      const stored = localStorage.getItem(this.STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  }

  /**
   * 清空搜索历史
   */
  static clear(): void {
    localStorage.removeItem(this.STORAGE_KEY);
  }
}
