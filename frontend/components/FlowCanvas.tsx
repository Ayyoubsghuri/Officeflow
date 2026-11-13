"use client";

// Node canvas: dotted, pannable, zoomable; nodes are draggable cards joined by
// curved pink connectors with ring ports (the look of the reference design).

import { motion } from "framer-motion";
import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import Icon from "./Icon";

export const NODE_W = 320;
export const NODE_H = 136;
const GHOST_W = 210;
const GHOST_H = 64;
const STEP_X = 250;
const STEP_Y = 175;

export interface FlowNode {
  key: string;
  kind: string;                 // start | excel | pdf | word | cross
  icon: string;
  chip: string;
  chipLime?: boolean;
  status?: { label: string; tone: string };
  title: string;
  subtitle: string;
  inFormats?: string;           // undefined for the start node
  outFormats: string;
  warning?: string;
}

export interface CanvasHandle {
  fit(): void;
  tidy(): void;
}

type Point = { x: number; y: number };

export function defaultPosition(index: number): Point {
  return { x: index * STEP_X, y: (index % 2) * STEP_Y };
}

function edgePath(a: Point, aw: number, ah: number, b: Point, bh: number) {
  const end = { x: b.x, y: b.y + bh / 2 };
  if (b.x >= a.x + aw + 40) {
    const start = { x: a.x + aw, y: a.y + ah / 2 };
    const span = Math.max((end.x - start.x) / 2, 40);
    return { d: `M${start.x} ${start.y} C${start.x + span} ${start.y} ${end.x - span} ${end.y} ${end.x} ${end.y}`, start, end };
  }
  const below = end.y > a.y + ah / 2;
  const start = { x: a.x + aw * 0.4, y: below ? a.y + ah : a.y };
  return { d: `M${start.x} ${start.y} C${start.x} ${end.y} ${start.x + (end.x - start.x) * 0.25} ${end.y} ${end.x} ${end.y}`, start, end };
}

