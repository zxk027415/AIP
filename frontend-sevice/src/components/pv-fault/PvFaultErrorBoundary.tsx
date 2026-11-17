import React from 'react';
import { Alert, Button } from 'antd';

interface PvFaultErrorBoundaryProps {
  children: React.ReactNode;
  title?: string;
}

interface PvFaultErrorBoundaryState {
  error: Error | null;
}

/**
 * 光伏工作区错误边界：捕获渲染崩溃，避免整页白屏，并展示可读错误信息。
 */
export default class PvFaultErrorBoundary extends React.Component<
  PvFaultErrorBoundaryProps,
  PvFaultErrorBoundaryState
> {
  state: PvFaultErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): PvFaultErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('[PvFaultErrorBoundary]', error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <Alert
        type="error"
        showIcon
        style={{ margin: 16 }}
        message={this.props.title || '光伏页面渲染失败'}
        description={(
          <div>
            <pre style={{ whiteSpace: 'pre-wrap', marginBottom: 12, fontSize: 12 }}>
              {error.message}
              {error.stack ? `\n\n${error.stack}` : ''}
            </pre>
            <Button
              size="small"
              onClick={() => {
                this.setState({ error: null });
                window.location.reload();
              }}
            >
              重新加载
            </Button>
          </div>
        )}
      />
    );
  }
}
