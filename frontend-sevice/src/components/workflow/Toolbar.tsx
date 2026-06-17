import React, { useEffect } from 'react';
import { Button, Space, Tooltip, Divider, Modal, Input } from 'antd';
import {
  SaveOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  ExportOutlined,
  UndoOutlined,
  RedoOutlined,
  PlusOutlined,
  FileTextOutlined,
} from '@ant-design/icons';
import { useWorkflowStore } from '../../stores/workflowStore';
import { useExecutionStore } from '../../stores/executionStore';
import { useUIStore } from '../../stores/uiStore';
import './Toolbar.css';

interface ToolbarProps {
  onNew?: () => void;
  onLoad?: () => void;
  onExport?: () => void;
  onValidate?: () => void;
}

const Toolbar: React.FC<ToolbarProps> = ({
  onNew,
  onLoad,
  onExport,
  onValidate,
}) => {
  const { currentWorkflow, isDirty, saveWorkflow, createNewWorkflow } = useWorkflowStore();
  const { executeWorkflow, isExecuting } = useExecutionStore();
  const { canUndo, canRedo, undo, redo } = useUIStore();

  const [isNewModalVisible, setIsNewModalVisible] = React.useState(false);
  const [newWorkflowName, setNewWorkflowName] = React.useState('');
  const [newWorkflowDescription, setNewWorkflowDescription] = React.useState('');

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+S or Cmd+S: Save
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
      // Ctrl+Z or Cmd+Z: Undo
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      }
      // Ctrl+Shift+Z or Cmd+Shift+Z: Redo
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'z') {
        e.preventDefault();
        handleRedo();
      }
      // Ctrl+N or Cmd+N: New
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        handleNew();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentWorkflow]);

  const handleNew = () => {
    if (isDirty) {
      Modal.confirm({
        title: '未保存的更改',
        content: '当前模板有未保存的更改，是否继续创建新模板？',
        onOk: () => setIsNewModalVisible(true),
      });
    } else {
      setIsNewModalVisible(true);
    }
  };

  const handleCreateNew = () => {
    if (!newWorkflowName.trim()) {
      return;
    }
    createNewWorkflow(newWorkflowName, newWorkflowDescription);
    setIsNewModalVisible(false);
    setNewWorkflowName('');
    setNewWorkflowDescription('');
    if (onNew) onNew();
  };

  const handleSave = async () => {
    if (!currentWorkflow) return;
    try {
      await saveWorkflow();
    } catch (error) {
      console.error('Save failed:', error);
    }
  };

  const handleLoad = () => {
    if (isDirty) {
      Modal.confirm({
        title: '未保存的更改',
        content: '当前模板有未保存的更改，是否继续加载？',
        onOk: () => {
          if (onLoad) onLoad();
        },
      });
    } else {
      if (onLoad) onLoad();
    }
  };

  const handleExecute = async () => {
    if (!currentWorkflow?.id) {
      Modal.warning({
        title: '无法执行',
        content: '请先保存模板后再执行',
      });
      return;
    }

    // Validate first if callback provided
    if (onValidate) {
      onValidate();
    }

    try {
      await executeWorkflow(currentWorkflow.id);
    } catch (error) {
      console.error('Execution failed:', error);
    }
  };

  const handleUndo = () => {
    const previousWorkflow = undo();
    if (previousWorkflow) {
      useWorkflowStore.getState().setWorkflow(previousWorkflow);
    }
  };

  const handleRedo = () => {
    const nextWorkflow = redo();
    if (nextWorkflow) {
      useWorkflowStore.getState().setWorkflow(nextWorkflow);
    }
  };

  const handleExport = () => {
    if (!currentWorkflow) return;
    
    const dataStr = JSON.stringify(currentWorkflow, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${currentWorkflow.name || 'workflow'}.json`;
    link.click();
    URL.revokeObjectURL(url);

    if (onExport) onExport();
  };

  return (
    <>
      <div className="workflow-toolbar">
        <Space split={<Divider type="vertical" />}>
          {/* File operations */}
          <Space>
            <Tooltip title="新建算法模板 (Ctrl+N)">
              <Button
                icon={<PlusOutlined />}
                onClick={handleNew}
              >
                新建
              </Button>
            </Tooltip>
            <Tooltip title="保存算法模板 (Ctrl+S)">
              <Button
                icon={<SaveOutlined />}
                onClick={handleSave}
                disabled={!currentWorkflow || !isDirty}
                type={isDirty ? 'primary' : 'default'}
              >
                保存
              </Button>
            </Tooltip>
            <Tooltip title="加载算法模板">
              <Button
                icon={<FolderOpenOutlined />}
                onClick={handleLoad}
              >
                加载
              </Button>
            </Tooltip>
          </Space>

          {/* Edit operations */}
          <Space>
            <Tooltip title="撤销 (Ctrl+Z)">
              <Button
                icon={<UndoOutlined />}
                onClick={handleUndo}
                disabled={!canUndo()}
              />
            </Tooltip>
            <Tooltip title="重做 (Ctrl+Shift+Z)">
              <Button
                icon={<RedoOutlined />}
                onClick={handleRedo}
                disabled={!canRedo()}
              />
            </Tooltip>
          </Space>

          {/* Execution */}
          <Space>
            <Tooltip title="执行算法模板">
              <Button
                icon={<PlayCircleOutlined />}
                onClick={handleExecute}
                disabled={!currentWorkflow || isExecuting}
                type="primary"
                loading={isExecuting}
              >
                执行
              </Button>
            </Tooltip>
            <Tooltip title="验证算法模板">
              <Button
                icon={<FileTextOutlined />}
                onClick={onValidate}
                disabled={!currentWorkflow}
              >
                验证
              </Button>
            </Tooltip>
          </Space>

          {/* Export */}
          <Space>
            <Tooltip title="导出为JSON">
              <Button
                icon={<ExportOutlined />}
                onClick={handleExport}
                disabled={!currentWorkflow}
              >
                导出
              </Button>
            </Tooltip>
          </Space>
        </Space>

        {/* Workflow info */}
        {currentWorkflow && (
          <div className="workflow-info">
            <span className="workflow-name">{currentWorkflow.name}</span>
            {isDirty && <span className="dirty-indicator">●</span>}
          </div>
        )}
      </div>

      {/* New Workflow Modal */}
      <Modal
        title="创建新算法模板"
        open={isNewModalVisible}
        onOk={handleCreateNew}
        onCancel={() => setIsNewModalVisible(false)}
        okText="创建"
        cancelText="取消"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <label>算法模板名称 *</label>
            <Input
              placeholder="请输入算法模板名称"
              value={newWorkflowName}
              onChange={(e) => setNewWorkflowName(e.target.value)}
            />
          </div>
          <div>
            <label>描述</label>
            <Input.TextArea
              placeholder="请输入算法模板描述"
              value={newWorkflowDescription}
              onChange={(e) => setNewWorkflowDescription(e.target.value)}
              rows={3}
            />
          </div>
        </Space>
      </Modal>
    </>
  );
};

export default Toolbar;
