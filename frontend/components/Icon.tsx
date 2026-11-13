// Line icons (24×24, stroke = currentColor).

const PATHS: Record<string, string> = {
  home: "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  excel: "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM3 9h18M3 15h18M9 3v18",
  pdf: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5",
  word: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6",
  cross: "M4 7h13l-3-3M20 17H7l3 3",
  workflow: "M5 3h3a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM16 15h3a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-3a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2zM10 6h4a3 3 0 0 1 3 3v6",
  history: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
  logs: "M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01",
  settings: "M4 6h9M19 6h1M4 12h3M13 12h7M4 18h11M21 18h-1M16 3.8a2.2 2.2 0 1 1 0 4.4 2.2 2.2 0 0 1 0-4.4zM10 9.8a2.2 2.2 0 1 1 0 4.4 2.2 2.2 0 0 1 0-4.4zM18 15.8a2.2 2.2 0 1 1 0 4.4 2.2 2.2 0 0 1 0-4.4z",
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  play: "M8 5l11 7-11 7z",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z",
  back: "M19 12H5M11 6l-6 6 6 6",
  forward: "M5 12h14M13 6l6 6-6 6",
  arrow: "M7 17L17 7M9 7h8v8",
  stop: "M7 6h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z",
  trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
  up: "M6 15l6-6 6 6",
  down: "M6 9l6 6 6-6",
  save: "M5 3h11l3 3v15H5zM8 3v6h7V3M8 21v-7h8v7",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  search: "M11 4a7 7 0 1 1 0 14 7 7 0 0 1 0-14zM20 20l-4-4",
  menu: "M4 6h16M4 12h10M4 18h13",
  bell: "M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0",
  sun: "M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z",
  calendar: "M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM16 3v4M8 3v4M3 11h18",
  export: "M12 3v12M7 8l5-5 5 5M5 15v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4",
  tasks: "M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2",
  fit: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  tidy: "M4 6h16M4 12h10M4 18h13",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 15l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z",
  undo: "M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  redo: "M15 14l5-5-5-5M20 9H9.5a5.5 5.5 0 0 0 0 11H13",
  check: "M5 12.5l4.5 4.5L19 7",
  x: "M6 6l12 12M18 6L6 18",
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5",
  chevron: "M9 6l6 6-6 6",
  winmin: "M6 12h12",
  winmax: "M7 7h10v10H7z",
  winrestore: "M8 10h8v8H8zM10 7h7a1 1 0 0 1 1 1v7",
  question: "M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.5V14M12 17h.01",
  drag: "M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01",
};

export default function Icon({ name, size = 20, stroke = 1.7, className }: {
  name: string; size?: number; stroke?: number; className?: string;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke}
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d={PATHS[name] ?? PATHS.file} />
    </svg>
  );
}
