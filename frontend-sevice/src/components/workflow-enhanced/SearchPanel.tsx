import React, { useState, useEffect, useRef } from 'react';
import { Node } from 'reactflow';
import { SearchEngine, SearchResult, SearchHistory } from '../../utils/search/SearchEngine';
import { FilterEngine, FilterCondition } from '../../utils/search/FilterEngine';
import './SearchPanel.css';

interface SearchPanelProps {
  isOpen: boolean;
  onClose: () => void;
  nodes: Node[];
  onSelectNode: (nodeId: string) => void;
  onHighlightNodes: (nodeIds: string[]) => void;
}

export const SearchPanel: React.FC<SearchPanelProps> = ({
  isOpen,
  onClose,
  nodes,
  onSelectNode,
  onHighlightNodes,
}) => {
  const [query, setQuery] = useState('');
  const [searchMode, setSearchMode] = useState<'exact' | 'fuzzy'>('exact');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<FilterCondition>({
    type: [],
    status: [],
    tags: [],
  });
  const inputRef = useRef<HTMLInputElement>(null);

  // 获取可用的过滤选项
  const availableTypes = FilterEngine.getNodeTypes(nodes);
  const availableStatuses = FilterEngine.getNodeStatuses(nodes);
  const availableTags = FilterEngine.getAllTags(nodes);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
      setHistory(SearchHistory.get());
    }
  }, [isOpen]);

  useEffect(() => {
    if (query.trim()) {
      performSearch();
    } else {
      setResults([]);
      onHighlightNodes([]);
    }
  }, [query, searchMode, filters, nodes]);

  const performSearch = () => {
    // 先应用过滤器
    const filteredNodes = FilterEngine.filter(nodes, filters);

    // 然后搜索
    const searchResults = searchMode === 'exact'
      ? SearchEngine.search(filteredNodes, query)
      : SearchEngine.fuzzySearch(filteredNodes, query);

    setResults(searchResults);

    // 高亮搜索结果
    const nodeIds = searchResults.map(r => r.node.id);
    onHighlightNodes(nodeIds);
  };

  const handleSearch = (searchQuery: string) => {
    setQuery(searchQuery);
    if (searchQuery.trim()) {
      SearchHistory.add(searchQuery);
      setHistory(SearchHistory.get());
    }
  };

  const handleSelectResult = (result: SearchResult) => {
    onSelectNode(result.node.id);
  };

  const handleClearHistory = () => {
    SearchHistory.clear();
    setHistory([]);
  };

  const toggleFilter = (filterType: keyof FilterCondition, value: string) => {
    setFilters(prev => {
      const current = prev[filterType] || [];
      const updated = current.includes(value)
        ? current.filter(v => v !== value)
        : [...current, value];
      return { ...prev, [filterType]: updated };
    });
  };

  const clearFilters = () => {
    setFilters({ type: [], status: [], tags: [] });
  };

  const hasActiveFilters = 
    (filters.type?.length || 0) + 
    (filters.status?.length || 0) + 
    (filters.tags?.length || 0) > 0;

  if (!isOpen) return null;

  return (
    <div className="search-panel">
      <div className="search-panel-header">
        <h3>🔍 搜索节点</h3>
        <button className="search-panel-close" onClick={onClose}>×</button>
      </div>

      <div className="search-panel-input-wrapper">
        <input
          ref={inputRef}
          type="text"
          className="search-panel-input"
          placeholder="搜索节点..."
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
        />
        <div className="search-panel-mode">
          <button
            className={`search-mode-btn ${searchMode === 'exact' ? 'active' : ''}`}
            onClick={() => setSearchMode('exact')}
          >
            精确
          </button>
          <button
            className={`search-mode-btn ${searchMode === 'fuzzy' ? 'active' : ''}`}
            onClick={() => setSearchMode('fuzzy')}
          >
            模糊
          </button>
        </div>
      </div>

      <div className="search-panel-toolbar">
        <button
          className={`search-filter-btn ${showFilters ? 'active' : ''}`}
          onClick={() => setShowFilters(!showFilters)}
        >
          🎯 过滤器 {hasActiveFilters && `(${(filters.type?.length || 0) + (filters.status?.length || 0) + (filters.tags?.length || 0)})`}
        </button>
        {hasActiveFilters && (
          <button className="search-clear-filters-btn" onClick={clearFilters}>
            清除过滤器
          </button>
        )}
      </div>

      {showFilters && (
        <div className="search-panel-filters">
          {availableTypes.length > 0 && (
            <div className="search-filter-group">
              <label>节点类型</label>
              <div className="search-filter-options">
                {availableTypes.map(type => (
                  <button
                    key={type}
                    className={`search-filter-option ${filters.type?.includes(type) ? 'active' : ''}`}
                    onClick={() => toggleFilter('type', type)}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>
          )}

          {availableStatuses.length > 0 && (
            <div className="search-filter-group">
              <label>节点状态</label>
              <div className="search-filter-options">
                {availableStatuses.map(status => (
                  <button
                    key={status}
                    className={`search-filter-option ${filters.status?.includes(status) ? 'active' : ''}`}
                    onClick={() => toggleFilter('status', status)}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>
          )}

          {availableTags.length > 0 && (
            <div className="search-filter-group">
              <label>标签</label>
              <div className="search-filter-options">
                {availableTags.map(tag => (
                  <button
                    key={tag}
                    className={`search-filter-option ${filters.tags?.includes(tag) ? 'active' : ''}`}
                    onClick={() => toggleFilter('tags', tag)}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="search-panel-content">
        {query.trim() ? (
          <>
            {results.length > 0 ? (
              <div className="search-results">
                <div className="search-results-header">
                  找到 {results.length} 个结果
                </div>
                {results.map((result, index) => (
                  <div
                    key={result.node.id}
                    className="search-result-item"
                    onClick={() => handleSelectResult(result)}
                  >
                    <div className="search-result-header">
                      <span className="search-result-label">
                        {result.node.data?.label || result.node.id}
                      </span>
                      <span className="search-result-score">
                        {Math.round(result.score)}
                      </span>
                    </div>
                    <div className="search-result-meta">
                      <span className="search-result-type">{result.node.type || 'default'}</span>
                      <span className="search-result-id">{result.node.id}</span>
                    </div>
                    {result.matches.length > 0 && (
                      <div className="search-result-matches">
                        {result.matches.map((match, i) => (
                          <span key={i} className="search-result-match">
                            {match.field}: {match.value.substring(0, 50)}
                            {match.value.length > 50 && '...'}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="search-empty">
                <p>未找到匹配的节点</p>
              </div>
            )}
          </>
        ) : (
          <div className="search-history">
            {history.length > 0 ? (
              <>
                <div className="search-history-header">
                  <span>搜索历史</span>
                  <button onClick={handleClearHistory}>清空</button>
                </div>
                {history.map((item, index) => (
                  <div
                    key={index}
                    className="search-history-item"
                    onClick={() => handleSearch(item)}
                  >
                    <span>🕐</span>
                    <span>{item}</span>
                  </div>
                ))}
              </>
            ) : (
              <div className="search-empty">
                <p>开始搜索节点...</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
