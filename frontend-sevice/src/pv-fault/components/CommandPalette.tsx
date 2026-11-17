// @AI_GENERATED
/**
 * 命令面板（design §35；任务 10.7）。
 *
 * Ctrl/Cmd + K 打开；快速跳转到最近项目、当前项目的各阶段、以及返回项目列表。
 * 数据来自 journeyContextStore（recents / lastHref）；不做任何写入，只导航。
 * 键盘可达：输入过滤 + ↑↓ 选择 + Enter 跳转 + Esc 关闭。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Empty, Input, Modal, Tag, Typography } from 'antd';
import type { InputRef } from 'antd';
import { useJourneyContextStore } from '../../stores/journeyContextStore';

const { Text } = Typography;

export interface CommandItem {
  key: string;
  label: string;
  hint?: string;
  href: string;
  group: string;
}

export interface CommandPaletteProps {
  /** 当前项目 id（存在时提供阶段跳转项）。 */
  projectId?: string;
  /** 当前项目的阶段列表（label + routeSegment）。 */
  stages?: Array<{ label: string; segment: string }>;
}

export function CommandPalette({ projectId, stages }: CommandPaletteProps): JSX.Element {
  const navigate = useNavigate();
  const recents = useJourneyContextStore((s) => s.recents);
  const lastHref = useJourneyContextStore((s) => s.lastHref);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<InputRef>(null);

  // Ctrl/Cmd + K 开关。
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIdx(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const commands = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = [];
    if (lastHref) {
      items.push({ key: 'continue-last', label: '继续上次', hint: lastHref, href: lastHref, group: '快捷' });
    }
    items.push({ key: 'project-list', label: '项目列表', href: '/projects', group: '快捷' });
    if (projectId && stages) {
      stages.forEach((st) =>
        items.push({
          key: `stage-${st.segment}`,
          label: `当前项目 · ${st.label}`,
          href: `/projects/${projectId}/${st.segment}`,
          group: '当前项目阶段',
        }),
      );
    }
    recents.forEach((r) =>
      items.push({ key: `recent-${r.kind}-${r.id}`, label: r.label, hint: r.kind, href: r.href, group: '最近访问' }),
    );
    return items;
  }, [lastHref, projectId, stages, recents]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q) || (c.hint || '').toLowerCase().includes(q));
  }, [commands, query]);

  const go = useCallback(
    (href: string) => {
      setOpen(false);
      navigate(href);
    },
    [navigate],
  );

  const onInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const target = filtered[activeIdx];
      if (target) go(target.href);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={() => setOpen(false)}
      footer={null}
      closable={false}
      destroyOnClose
      styles={{ body: { padding: 12 } }}
      title={null}
    >
      <Input
        ref={inputRef}
        placeholder="跳转到项目 / 阶段…（↑↓ 选择，Enter 跳转，Esc 关闭）"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActiveIdx(0);
        }}
        onKeyDown={onInputKeyDown}
        aria-label="命令面板搜索"
        allowClear
      />
      <div style={{ marginTop: 8, maxHeight: 360, overflow: 'auto' }} role="listbox" aria-label="命令列表">
        {filtered.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无匹配项" />
        ) : (
          filtered.map((c, idx) => (
            <div
              key={c.key}
              role="option"
              aria-selected={idx === activeIdx}
              onMouseEnter={() => setActiveIdx(idx)}
              onClick={() => go(c.href)}
              style={{
                padding: '8px 10px',
                borderRadius: 6,
                cursor: 'pointer',
                background: idx === activeIdx ? '#fff7e6' : 'transparent',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span>
                <Text>{c.label}</Text>
                {c.hint && (
                  <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                    {c.hint}
                  </Text>
                )}
              </span>
              <Tag color="default" style={{ marginInlineEnd: 0 }}>
                {c.group}
              </Tag>
            </div>
          ))
        )}
      </div>
    </Modal>
  );
}

export default CommandPalette;
// @AI_GENERATED: end
