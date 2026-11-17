import { ShortcutConfig, ShortcutCategory } from './KeyboardShortcutManager';

/**
 * 默认快捷键配置
 */
export const createDefaultShortcuts = (handlers: {
  // 编辑操作
  undo: () => void;
  redo: () => void;
  copy: () => void;
  cut: () => void;
  paste: () => void;
  duplicate: () => void;
  delete: () => void;
  selectAll: () => void;
  deselectAll: () => void;
  
  // 视图操作
  zoomIn: () => void;
  zoomOut: () => void;
  zoomToFit: () => void;
  zoomToActual: () => void;
  toggleGrid: () => void;
  toggleMinimap: () => void;
  
  // 文件操作
  save: () => void;
  saveAs: () => void;
  open: () => void;
  newWorkflow: () => void;
  
  // 算法模板操作
  run: () => void;
  stop: () => void;
  search: () => void;
  showHelp: () => void;
  
  // 导航操作
  moveUp: () => void;
  moveDown: () => void;
  moveLeft: () => void;
  moveRight: () => void;
}): ShortcutConfig[] => {
  return [
    // ========== 编辑操作 ==========
    {
      id: 'undo',
      key: 'z',
      ctrl: true,
      description: '撤销',
      category: ShortcutCategory.EDIT,
      handler: handlers.undo,
    },
    {
      id: 'redo',
      key: 'y',
      ctrl: true,
      description: '重做',
      category: ShortcutCategory.EDIT,
      handler: handlers.redo,
    },
    {
      id: 'redo-alt',
      key: 'z',
      ctrl: true,
      shift: true,
      description: '重做（备选）',
      category: ShortcutCategory.EDIT,
      handler: handlers.redo,
    },
    {
      id: 'copy',
      key: 'c',
      ctrl: true,
      description: '复制',
      category: ShortcutCategory.EDIT,
      handler: handlers.copy,
    },
    {
      id: 'cut',
      key: 'x',
      ctrl: true,
      description: '剪切',
      category: ShortcutCategory.EDIT,
      handler: handlers.cut,
    },
    {
      id: 'paste',
      key: 'v',
      ctrl: true,
      description: '粘贴',
      category: ShortcutCategory.EDIT,
      handler: handlers.paste,
    },
    {
      id: 'duplicate',
      key: 'd',
      ctrl: true,
      description: '复制',
      category: ShortcutCategory.EDIT,
      handler: handlers.duplicate,
    },
    {
      id: 'delete',
      key: 'Delete',
      description: '删除选中项',
      category: ShortcutCategory.EDIT,
      handler: handlers.delete,
    },
    {
      id: 'delete-alt',
      key: 'Backspace',
      description: '删除选中项（备选）',
      category: ShortcutCategory.EDIT,
      handler: handlers.delete,
    },

    // ========== 选择操作 ==========
    {
      id: 'select-all',
      key: 'a',
      ctrl: true,
      description: '全选',
      category: ShortcutCategory.SELECTION,
      handler: handlers.selectAll,
    },
    {
      id: 'deselect-all',
      key: 'Escape',
      description: '取消选择',
      category: ShortcutCategory.SELECTION,
      handler: handlers.deselectAll,
    },

    // ========== 视图操作 ==========
    {
      id: 'zoom-in',
      key: '=',
      ctrl: true,
      description: '放大',
      category: ShortcutCategory.VIEW,
      handler: handlers.zoomIn,
    },
    {
      id: 'zoom-out',
      key: '-',
      ctrl: true,
      description: '缩小',
      category: ShortcutCategory.VIEW,
      handler: handlers.zoomOut,
    },
    {
      id: 'zoom-to-fit',
      key: 'f',
      description: '适应视图',
      category: ShortcutCategory.VIEW,
      handler: handlers.zoomToFit,
    },
    {
      id: 'zoom-to-actual',
      key: '0',
      ctrl: true,
      description: '实际大小',
      category: ShortcutCategory.VIEW,
      handler: handlers.zoomToActual,
    },
    {
      id: 'toggle-grid',
      key: 'g',
      ctrl: true,
      description: '切换网格',
      category: ShortcutCategory.VIEW,
      handler: handlers.toggleGrid,
    },
    {
      id: 'toggle-minimap',
      key: 'm',
      ctrl: true,
      description: '切换小地图',
      category: ShortcutCategory.VIEW,
      handler: handlers.toggleMinimap,
    },

    // ========== 文件操作 ==========
    {
      id: 'save',
      key: 's',
      ctrl: true,
      description: '保存',
      category: ShortcutCategory.FILE,
      handler: handlers.save,
    },
    {
      id: 'save-as',
      key: 's',
      ctrl: true,
      shift: true,
      description: '另存为',
      category: ShortcutCategory.FILE,
      handler: handlers.saveAs,
    },
    {
      id: 'open',
      key: 'o',
      ctrl: true,
      description: '打开',
      category: ShortcutCategory.FILE,
      handler: handlers.open,
    },
    {
      id: 'new',
      key: 'n',
      ctrl: true,
      description: '新建算法模板',
      category: ShortcutCategory.FILE,
      handler: handlers.newWorkflow,
    },

    // ========== 算法模板操作 ==========
    {
      id: 'run',
      key: 'r',
      ctrl: true,
      description: '运行算法模板',
      category: ShortcutCategory.WORKFLOW,
      handler: handlers.run,
    },
    {
      id: 'stop',
      key: 'e',
      ctrl: true,
      description: '停止运行',
      category: ShortcutCategory.WORKFLOW,
      handler: handlers.stop,
    },
    {
      id: 'search',
      key: 'f',
      ctrl: true,
      description: '搜索',
      category: ShortcutCategory.WORKFLOW,
      handler: handlers.search,
    },
    {
      id: 'help',
      key: '?',
      description: '显示帮助',
      category: ShortcutCategory.WORKFLOW,
      handler: handlers.showHelp,
    },

    // ========== 导航操作 ==========
    {
      id: 'move-up',
      key: 'ArrowUp',
      description: '向上移动',
      category: ShortcutCategory.NAVIGATION,
      handler: handlers.moveUp,
    },
    {
      id: 'move-down',
      key: 'ArrowDown',
      description: '向下移动',
      category: ShortcutCategory.NAVIGATION,
      handler: handlers.moveDown,
    },
    {
      id: 'move-left',
      key: 'ArrowLeft',
      description: '向左移动',
      category: ShortcutCategory.NAVIGATION,
      handler: handlers.moveLeft,
    },
    {
      id: 'move-right',
      key: 'ArrowRight',
      description: '向右移动',
      category: ShortcutCategory.NAVIGATION,
      handler: handlers.moveRight,
    },
  ];
};
