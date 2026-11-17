import { useState, useEffect } from 'react';
import {
  Card,
  Tree,
  Input,
  Descriptions,
  Empty,
  Spin,
  message,
  Typography,
  Space,
  Tag,
  Drawer,
  Button,
  Grid,
  Divider,
  Tabs,
} from 'antd';
import type { DataNode } from 'antd/es/tree';
import { SearchOutlined, FunctionOutlined, MenuOutlined, CloseOutlined } from '@ant-design/icons';
import { functionApi } from '../services/api';
import type { FunctionDefinition, Category } from '../types/function';
import FunctionExecutor from './FunctionExecutor';
import { td } from '../utils/dataTranslation';

const { Search } = Input;
const { Title, Text, Paragraph } = Typography;
const { useBreakpoint } = Grid;

interface FunctionLibraryProps {
  onFunctionSelect?: (func: FunctionDefinition) => void;
  onFunctionDragStart?: (func: FunctionDefinition) => void;
}

/**
 * AI算法库浏览器组件
 * 
 * 功能：
 * - 分类树形展示
 * - 函数搜索
 * - 函数详情展示
 * - 函数拖拽支持
 * - 响应式布局（桌面、平板、移动端）
 */
const FunctionLibrary: React.FC<FunctionLibraryProps> = ({
  onFunctionSelect,
  onFunctionDragStart,
}) => {
  const [categories, setCategories] = useState<Category[]>([]);
  const [functions, setFunctions] = useState<FunctionDefinition[]>([]);
  const [filteredFunctions, setFilteredFunctions] = useState<FunctionDefinition[]>([]);
  const [selectedFunction, setSelectedFunction] = useState<FunctionDefinition | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  
  // 响应式状态
  const screens = useBreakpoint();
  const [categoryDrawerVisible, setCategoryDrawerVisible] = useState(false);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  
  // 判断是否为移动端或平板
  // Ant Design 断点：xs: 0, sm: 576px, md: 768px, lg: 992px, xl: 1200px, xxl: 1600px
  const isMobile = !screens.md; // < 768px
  const isTablet = screens.md && !screens.lg; // 768px - 991px
  const isDesktop = screens.lg; // >= 992px (调整为更适合实际使用的断点)
  
  // 调试信息
  useEffect(() => {
    console.log('Breakpoints:', screens);
    console.log('isMobile:', isMobile, 'isTablet:', isTablet, 'isDesktop:', isDesktop);
    console.log('Window width:', window.innerWidth);
  }, [screens, isMobile, isTablet, isDesktop]);

  // 加载分类和函数
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [categoriesData, functionsData] = await Promise.all([
        functionApi.getCategories(),
        functionApi.getAllFunctions(),
      ]);
      setCategories(categoriesData as Category[]);
      setFunctions(functionsData as FunctionDefinition[]);
      setFilteredFunctions(functionsData as FunctionDefinition[]);
      
      // 自动选择第一个分类和第一个函数
      if (categoriesData.length > 0 && functionsData.length > 0) {
        const firstCategory = categoriesData[0] as Category;
        const firstCategoryFunctions = (functionsData as FunctionDefinition[]).filter(
          f => f.category === firstCategory.id
        );
        
        // 设置选中的分类
        setSelectedCategory(firstCategory.id);
        
        // 过滤并显示第一个分类的函数
        setFilteredFunctions(firstCategoryFunctions);
        
        // 选择第一个函数
        if (firstCategoryFunctions.length > 0) {
          setSelectedFunction(firstCategoryFunctions[0]);
          if (onFunctionSelect) {
            onFunctionSelect(firstCategoryFunctions[0]);
          }
        }
      }
    } catch (error) {
      message.error(td('加载AI算法库失败'));
      console.error('Failed to load function library:', error);
    } finally {
      setLoading(false);
    }
  };

  // 搜索函数
  const handleSearch = async (value: string) => {
    setSearchQuery(value);
    
    if (!value.trim()) {
      // 如果搜索为空，显示所有函数或选中分类的函数
      if (selectedCategory) {
        const filtered = functions.filter(f => f.category === selectedCategory);
        setFilteredFunctions(filtered);
      } else {
        setFilteredFunctions(functions);
      }
      return;
    }

    try {
      const results = await functionApi.searchFunctions(value, selectedCategory || undefined);
      setFilteredFunctions(results as FunctionDefinition[]);
    } catch (error) {
      message.error(td('搜索失败'));
      console.error('Search failed:', error);
    }
  };

  // 转换分类为树形数据
  const convertCategoriesToTreeData = (): DataNode[] => {
    return categories.map(category => ({
      title: category.name,
      key: category.id,
      icon: <FunctionOutlined />,
      children: category.subcategories?.map(sub => ({
        title: sub.name,
        key: sub.id,
        icon: <FunctionOutlined />,
      })),
    }));
  };

  // 选择分类
  const handleCategorySelect = (selectedKeys: React.Key[]) => {
    const categoryId = selectedKeys[0] as string;
    setSelectedCategory(categoryId);
    
    if (categoryId) {
      const filtered = functions.filter(f => f.category === categoryId);
      setFilteredFunctions(filtered);
    } else {
      setFilteredFunctions(functions);
    }
    
    // 清空搜索
    setSearchQuery('');
  };

  // 选择函数
  const handleFunctionClick = (func: FunctionDefinition) => {
    setSelectedFunction(func);
    onFunctionSelect?.(func);
    
    // 移动端自动打开详情抽屉
    if (isMobile) {
      setDetailDrawerVisible(true);
    }
  };

  // 拖拽开始
  const handleDragStart = (e: React.DragEvent, func: FunctionDefinition) => {
    console.log('Drag start:', func.id, func.name);
    // 设置拖拽数据，与 WorkflowCanvas 期望的格式匹配
    e.dataTransfer.setData('functionId', func.id);
    e.dataTransfer.setData('functionLabel', func.name);
    e.dataTransfer.effectAllowed = 'copy';
    onFunctionDragStart?.(func);
  };

  // 渲染函数列表项
  const renderFunctionItem = (func: FunctionDefinition) => (
    <div
      key={func.id}
      draggable={true}
      onDragStart={(e) => handleDragStart(e, func)}
      onClick={() => handleFunctionClick(func)}
      style={{
        padding: isMobile ? '12px' : '8px 12px',
        margin: '4px 0',
        cursor: 'grab',
        border: '1px solid #d9d9d9',
        borderRadius: '4px',
        backgroundColor: selectedFunction?.id === func.id ? '#e6f7ff' : '#fff',
        transition: 'all 0.3s',
        minHeight: isMobile ? '44px' : 'auto', // 移动端最小触摸目标
        userSelect: 'none', // 防止拖拽时选中文本
      }}
      onMouseEnter={(e) => {
        if (!isMobile) {
          e.currentTarget.style.borderColor = '#1890ff';
          e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
        }
      }}
      onMouseLeave={(e) => {
        if (!isMobile) {
          e.currentTarget.style.borderColor = '#d9d9d9';
          e.currentTarget.style.boxShadow = 'none';
        }
      }}
      onDragEnd={(e) => {
        e.currentTarget.style.cursor = 'grab';
      }}
    >
      <Space direction="vertical" size={0} style={{ width: '100%' }}>
        <Text strong style={{ fontSize: isMobile ? '14px' : '13px' }}>{func.name}</Text>
        <Text type="secondary" style={{ fontSize: isMobile ? '12px' : '12px' }}>
          {func.description.substring(0, isMobile ? 40 : 50)}
          {func.description.length > (isMobile ? 40 : 50) ? '...' : ''}
        </Text>
      </Space>
    </div>
  );

  // 渲染分类面板
  const renderCategoryPanel = () => (
    <Card 
      title={td('算法基础模块分类')} 
      size="small" 
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
      bodyStyle={{ flex: 1, overflow: 'auto', padding: '12px' }}
    >
      <Spin spinning={loading}>
        {categories.length > 0 ? (
          <Tree
            showIcon
            defaultExpandAll
            selectedKeys={selectedCategory ? [selectedCategory] : []}
            treeData={convertCategoriesToTreeData()}
            onSelect={handleCategorySelect}
          />
        ) : (
          <Empty description={td('暂无分类')} />
        )}
      </Spin>
    </Card>
  );

  // 渲染函数列表面板
  const renderFunctionListPanel = () => (
    <Card
      title={
        <Space>
          {isMobile && (
            <Button
              type="text"
              icon={<MenuOutlined />}
              onClick={() => setCategoryDrawerVisible(true)}
            />
          )}
          <span>{td('函数列表')}</span>
        </Space>
      }
      size="small"
      extra={<Text type="secondary">{filteredFunctions.length} {td('个')}</Text>}
      style={{ 
        height: '100%',
        display: 'flex', 
        flexDirection: 'column' 
      }}
      bodyStyle={{ 
        flex: 1, 
        overflow: 'auto', 
        padding: isMobile ? '8px' : '12px' 
      }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Search
          placeholder={td('搜索函数...')}
          allowClear
          prefix={<SearchOutlined />}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onSearch={handleSearch}
          size={isMobile ? 'large' : 'middle'}
        />
        
        <div style={{ 
          maxHeight: isMobile ? 'calc(100vh - 300px)' : 'calc(100vh - 400px)', 
          overflow: 'auto' 
        }}>
          {filteredFunctions.length > 0 ? (
            filteredFunctions.map(renderFunctionItem)
          ) : (
            <Empty description={td('未找到函数')} />
          )}
        </div>
      </Space>
    </Card>
  );

  // 渲染函数详情内容
  const renderFunctionDetail = () => {
    if (!selectedFunction) {
      return <Empty description={td('请选择一个函数查看详情')} />;
    }

    // 函数介绍标签页内容
    const renderFunctionInfo = () => (
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={isMobile ? 5 : 4}>{selectedFunction.name}</Title>
          <Paragraph style={{ fontSize: isMobile ? '13px' : '14px' }}>
            {selectedFunction.description}
          </Paragraph>
        </div>

        <Descriptions 
          title={td('基本信息')} 
          column={1} 
          bordered 
          size="small"
          labelStyle={{ fontSize: isMobile ? '12px' : '13px' }}
          contentStyle={{ fontSize: isMobile ? '12px' : '13px' }}
        >
          <Descriptions.Item label={td('函数ID')}>
            <Text code style={{ fontSize: isMobile ? '11px' : '12px' }}>
              {selectedFunction.id}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label={td('分类')}>
            <Tag color="blue">
              {categories.find(c => c.id === selectedFunction.category)?.name || selectedFunction.category}
            </Tag>
          </Descriptions.Item>
        </Descriptions>

        {/* 输入输出参数 */}
        <div>
          <Title level={5} style={{ fontSize: isMobile ? '14px' : '16px' }}>
            {td('输入/输出')}
          </Title>
          <Descriptions 
            column={1} 
            bordered 
            size="small"
            labelStyle={{ fontSize: isMobile ? '12px' : '13px' }}
            contentStyle={{ fontSize: isMobile ? '12px' : '13px' }}
          >
            {/* 输入参数 */}
            {selectedFunction.parameters.length > 0 ? (
              selectedFunction.parameters.map((param, index) => (
                <Descriptions.Item
                  key={`input-${index}`}
                  label={
                    <Space>
                      <Text strong>{param.name}</Text>
                      <Tag color="blue">{td('输入')}</Tag>
                    </Space>
                  }
                >
                  <Space direction="vertical" size={0}>
                    <Space>
                      <Text>{td('类型')}: <Tag>{param.type}</Tag></Text>
                      {param.required && <Tag color="red">{td('必需')}</Tag>}
                    </Space>
                    {param.description && (
                      <Text type="secondary" style={{ fontSize: isMobile ? '11px' : '12px' }}>
                        {param.description}
                      </Text>
                    )}
                  </Space>
                </Descriptions.Item>
              ))
            ) : (
              <Descriptions.Item label={<Text type="secondary">{td('输入')}</Text>}>
                <Text type="secondary">{td('无参数')}</Text>
              </Descriptions.Item>
            )}
            
            {/* 输出 */}
            <Descriptions.Item 
              label={
                <Space>
                  <Text strong>C</Text>
                  <Tag color="green">{td('输出')}</Tag>
                </Space>
              }
            >
              <Space direction="vertical" size={0}>
                <Space>
                  <Text>{td('类型')}: <Tag color="green">{selectedFunction.returnType || selectedFunction.return_type || 'ANY'}</Tag></Text>
                </Space>
                <Text type="secondary" style={{ fontSize: isMobile ? '11px' : '12px' }}>
                  {td('函数执行后返回的结果')}
                </Text>
              </Space>
            </Descriptions.Item>
          </Descriptions>
        </div>

        <div>
          <Title level={5} style={{ fontSize: isMobile ? '14px' : '16px' }}>
            {td('使用示例')}
          </Title>
          {selectedFunction.examples.length > 0 ? (
            <div style={{ 
              backgroundColor: '#f5f5f5', 
              padding: isMobile ? '8px' : '12px', 
              borderRadius: '4px',
              overflowX: 'auto'
            }}>
              {selectedFunction.examples.map((example, index) => (
                <pre key={index} style={{ 
                  margin: 0, 
                  fontFamily: 'monospace', 
                  fontSize: isMobile ? '11px' : '12px',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word'
                }}>
                  {example}
                </pre>
              ))}
            </div>
          ) : (
            <Text type="secondary">{td('暂无示例')}</Text>
          )}
        </div>
      </Space>
    );

    // 函数执行标签页内容
    const renderFunctionExecutor = () => (
      <FunctionExecutor functionDef={selectedFunction} isMobile={isMobile} />
    );

    // Tabs 配置
    const tabItems = [
      {
        key: 'executor',
        label: td('函数执行'),
        children: renderFunctionExecutor(),
      },
      {
        key: 'info',
        label: td('函数介绍'),
        children: renderFunctionInfo(),
      },
    ];

    return (
      <Tabs 
        defaultActiveKey="executor" 
        items={tabItems}
        size={isMobile ? 'small' : 'middle'}
      />
    );
  };

  // 桌面端布局
  if (isDesktop) {
    return (
      <div style={{ display: 'flex', height: '100%', gap: '16px' }}>
        {/* 左侧：AI算法库（包含分类树和函数列表） */}
        <Card
          title={<span style={{ fontSize: '16px', fontWeight: 'bold', color: '#1890ff' }}>{td('AI算法库')}</span>}
          size="small"
          style={{ width: '300px', display: 'flex', flexDirection: 'column' }}
          bodyStyle={{ flex: 1, overflow: 'hidden', padding: '12px', display: 'flex', flexDirection: 'column', gap: '16px' }}
        >
          {/* 分类树 - 固定高度 30% */}
          <div style={{ height: '30%', minHeight: '200px', maxHeight: '350px' }}>
            <div style={{ marginBottom: '8px', fontWeight: 'bold', fontSize: '13px' }}>{td('算法基础模块分类')}</div>
            <div style={{ height: 'calc(100% - 28px)', overflow: 'auto', border: '1px solid #f0f0f0', borderRadius: '4px', padding: '8px' }}>
              <Spin spinning={loading}>
                {categories.length > 0 ? (
                  <Tree
                    showIcon
                    defaultExpandAll
                    selectedKeys={selectedCategory ? [selectedCategory] : []}
                    treeData={convertCategoriesToTreeData()}
                    onSelect={handleCategorySelect}
                  />
                ) : (
                  <Empty description={td('暂无分类')} />
                )}
              </Spin>
            </div>
          </div>
          
          {/* 函数列表 - 占据剩余空间 70% */}
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ marginBottom: '8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 'bold', fontSize: '13px' }}>{td('函数列表')}</span>
              <Text type="secondary" style={{ fontSize: '12px' }}>
                {filteredFunctions.length} {td('个')}
              </Text>
            </div>
            <Search
              placeholder={td('搜索函数...')}
              allowClear
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              style={{ marginBottom: '12px' }}
              size="small"
            />
            <div style={{ flex: 1, overflow: 'auto', border: '1px solid #f0f0f0', borderRadius: '4px', padding: '8px' }}>
              <Spin spinning={loading}>
                {filteredFunctions.length > 0 ? (
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    {filteredFunctions.map(func => renderFunctionItem(func))}
                  </Space>
                ) : (
                  <Empty description={td('未找到函数')} />
                )}
              </Spin>
            </div>
          </div>
        </Card>

        {/* 右侧：函数应用 */}
        <Card
          title={
            <span style={{ fontSize: '16px', fontWeight: 'bold', color: '#1890ff' }}>
              {selectedFunction ? (
                <>
                  {td(categories.find(c => c.id === selectedFunction.category)?.name || '未分类')}
                  <span style={{ margin: '0 8px' }}>&gt;</span>
                  {selectedFunction.name}
                </>
              ) : (
                td('函数应用')
              )}
            </span>
          }
          size="small"
          style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
          bodyStyle={{ flex: 1, overflow: 'auto', padding: '16px' }}
        >
          {renderFunctionDetail()}
        </Card>
      </div>
    );
  }

  // 平板端布局
  if (isTablet) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '16px' }}>
        {/* 上部：分类和函数列表 */}
        <div style={{ display: 'flex', gap: '16px', height: '50%' }}>
          <div style={{ width: '200px' }}>
            {renderCategoryPanel()}
          </div>
          <div style={{ flex: 1 }}>
            {renderFunctionListPanel()}
          </div>
        </div>

        {/* 下部：函数详情 */}
        <Card
          title={td('函数详情')}
          size="small"
          style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
          bodyStyle={{ flex: 1, overflow: 'auto', padding: '16px' }}
        >
          {renderFunctionDetail()}
        </Card>
      </div>
    );
  }

  // 移动端布局
  return (
    <div style={{ height: '100%' }}>
      {/* 主内容：函数列表 */}
      {renderFunctionListPanel()}

      {/* 分类抽屉 */}
      <Drawer
        title={td('算法基础模块分类')}
        placement="left"
        onClose={() => setCategoryDrawerVisible(false)}
        open={categoryDrawerVisible}
        width="80%"
      >
        <Spin spinning={loading}>
          {categories.length > 0 ? (
            <Tree
              showIcon
              defaultExpandAll
              treeData={convertCategoriesToTreeData()}
              onSelect={(keys) => {
                handleCategorySelect(keys);
                setCategoryDrawerVisible(false);
              }}
            />
          ) : (
            <Empty description={td('暂无分类')} />
          )}
        </Spin>
      </Drawer>

      {/* 详情抽屉 */}
      <Drawer
        title={
          <Space>
            <span>{td('函数详情')}</span>
            <Button
              type="text"
              size="small"
              icon={<CloseOutlined />}
              onClick={() => setDetailDrawerVisible(false)}
            />
          </Space>
        }
        placement="right"
        onClose={() => setDetailDrawerVisible(false)}
        open={detailDrawerVisible}
        width="90%"
        closeIcon={null}
      >
        {renderFunctionDetail()}
      </Drawer>
    </div>
  );
};

export default FunctionLibrary;
