// Frosted-glass folder with a sheet of paper peeking out (library cards).

export default function FolderGlyph({ label, tone = "grey", size = "md" }: { label?: string; tone?: "grey" | "green" | "amber" | "blue"; size?: "md" | "lg" }) {
  return (
    <div className={`fglyph tone-${tone} ${size}`} aria-hidden>
      <div className="fglyph-back" />
      <div className="fglyph-paper"><span /><span /><span /></div>
      <div className="fglyph-paper second" />
      <div className="fglyph-front">{label && <span className="fglyph-label">{label}</span>}</div>
    </div>
  );
}
