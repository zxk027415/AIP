// @AI_GENERATED: Kiro v1.0
import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Typography, Tag, Space, Breadcrumb, Row, Col,
  Button, Grid, Input, Statistic, Empty,
} from 'antd';
import {
  SearchOutlined,
  FunctionOutlined,
  AppstoreOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { BASIC_MODULE_CATEGORIES } from '../data/basicModuleCategories';
import BASIC_MODULE_FUNCTIONS from '../data/basicModuleFunctions';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end

const { Title, Paragraph, Text } = Typography;
const { useBreakpoint } = Grid;
const CHINESE_CHAR_RE = /[\u4e00-\u9fff]/;

const humanizeIdentifier = (value: string): string =>
  value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b[a-z]/g, (ch) => ch.toUpperCase());



const BasicModuleCategoryPage: React.FC = () => {
  const { categoryId } = useParams<{ categoryId: string }>();
  const navigate = useNavigate();
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end

  const [searchText, setSearchText] = useState('');

  const displayText = (text: string | null | undefined, fallbackId?: string): string => {
    const original = String(text ?? '');
    const translated = td(original);
    if ((i18n.language || '').toLowerCase().startsWith('zh')) return original;
    if (!translated || CHINESE_CHAR_RE.test(translated)) {
      return humanizeIdentifier(fallbackId || original);
    }
    return translated;
  };

  const category = useMemo(
    () => BASIC_MODULE_CATEGORIES.find(c => c.id === categoryId),
    [categoryId],
  );

  const subCategories = useMemo(
    () => (categoryId ? BASIC_MODULE_FUNCTIONS[categoryId] : undefined),
    [categoryId],
  );

  const filteredSubCategories = useMemo(() => {
    if (!subCategories) return [];
    if (!searchText.trim()) return subCategories;
    const kw = searchText.trim().toLowerCase();
    return subCategories
      .map(sc => ({
        ...sc,
        functions: sc.functions.filter(
          fn =>
            fn.name.toLowerCase().includes(kw) ||
            fn.id.toLowerCase().includes(kw) ||
            fn.description.toLowerCase().includes(kw) ||
            displayText(fn.name, fn.id).toLowerCase().includes(kw) ||
            displayText(fn.description, `${fn.id}_desc`).toLowerCase().includes(kw),
        ),
      }))
      .filter(sc => sc.functions.length > 0);
  }, [subCategories, searchText]);

  const totalFunctions = useMemo(
    () => subCategories?.reduce((s, sc) => s + sc.functions.length, 0) ?? 0,
    [subCategories],
  );

  const filteredCount = useMemo(
    () => filteredSubCategories.reduce((s, sc) => s + sc.functions.length, 0),
    [filteredSubCategories],
  );

  if (!category || !subCategories) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Empty description={t('basicModule.categoryNotFound')} />
        <Button type="primary" onClick={() => navigate('/basic-modules')} style={{ marginTop: 16 }}>
          {t('basicModule.backToOverview')}
        </Button>
      </div>
    );
  }

  return (
    <div style={{ padding: isMobile ? '12px' : '24px', height: '100%', overflow: 'auto' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Breadcrumb
          items={[
            { title: <a onClick={() => navigate('/basic-modules')}>{t('basicModule.basicAlgorithmLibrary')}</a> },
            { title: displayText(category.name, category.id) },
          ]}
        />

        {/* 分类头部卡片 */}
        <Card style={{ borderTop: `4px solid ${category.layerColor}` }}>
          <Row align="middle" gutter={16}>
            <Col>
              <div style={{ fontSize: '48px' }}>{category.icon}</div>
            </Col>
            <Col flex="auto">
              <Title level={isMobile ? 4 : 3} style={{ marginBottom: 4, marginTop: 0 }}>
                {displayText(category.name, category.id)}
              </Title>
              <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                {displayText(category.description, `${category.id}_desc`)}
              </Paragraph>
              <Space wrap>
                <Tag color={category.layerColor}>{displayText(category.layer, category.layer)}</Tag>
                <Tag icon={<FunctionOutlined />}>{totalFunctions} {t('basicModule.functionsUnit')}</Tag>
                <Tag icon={<AppstoreOutlined />}>{subCategories.length} {t('basicModule.subCategoriesUnit')}</Tag>
              </Space>
            </Col>
          </Row>
        </Card>

        {/* 统计栏 */}
        <Row gutter={[16, 16]}>
          <Col xs={8}>
            <Card size="small">
              <Statistic
                title={t('basicModule.totalFunctions')}
                value={totalFunctions}
                suffix={t('basicModule.unit')}
                valueStyle={{ color: category.layerColor }}
                prefix={<FunctionOutlined />}
              />
            </Card>
          </Col>
          <Col xs={8}>
            <Card size="small">
              <Statistic
                title={t('basicModule.subCategories')}
                value={subCategories.length}
                suffix={t('basicModule.unit')}
                valueStyle={{ color: '#1890ff' }}
                prefix={<AppstoreOutlined />}
              />
            </Card>
          </Col>
          <Col xs={8}>
            <Card size="small">
              <Statistic
                title={t('basicModule.techLayer')}
                value={displayText(category.layer, category.layer)}
                valueStyle={{ color: category.layerColor, fontSize: '16px' }}
              />
            </Card>
          </Col>
        </Row>

        {/* 搜索 */}
        <Input
          placeholder={t('basicModule.searchPlaceholder')}
          prefix={<SearchOutlined />}
          allowClear
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          style={{ maxWidth: 400 }}
        />
        {searchText.trim() && (
          <Text type="secondary">
            {t('basicModule.searchResult', { filtered: filteredCount, total: totalFunctions })}
          </Text>
        )}

        {/* 子分类函数列表 */}
        {filteredSubCategories.map((sc) => {
          const color = category.layerColor;
          return (
            <Card
              key={sc.subCategory}
              size="small"
              title={
                <span>
                  {category.icon} {displayText(sc.subCategory)}
                </span>
              }
              style={{ marginBottom: 4 }}
              extra={<Tag color={color}>{sc.functions.length} {t('basicModule.functionsUnit')}</Tag>}
            >
              <Row gutter={[8, 8]}>
                {sc.functions.map(fn => (
                  <Col xs={24} sm={12} md={8} key={fn.id}>
                    <Card
                      size="small"
                      hoverable
                      style={{ borderLeft: `3px solid ${color}` }}
                    >
                      <Text strong>{displayText(fn.name, fn.id)}</Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: '12px' }}>
                        {fn.id}
                      </Text>
                      <Paragraph
                        type="secondary"
                        ellipsis={{ rows: 1 }}
                        style={{ fontSize: '12px', marginBottom: 8, marginTop: 4 }}
                      >
                        {displayText(fn.description, `${fn.id}_desc`)}
                      </Paragraph>
                      <Space>
                        <Button
                          size="small"
                          type="primary"
                          icon={<RocketOutlined />}
                          onClick={e => {
                            e.stopPropagation();
                            navigate('/workflow/editor');
                          }}
                        >
                          {t('basicModule.addToTemplate')}
                        </Button>
                        <Button
                          size="small"
                          onClick={e => {
                            e.stopPropagation();
                            navigate('/functions');
                          }}
                        >
                          {t('basicModule.details')}
                        </Button>
                      </Space>
                    </Card>
                  </Col>
                ))}
              </Row>
            </Card>
          );
        })}

        {filteredSubCategories.length === 0 && searchText.trim() && (
          <Empty description={t('basicModule.noMatchingFunctions')} />
        )}
      </Space>
    </div>
  );
};

export default BasicModuleCategoryPage;
// @AI_GENERATED: end