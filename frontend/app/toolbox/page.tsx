"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import ToolCard from "@/components/ToolCard";
import { useApp } from "@/lib/app-context";

const INTRO: Record<string, string> = {
  excel: "Merge, clean, split, compare and convert Excel and CSV files — one file or whole folders.",
  pdf: "Organise, rename, split, merge and search large collections of PDF documents.",
  word: "Generate documents from Excel, replace text, merge, format and convert Word documents.",
};

function Toolbox() {
  const { meta, stats } = useApp();
  const router = useRouter();
  const category = useSearchParams().get("cat") ?? "excel";
  if (!meta) return null;
  const operations = meta.operations.filter((o) => o.category === category);
  return (
    <div className="col" style={{ gap: 22 }}>
      <div>
        <h1 className="h1">{meta.categories[category] ?? category} Toolbox</h1>
        <div className="muted" style={{ marginTop: 6 }}>{INTRO[category]}</div>
      </div>
      <div className="toolgrid">
        {operations.map((op, i) => (
          <ToolCard key={op.id} op={op} index={i} stat={stats?.targets[op.id]} onClick={() => router.push(`/tool/?id=${op.id}`)} />
        ))}
      </div>
    </div>
  );
}

export default function Page() {
  return <Suspense><Toolbox /></Suspense>;
}
