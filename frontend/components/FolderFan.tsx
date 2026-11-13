"use client";

// 3D stack of glass folders — one per tool. The geometry is a tiny perspective
// camera (same model as the reference design: folders standing in a row, the
// middle ones seen edge-on); each folder is ordinary HTML/SVG mapped onto its
// projected quadrilateral with a CSS matrix3d, so text stays crisp.

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "./Icon";

export interface FanItem {
  id: string;
  title: string;
  caption: string;
  stat: string;
  icon: string;
}

const LW = 320;
const LH = 250;
const DEPTH = 1.0;
const HEIGHT = 0.8;
const SPACING = 0.24;
const CAMERA_Y = 1.15;
const DISTANCE = 3.1;
const YAW = 0.3;
const FAN = 0.08;
const OPEN = 0.4;

type P = { x: number; y: number };

/** CSS matrix3d mapping an LW×LH element onto the quad (tl, tr, br, bl). */
function quadMatrix([p0, p1, p2, p3]: P[]): string {
  const dx1 = p1.x - p2.x, dx2 = p3.x - p2.x, dx3 = p0.x - p1.x + p2.x - p3.x;
  const dy1 = p1.y - p2.y, dy2 = p3.y - p2.y, dy3 = p0.y - p1.y + p2.y - p3.y;
  let g = 0, h = 0;
  if (Math.abs(dx3) > 1e-9 || Math.abs(dy3) > 1e-9) {
    const det = dx1 * dy2 - dx2 * dy1;
    g = (dx3 * dy2 - dx2 * dy3) / det;
    h = (dx1 * dy3 - dx3 * dy1) / det;
  }
  const a = p1.x - p0.x + g * p1.x, b = p3.x - p0.x + h * p3.x, c = p0.x;
  const d = p1.y - p0.y + g * p1.y, e = p3.y - p0.y + h * p3.y, f = p0.y;
  return `matrix3d(${a / LW},${d / LW},0,${g / LW},${b / LH},${e / LH},0,${h / LH},0,0,1,0,${c},${f},0,1)`;
}

interface Card {
  index: number;
  quad: P[];
  nearLeft: boolean;
  depth: number;
}

function layout(count: number, lift: number[], width: number, height: number): Card[] {
  const centre = (count - 1) / 2;
  const raw = [];
  for (let i = 0; i < count; i++) {
    const u = (i - centre) / (centre || 1);
    let push = 0;
    for (let j = 0; j < count; j++) if (j !== i) push += (i > j ? 0.16 : -0.16) * lift[j];
    const x = (i - centre) * SPACING + push;
    const l = lift[i];
    const z = DISTANCE + x * Math.tan(YAW) - 0.22 * l;
    const side = u <= 0 ? -1 : 1;
    const opening = OPEN + 0.55 * (1 - Math.min(Math.abs(u) * 2.5, 1));
    const angle = -FAN * Math.sign(u) * Math.abs(u) ** 0.8 - side * opening * l;
    const dx = Math.sin(angle) * DEPTH, dz = Math.cos(angle) * DEPTH;
    const y0 = 0.1 * l, y1 = HEIGHT * (1 + 0.1 * l) + 0.1 * l;
    const project = (px: number, py: number, pz: number): P => ({ x: px / pz, y: (CAMERA_Y - py) / pz });
    raw.push({
      i, x,
      pts: [project(x, y1, z), project(x + dx, y1, z + dz), project(x + dx, y0, z + dz), project(x, y0, z)],
    });
  }
  const xs = raw.flatMap((r) => r.pts.map((p) => p.x));
  const ys = raw.flatMap((r) => r.pts.map((p) => p.y));
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const top = 70, bottom = 16, margin = 24;
  const scale = Math.min((width - 2 * margin) / (maxX - minX), (height - top - bottom) / (maxY - minY));
  const ox = (width - (maxX - minX) * scale) / 2 - minX * scale;
  const oy = top + (height - top - bottom - (maxY - minY) * scale) / 2 - minY * scale;
  return raw.map(({ i, x, pts }) => {
    const [nt, ft, fb, nb] = pts.map((p) => ({ x: p.x * scale + ox, y: p.y * scale + oy }));
    const nearLeft = nt.x <= ft.x;
    return { index: i, nearLeft, depth: Math.abs(x), quad: nearLeft ? [nt, ft, fb, nb] : [ft, nt, nb, fb] };
  });
}

