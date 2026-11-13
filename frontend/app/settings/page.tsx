"use client";

import { useCallback, useEffect, useState } from "react";
import FileBrowser from "@/components/FileBrowser";
import Icon from "@/components/Icon";
import { Check } from "@/components/ParamForm";
import { api, type AiStatus, type PluginFile } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { openPath } from "@/lib/desktop";
import { nativePick } from "@/lib/pick";

function AiSettings() {
  const { settings, saveSettings, toast } = useApp();
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [key, setKey] = useState("");
  useEffect(() => { api<AiStatus>("GET", "/api/ai/status").then(setStatus).catch(() => {}); }, []);
  const save = async () => {
    try {
      setStatus(await api<AiStatus>("PUT", "/api/ai/key", { key }));
      setKey("");
      toast("API key saved on this computer.");
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  };
  if (!status || !settings) return null;
  return (
    <section className="card pad col" id="ai">
      <div className="row"><div className="h2 grow">AI assistant</div>
        {status.configured ? <span className="tag green">Connected · key {status.key_hint}</span> : <span className="tag">Not connected</span>}</div>
      <div className="muted">Optional. The AI designs workflows and writes plugin tools. It receives only your request text and OfficeFlow’s list of tools — never your files, file names, paths or history.</div>
      <div className="field">
        <label>Anthropic API key</label>
        <div className="row">
          <input className="input" type="password" autoComplete="off" value={key} placeholder={status.configured ? "Enter a new key to replace the saved one" : "sk-ant-…"}
            onChange={(e) => setKey(e.target.value)} />
          <button className="btn primary" disabled={!key.trim()} onClick={save}><Icon name="key" size={17} />Save</button>
          {status.configured && <button className="btn danger" onClick={async () => setStatus(await api<AiStatus>("DELETE", "/api/ai/key"))}><Icon name="trash" size={16} />Remove</button>}
        </div>
        <div className="help">Create one at console.anthropic.com. It is stored only on this computer (encrypted with your Windows account on Windows) and is never shown again.</div>
      </div>
      <div className="field">
        <label>Model</label>
        <select className="select" value={settings.ai_model} onChange={(e) => saveSettings({ ai_model: e.target.value })}>
          {Object.entries(status.models).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
      </div>
      <Check on={settings.ai_redact} label="Hide file paths and e-mail addresses in my requests automatically" onChange={(v) => saveSettings({ ai_redact: v })} />
    </section>
  );
}

function Plugins() {
  const { meta, refreshMeta, toast } = useApp();
  const [plugins, setPlugins] = useState<PluginFile[]>([]);
  const [viewing, setViewing] = useState<{ file: string; code: string } | null>(null);
  const load = useCallback(() => api<PluginFile[]>("GET", "/api/plugins").then(setPlugins).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  if (!meta) return null;
  return (
    <section className="card pad col">
      <div className="h2">Plugins</div>
      <div className="muted">Extra tools — written by the AI assistant or added by hand. Only install plugins from people you trust.</div>
      {meta.plugin_problems.map((p) => <div key={p} className="banner failed">{p}</div>)}
      {plugins.length === 0 && <div className="faint">No plugin installed.</div>}
      {plugins.map((plugin) => (
        <div key={plugin.file} className="plugin-row">
          <Icon name="code" size={18} />
          <div className="grow">
            <b>{plugin.file}</b>
            <div className="faint" style={{ fontSize: 12 }}>{plugin.loaded ? plugin.tools.map((t) => t.name).join(", ") : "Not loaded (see Logs)"}</div>
          </div>
          <button className="btn" onClick={async () => setViewing(await api("GET", `/api/plugins/${encodeURIComponent(plugin.file)}`))}><Icon name="eye" size={16} />Code</button>
          <button className="btn danger" onClick={async () => {
            if (!window.confirm(`Remove the plugin ${plugin.file}? Its tools disappear from OfficeFlow.`)) return;
            await api("DELETE", `/api/plugins/${encodeURIComponent(plugin.file)}`);
            toast(`${plugin.file} removed.`);
            load();
            refreshMeta();
          }}><Icon name="trash" size={16} />Remove</button>
        </div>
      ))}
      {viewing && (
        <div className="codeview selectable">
          {viewing.code.split("\n").map((line, i) => <div key={i} className="codeline"><span className="ln">{i + 1}</span><span>{line || " "}</span></div>)}
        </div>
      )}
      <div><button className="btn" onClick={() => openPath(`${meta.home}/plugins`)}><Icon name="folder" size={17} />Open plugin folder</button></div>
    </section>
  );
}

export default function SettingsPage() {
  const { settings, saveSettings, meta } = useApp();
  const [browsing, setBrowsing] = useState(false);
  if (!settings || !meta) return null;
  return (
    <div className="col" style={{ gap: 18, maxWidth: 820 }}>
      <h1 className="h1">Settings</h1>
      <section className="card pad col">
        <div className="h2">Appearance</div>
        <div className="row">
          {(["dark", "light"] as const).map((theme) => (
            <button key={theme} className={`themecard ${settings.theme === theme ? "on" : ""} ${theme}`} onClick={() => saveSettings({ theme })}>
              <span className="themeprev" />{theme === "dark" ? "Dark" : "Light"}
            </button>
          ))}
        </div>
      </section>
      <section className="card pad col">
        <div className="h2">Files</div>
        <div className="field">
          <label>Default output folder</label>
          <div className="row">
            <input className="input" value={settings.output_dir} onChange={(e) => saveSettings({ output_dir: e.target.value })} />
            <button className="btn" onClick={async () => {
              const picked = await nativePick("folder", [], settings.output_dir);
              if (picked === null) setBrowsing(true);
              else if (picked[0]) saveSettings({ output_dir: picked[0] });
            }}><Icon name="folder" size={17} />Browse</button>
          </div>
          <div className="help">Tools start with this folder; each tool lets you change it.</div>
        </div>
        <Check on={settings.include_subfolders} label="Include files in sub-folders by default" onChange={(v) => saveSettings({ include_subfolders: v })} />
      </section>
      <section className="card pad col">
        <div className="h2">Word to PDF</div>
        <div className="muted">{meta.pdf_converter ? `Conversions use ${meta.pdf_converter}.` : "No converter found. Install LibreOffice (free) or Microsoft Word to convert Word documents to PDF."}</div>
      </section>
      <AiSettings />
      <Plugins />
      <section className="card pad col">
        <div className="h2">About</div>
        <div>OfficeFlow {meta.version} — offline office automation</div>
        <div className="faint selectable" style={{ fontSize: 12 }}>Data folder: {meta.home}</div>
      </section>
      {browsing && <FileBrowser mode="folder" extensions={[]} start={settings.output_dir} onClose={() => setBrowsing(false)}
        onPick={(p) => { saveSettings({ output_dir: p[0] }); setBrowsing(false); }} />}
    </div>
  );
}