export default function FlowCanvas({ nodes, selected, broken, positions, onPositions, onSelect, onAdd, onInsert, onUndo, onRedo,
  canUndo, canRedo, handle }: {
  nodes: FlowNode[];
  selected: string;
  broken: Set<string>;
  positions: Record<string, Point>;
  onPositions(p: Record<string, Point>): void;
  onSelect(key: string): void;
  onAdd(screen: Point): void;
  onInsert(afterIndex: number, screen: Point): void;
  onUndo(): void;
  onRedo(): void;
  canUndo: boolean;
  canRedo: boolean;
  handle: Ref<CanvasHandle>;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ x: 80, y: 120, scale: 1 });
  const drag = useRef<{ kind: "pan" | "node"; key?: string; start: Point; origin: Point; moved: boolean } | null>(null);

  const pos = useCallback((key: string, index: number) => positions[key] ?? defaultPosition(index), [positions]);
  const placed = nodes.map((node, index) => ({ node, index, at: pos(node.key, index) }));
  const last = placed[placed.length - 1];
  const ghostAt = last
    ? { x: last.at.x + (defaultPosition(nodes.length).x - defaultPosition(nodes.length - 1).x),
        y: last.at.y + (defaultPosition(nodes.length).y - defaultPosition(nodes.length - 1).y) + (NODE_H - GHOST_H) / 2 }
    : { x: 0, y: 0 };

  const fit = useCallback(() => {
    const el = box.current;
    if (!el || !placed.length) return;
    const xs = [...placed.map((p) => p.at.x), ghostAt.x + GHOST_W, ...placed.map((p) => p.at.x + NODE_W)];
    const ys = [...placed.map((p) => p.at.y), ...placed.map((p) => p.at.y + NODE_H)];
    const area = { x: Math.min(...xs) - 90, y: Math.min(...ys) - 80, w: Math.max(...xs) - Math.min(...xs) + 180, h: Math.max(...ys) - Math.min(...ys) + 200 };
    const scale = Math.max(0.6, Math.min(1, el.clientWidth / area.w, el.clientHeight / area.h));
    const visible = el.clientWidth / scale;
    const cx = area.w <= visible ? area.x + area.w / 2 : area.x + visible / 2;
    setView({ scale, x: el.clientWidth / 2 - cx * scale, y: el.clientHeight / 2 - (area.y + area.h / 2) * scale + 10 });
  }, [placed, ghostAt.x]);

  useImperativeHandle(handle, () => ({
    fit,
    tidy: () => { onPositions({}); setTimeout(fit, 0); },
  }), [fit, onPositions]);

  // Re-frame the flow whenever steps are added or removed.
  useEffect(() => {
    const frame = requestAnimationFrame(() => fit());
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length]);

  const zoom = (factor: number, around?: Point) => {
    const el = box.current!;
    const c = around ?? { x: el.clientWidth / 2, y: el.clientHeight / 2 };
    setView((v) => {
      const scale = Math.max(0.35, Math.min(1.8, v.scale * factor));
      const k = scale / v.scale;
      return { scale, x: c.x - (c.x - v.x) * k, y: c.y - (c.y - v.y) * k };
    });
  };

  const onPointerDown = (e: React.PointerEvent, key?: string) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const index = key ? nodes.findIndex((n) => n.key === key) : -1;
    drag.current = key
      ? { kind: "node", key, start: { x: e.clientX, y: e.clientY }, origin: pos(key, index), moved: false }
      : { kind: "pan", start: { x: e.clientX, y: e.clientY }, origin: { x: view.x, y: view.y }, moved: false };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.start.x, dy = e.clientY - d.start.y;
    if (!d.moved && Math.hypot(dx, dy) < 4) return;
    d.moved = true;
    if (d.kind === "pan") setView((v) => ({ ...v, x: d.origin.x + dx, y: d.origin.y + dy }));
    else onPositions({ ...Object.fromEntries(nodes.map((n, i) => [n.key, pos(n.key, i)])), [d.key!]: { x: d.origin.x + dx / view.scale, y: d.origin.y + dy / view.scale } });
  };
  const onPointerUp = (key?: string) => {
    const d = drag.current;
    drag.current = null;
    if (d && !d.moved) onSelect(key ?? "");
  };

  const toScreen = (p: Point) => {
    const rect = box.current!.getBoundingClientRect();
    return { x: rect.left + view.x + p.x * view.scale, y: rect.top + view.y + p.y * view.scale };
  };

  const edges = placed.slice(1).map((target, i) => {
    const source = placed[i];
    return { key: target.node.key, index: i, ...edgePath(source.at, NODE_W, NODE_H, target.at, NODE_H), broken: broken.has(target.node.key) };
  });
  const ghostEdge = last ? edgePath(last.at, NODE_W, NODE_H, ghostAt, GHOST_H) : null;

  return (
    <div ref={box} className="flow" style={{ backgroundPosition: `${view.x}px ${view.y}px`, backgroundSize: `${24 * view.scale}px ${24 * view.scale}px` }}
      onPointerDown={(e) => onPointerDown(e)} onPointerMove={onPointerMove} onPointerUp={() => onPointerUp()}
      onWheel={(e) => { const r = box.current!.getBoundingClientRect(); zoom(e.deltaY < 0 ? 1.1 : 1 / 1.1, { x: e.clientX - r.left, y: e.clientY - r.top }); }}>
      <div className="flow-world" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}>
        <svg className="flow-edges" width="1" height="1">
          {edges.map((edge) => (
            <g key={edge.key}>
              <path d={edge.d} className={`flow-edge ${edge.broken ? "broken" : ""}`} />
              <circle cx={edge.start.x} cy={edge.start.y} r="6.5" className={`flow-port ${edge.broken ? "broken" : ""}`} />
              <circle cx={edge.end.x} cy={edge.end.y} r="6.5" className={`flow-port ${edge.broken ? "broken" : ""}`} />
            </g>
          ))}
          {ghostEdge && <g><path d={ghostEdge.d} className="flow-edge ghost" /><circle cx={ghostEdge.start.x} cy={ghostEdge.start.y} r="6.5" className="flow-port" /></g>}
        </svg>
        {edges.map((edge) => {
          const mid = { x: (edge.start.x + edge.end.x) / 2, y: (edge.start.y + edge.end.y) / 2 };
          return (
            <button key={`ins-${edge.key}`} className="flow-insert" style={{ left: mid.x - 13, top: mid.y - 13 }} title="Insert a step here"
              onPointerDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); onInsert(edge.index, toScreen(mid)); }}>
              <Icon name="plus" size={14} stroke={2.2} />
            </button>
          );
        })}
        {placed.map(({ node, at }) => (
          <motion.div key={node.key} className={`flow-node ${selected === node.key ? "selected" : ""} ${node.warning ? "warn" : ""}`}
            style={{ left: at.x, top: at.y, width: NODE_W, height: NODE_H }}
            initial={{ opacity: 0, scale: 0.92 }} animate={{ opacity: 1, scale: 1 }} transition={{ type: "spring", stiffness: 380, damping: 30 }}
            onPointerDown={(e) => onPointerDown(e, node.key)} onPointerMove={onPointerMove} onPointerUp={(e) => { e.stopPropagation(); onPointerUp(node.key); }}>
            <span className={`flow-tile kind-${node.kind}`}><Icon name={node.icon} size={28} /></span>
            <div className="flow-body">
              <div className="row" style={{ gap: 6 }}>
                <span className={`tag ${node.chipLime ? "lime" : ""}`}>{node.chip}</span>
                {node.status && <span className={`tag ${node.status.tone}`}>{node.status.label}</span>}
              </div>
              <div className="flow-title ellipsis">{node.title}</div>
              <div className={`flow-sub ellipsis ${node.warning ? "warn" : ""}`} title={node.warning || node.subtitle}>{node.warning || node.subtitle}</div>
              <div className="flow-formats">
                {node.inFormats !== undefined && <><span className="fmtpill">IN <b>{node.inFormats}</b></span><Icon name="forward" size={13} /></>}
                <span className="fmtpill out">OUT <b>{node.outFormats}</b></span>
              </div>
            </div>
          </motion.div>
        ))}
        {last && (
          <button className="flow-ghost" style={{ left: ghostAt.x, top: ghostAt.y, width: GHOST_W, height: GHOST_H }}
            onPointerDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); onAdd(toScreen({ x: ghostAt.x, y: ghostAt.y + GHOST_H + 8 })); }}>
            <Icon name="plus" size={17} /> Add step
          </button>
        )}
      </div>

      <div className="floatbar vertical" style={{ left: 18, top: 18 }} onPointerDown={(e) => e.stopPropagation()}>
        <button title="Fit the workflow in view" onClick={fit}><Icon name="fit" size={19} /></button>
        <button title="Zoom in" onClick={() => zoom(1.2)}><Icon name="plus" size={19} /></button>
        <button title="Zoom out" onClick={() => zoom(1 / 1.2)}><Icon name="minus" size={19} /></button>
      </div>
      <div className="floatbar vertical" style={{ left: 18, top: 174 }} onPointerDown={(e) => e.stopPropagation()}>
        <button title="Tidy up the layout" onClick={() => { onPositions({}); setTimeout(fit, 0); }}><Icon name="tidy" size={19} /></button>
      </div>
      <div className="floatbar bottom" onPointerDown={(e) => e.stopPropagation()}>
        <button className="create" onClick={(e) => { const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); onAdd({ x: r.left, y: r.top - 8 - 420 }); }}>
          <Icon name="sparkle" size={18} /> Add step
        </button>
        <span className="sep" />
        <button title="Undo (Ctrl+Z)" disabled={!canUndo} onClick={onUndo}><Icon name="undo" size={19} /></button>
        <button title="Redo (Ctrl+Shift+Z)" disabled={!canRedo} onClick={onRedo}><Icon name="redo" size={19} /></button>
      </div>
    </div>
  );
}