function FolderArt({ item, selected, nearLeft, fade }: { item: FanItem; selected: boolean; nearLeft: boolean; fade: number }) {
  const tab = nearLeft ? [14, 128] : [LW - 128, LW - 14];
  const back = `M0 52 Q0 34 18 34 L${tab[0]} 34 C${tab[0] + 8} 34 ${tab[0] + 6} 6 ${tab[0] + 24} 6 L${tab[1] - 24} 6 C${tab[1] - 6} 6 ${tab[1] - 8} 34 ${tab[1]} 34 L${LW - 18} 34 Q${LW} 34 ${LW} 52 L${LW} ${LH - 18} Q${LW} ${LH} ${LW - 18} ${LH} L18 ${LH} Q0 ${LH} 0 ${LH - 18} Z`;
  const top = 112, dip = 26;
  const front = nearLeft
    ? `M0 ${top + 18} Q0 ${top} 18 ${top} L${LW * 0.42} ${top} C${LW * 0.55} ${top} ${LW * 0.52} ${top + dip} ${LW * 0.66} ${top + dip} L${LW - 18} ${top + dip} Q${LW} ${top + dip} ${LW} ${top + dip + 18} L${LW} ${LH - 18} Q${LW} ${LH} ${LW - 18} ${LH} L18 ${LH} Q0 ${LH} 0 ${LH - 18} Z`
    : `M0 ${top + dip + 18} Q0 ${top + dip} 18 ${top + dip} L${LW * 0.34} ${top + dip} C${LW * 0.48} ${top + dip} ${LW * 0.45} ${top} ${LW * 0.58} ${top} L${LW - 18} ${top} Q${LW} ${top} ${LW} ${top + 18} L${LW} ${LH - 18} Q${LW} ${LH} ${LW - 18} ${LH} L18 ${LH} Q0 ${LH} 0 ${LH - 18} Z`;
  const id = `f${item.id.replace(/\W/g, "")}`;
  const papers = [0, 1].map((k) => (nearLeft ? 34 + k * 26 : LW - 34 - k * 26 - 210));
  return (
    <svg width={LW} height={LH} viewBox={`0 0 ${LW} ${LH}`} style={{ overflow: "visible", display: "block" }}>
      <defs>
        <linearGradient id={`${id}b`} x1="0" y1="0" x2="0" y2="1">
          {selected ? (<><stop offset="0" stopColor="#2ea058" /><stop offset="1" stopColor="#147038" /></>) : (
            <><stop offset="0" stopColor="var(--fan-back-top)" stopOpacity={0.65 * fade} />
              <stop offset="0.45" stopColor="var(--fan-back-top)" stopOpacity={0.22 * fade} />
              <stop offset="1" stopColor="var(--fan-back-top)" stopOpacity={0.03 * fade} /></>)}
        </linearGradient>
        <linearGradient id={`${id}f`} x1="0" y1="0" x2={selected ? 1 : 0} y2="1">
          {selected ? (<><stop offset="0" stopColor="#68e78e" /><stop offset="1" stopColor="#34ac62" /></>) : (
            <><stop offset="0" stopColor="var(--fan-front)" stopOpacity={0.8 * fade} />
              <stop offset="0.5" stopColor="var(--fan-front)" stopOpacity={0.38 * fade} />
              <stop offset="1" stopColor="var(--fan-front)" stopOpacity={0.08 * fade} /></>)}
        </linearGradient>
      </defs>
      <path d={back} fill={`url(#${id}b)`} stroke={selected ? "#bfffd2" : "var(--fan-stroke)"} strokeOpacity={selected ? 0.9 : fade} strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
      {papers.map((x, k) => (
        <g key={k}>
          <rect x={x} y={46 - k * 8 + (k ? 0 : 6)} width="210" height="120" rx="10" fill="#fff" fillOpacity={(selected ? 0.92 : 0.6) * fade} />
          {[150, 110, 135, 90].map((w, r) => (
            <rect key={r} x={x + 18} y={46 - k * 8 + (k ? 0 : 6) + 18 + r * 16} width={w} height="7" rx="3.5" fill="#000b1a" fillOpacity={0.16 * fade} />
          ))}
        </g>
      ))}
      <path d={front} fill={`url(#${id}f)`} stroke={selected ? "#bfffd2" : "var(--fan-stroke)"} strokeOpacity={selected ? 0.9 : fade} strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
      <foreignObject x="20" y={top + 36} width={LW - 40} height={LH - top - 44}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: nearLeft ? "flex-start" : "flex-end", height: "100%",
          justifyContent: "space-between", color: selected ? "#fff" : "var(--fan-ink)", opacity: selected ? 1 : 0.85 * fade }}>
          <Icon name={item.icon} size={30} />
          <div style={{ fontSize: 23, fontWeight: selected ? 700 : 600, whiteSpace: "nowrap", overflow: "hidden",
            textOverflow: "ellipsis", maxWidth: "100%", paddingBottom: 4 }}>{item.title}</div>
        </div>
      </foreignObject>
    </svg>
  );
}

