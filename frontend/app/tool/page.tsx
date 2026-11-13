"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Icon from "@/components/Icon";
import InputList from "@/components/InputList";
import ParamForm, { defaults } from "@/components/ParamForm";
import RunPanel from "@/components/RunPanel";
import { useApp } from "@/lib/app-context";
import { formats } from "@/lib/formats";
import { useJob } from "@/lib/useJob";

function Tool() {
  const { op: find, settings, meta } = useApp();
  const router = useRouter();
  const id = useSearchParams().get("id") ?? "";
  const op = find(id);
  const [inputs, setInputs] = useState<string[]>([]);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [outputDir, setOutputDir] = useState("");
  const [recursive, setRecursive] = useState(true);
  const { job, error, start, cancel, setError } = useJob();

  useEffect(() => {
    if (op) setValues(defaults(op.params));
  }, [op]);
  useEffect(() => {
    if (settings) {
      setOutputDir((d) => d || settings.output_dir);
      setRecursive(settings.include_subfolders);
    }
  }, [settings]);

  if (!meta) return null;
  if (!op) return <div className="banner failed">Unknown tool “{id}”.</div>;

  const body = (mode: string) => ({ mode, op: op.id, inputs, params: values, output_dir: outputDir, recursive });
  const go = (mode: "preview" | "run") => {
    if (!inputs.length) return setError("Add at least one file or folder first (step 1).");
    if (mode === "run" && values.move && !window.confirm("The original files will be removed from their folders after being copied. Continue?")) return;
    start(body(mode), op.name);
  };

  return (
    <div className="col" style={{ gap: 18 }}>
      <div className="row">
        <button className="btn" onClick={() => router.back()}><Icon name="back" size={17} />Back</button>
      </div>
      <div>
        <div className="row" style={{ gap: 14 }}>
          <span className={`tile big cat-${op.category}`}><Icon name={op.category} size={26} /></span>
          <div>
            <h1 className="h1">{op.name}</h1>
            <div className="fmt" style={{ marginTop: 4 }}>Reads <b>{formats(op.input_extensions)}</b><Icon name="forward" size={14} />Writes <b>{formats(op.output_extensions)}</b></div>
          </div>
        </div>
        <div className="muted" style={{ marginTop: 10, maxWidth: 900 }}>{op.description}</div>
      </div>
      <div className="toolpage">
        <div className="col" style={{ gap: 18, minWidth: 0 }}>
          <div className="card pad">
            <InputList title={`1 · ${op.input_label}`} extensions={op.input_extensions} value={inputs} onChange={setInputs} />
          </div>
          <div className="card pad">
            <div className="h2" style={{ marginBottom: 14 }}>3 · Preview and run</div>
            <RunPanel outputDir={outputDir} onOutputDir={setOutputDir} recursive={recursive} onRecursive={setRecursive}
              onPreview={() => go("preview")} onRun={() => go("run")} onCancel={cancel} job={job} error={error} />
          </div>
        </div>
        <div className="card pad" style={{ alignSelf: "start" }}>
          <div className="h2" style={{ marginBottom: 16 }}>2 · Settings</div>
          <ParamForm params={op.params} values={values} onChange={setValues} />
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <Suspense><Tool /></Suspense>;
}
