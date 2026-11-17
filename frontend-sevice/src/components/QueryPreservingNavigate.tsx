// @AI_GENERATED
/**
 * 保留 query 的兼容重定向。
 *
 * 设计依据：design.md §33.2（每个兼容重定向必须保留 query string）；
 * requirements.md R1.8、R1.9、R2.3。React Router 的 <Navigate to="/x"> 会丢弃当前
 * location.search，导致跳转丢上下文（如 ?workflow_id= / ?scenario_id=）。本组件把
 * 当前 search 透传到目标路径。
 */

import { Navigate, useLocation } from 'react-router-dom';
import { appendSearch } from '../utils/journeyParams';

export interface QueryPreservingNavigateProps {
  to: string;
  replace?: boolean;
}

export function QueryPreservingNavigate({ to, replace = true }: QueryPreservingNavigateProps): JSX.Element {
  const location = useLocation();
  return <Navigate to={appendSearch(to, location.search)} replace={replace} />;
}

export default QueryPreservingNavigate;

// @AI_GENERATED: end