export default function FolderFan({ items, selected, onSelect, onOpen }: {
  items: FanItem[]; selected: string; onSelect(id: string): void; onOpen(id: string): void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 1100, height: 400 });
  const index = Math.max(0, items.findIndex((i) => i.id === selected));
  const [lift, setLift] = useState<number[]>(() => items.map((_, i) => (i === index ? 1 : 0)));
  const liftRef = useRef(lift);

  useEffect(() => {
    if (!box.current) return;
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);

  // Spring the lift values towards the selection.
  useEffect(() => {
    if (liftRef.current.length !== items.length) liftRef.current = items.map((_, i) => (i === index ? 1 : 0));
    let frame = 0;
    const step = () => {
      let moving = false;
      liftRef.current = liftRef.current.map((value, i) => {
        const target = i === index ? 1 : 0;
        const next = value + (target - value) * 0.22;
        if (Math.abs(target - next) > 0.004) { moving = true; return next; }
        return target;
      });
      setLift([...liftRef.current]);
      if (moving) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [index, items.length]);

  const cards = useMemo(
    () => (items.length && lift.length === items.length ? layout(items.length, lift, size.width, size.height) : []),
    [items.length, lift, size],
  );
  const order = useMemo(() => [...cards].sort((a, b) => b.depth - a.depth).sort((a, b) => Number(a.index === index) - Number(b.index === index)), [cards, index]);
  const maxDepth = SPACING * items.length / 2 + 0.3;

  const step = useCallback((delta: number) => {
    const next = Math.min(Math.max(index + delta, 0), items.length - 1);
    if (items[next]) onSelect(items[next].id);
  }, [index, items, onSelect]);

  const current = cards.find((c) => c.index === index);
  const item = items[index];
  let info: { left: number; top: number } | null = null;
  if (current) {
    const xs = current.quad.map((p) => p.x), ys = current.quad.map((p) => p.y);
    const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...ys), bottom = Math.max(...ys);
    const width = 210;
    let x = left - width + 34 > 12 ? left - width + 34 : right - 34;
    x = Math.max(12, Math.min(x, size.width - width - 12));
    info = { left: x, top: top + (bottom - top) * 0.22 };
  }

  return (
    <div ref={box} className="fan" tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") step(-1);
        if (e.key === "ArrowRight") step(1);
        if (e.key === "Enter" && item) onOpen(item.id);
      }}
      onWheel={(e) => step(e.deltaY > 0 || e.deltaX > 0 ? 1 : -1)}>
      <svg className="fan-arc" width="100%" height="120" preserveAspectRatio="none" viewBox="0 0 100 120">
        <defs>
          <linearGradient id="arc" x1="0" x2="1">
            <stop offset="0" stopColor="#68e78e" stopOpacity="0" />
            <stop offset=".5" stopColor="#68e78e" stopOpacity=".8" />
            <stop offset="1" stopColor="#68e78e" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d="M30 112 C40 28 60 28 70 112" fill="none" stroke="url(#arc)" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="fan-handle">
        <button onClick={() => step(-1)} title="Previous tool">‹</button>
        <button onClick={() => step(1)} title="Next tool">›</button>
      </div>
      <div className="fan-stage">
        {order.map((card) => {
          const fade = 1 - 0.45 * Math.min(card.depth / maxDepth, 1);
          return (
            <div key={items[card.index].id} className={`fan-card ${card.index === index ? "on" : ""}`}
              style={{ transform: quadMatrix(card.quad) }}
              onMouseEnter={() => onSelect(items[card.index].id)}
              onClick={() => onOpen(items[card.index].id)}>
              <FolderArt item={items[card.index]} selected={card.index === index} nearLeft={card.nearLeft} fade={fade} />
            </div>
          );
        })}
      </div>
      <AnimatePresence>
        {info && item && (
          <motion.div key="info" className="fan-info" initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1, left: info.left, top: info.top }} exit={{ opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }} onClick={() => onOpen(item.id)}>
            <div className="row" style={{ alignItems: "flex-start" }}>
              <div className="grow">
                <div className="fan-info-title ellipsis">{item.title}</div>
                <div className="fan-info-caption">{item.caption}</div>
              </div>
              <Icon name="arrow" size={16} />
            </div>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
              <motion.div key={item.stat + item.id} className="fan-info-stat" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>{item.stat}</motion.div>
              <span className="fan-info-dot" />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
