"use client";

import { motion } from "framer-motion";
import Icon from "./Icon";
import type { Operation, TargetStat } from "@/lib/api";
import { formats } from "@/lib/formats";

export default function ToolCard({ op, stat, onClick, index = 0 }: { op: Operation; stat?: TargetStat; onClick(): void; index?: number }) {
  return (
    <motion.button className={`toolcard cat-${op.category}`} onClick={onClick}
      initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.03, type: "spring", stiffness: 300, damping: 28 }}
      whileHover={{ y: -4 }}>
      <div className="row">
        <span className="tile"><Icon name={op.category} size={22} /></span>
        <div className="grow" />
        {stat ? <span className="tag">{stat.runs} run{stat.runs > 1 ? "s" : ""}</span> : <Icon name="arrow" size={18} className="faint" />}
      </div>
      <div className="h2" style={{ textAlign: "left" }}>{op.name}</div>
      <div className="muted toolcard-desc">{op.description}</div>
      <div className="fmt"><b>{formats(op.input_extensions)}</b><Icon name="forward" size={14} /><b>{formats(op.output_extensions)}</b></div>
    </motion.button>
  );
}
