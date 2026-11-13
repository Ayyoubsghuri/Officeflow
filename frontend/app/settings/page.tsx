"use client";

import { useCallback, useEffect, useState } from "react";
import FileBrowser from "@/components/FileBrowser";
import ErrorBoundary from "@/components/ErrorBoundary";
import Icon from "@/components/Icon";
import { Check } from "@/components/ParamForm";
import { motion } from "framer-motion";
import { api, type AiProvider, type AiStatus, type PluginFile } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { openPath } from "@/lib/desktop";
import { nativePick } from "@/lib/pick";

const KEY_HELP: Record<AiProvider, string> = {
  anthropic: "Create one at console.anthropic.com.",
  openai: "Create one at platform.openai.com → API keys.",
};

function AiSettings() {
  const { settings, saveSettings, toast } = useApp();
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [keys, setKeys] = useState<Record<AiProvider, string>>({ anthropic: "", openai: "" });
  const [openaiModels, setOpenaiModels] = useState<string[]>([]);
  const refresh = useCallback(() => api<AiStatus>("GET", "/api/ai/status").then(setStatus).catch(() => {}), []);
  useEffect(() => { refresh(); }, [refresh, settings?.ai_provider, settings?.ai_openai_model]);

  const loadModels = useCallback(async (quiet = false) => {
    try {
      setOpenaiModels((await api<{ models: string[] }>("GET", "/api/ai/models?provider=openai")).models);
    } catch (e) {
      if (!quiet) toast(e instanceof Error ? e.message : String(e), "error");
    }
  }, [toast]);
  useEffect(() => {
    if (status?.providers?.openai?.configured && settings?.ai_provider === "openai" && !openaiModels.length) loadModels(true);
  }, [status, settings?.ai_provider, openaiModels.length, loadModels]);

  const save = async (provider: AiProvider) => {
    try {
      setStatus(await api<AiStatus>("PUT", "/api/ai/key", { key: keys[provider], provider }));
      setKeys((k) => ({ ...k, [provider]: "" }));
      toast("API key saved on this computer.");
      if (provider === "openai") loadModels(true);
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  };
  if (!status || !settings) return null;
  const provider: AiProvider = settings.ai_provider === "openai" ? "openai" : "anthropic";
  const info = status.providers?.[provider];
  if (!info) {
    return (
      <section className="card pad col" id="ai">
        <div className="h2">AI assistant</div>
        <div className="banner warning">The OfficeFlow engine is older than this screen. Close every OfficeFlow window and start it again.</div>
      </section>
    );
  }
  return (
    <section className="card pad col" id="ai">
      <div className="row"><div className="h2 grow">AI assistant</div>
        {info.configured ? <span className="tag green">Connected · {info.label} · key {info.key_hint}</span> : <span className="tag">Not connected</span>}</div>
      <div className="muted">Optional. The AI designs workflows and writes plugin tools. It receives only your request text and OfficeFlow’s list of tools — never your files, file names, paths or history.</div>
      <div className="field">
        <label>Provider</label>
        <div className="segmented">
          {(Object.keys(status.providers) as AiProvider[]).map((name) => (
            <button key={name} className={provider === name ? "on" : ""} onClick={() => saveSettings({ ai_provider: name })}>
              <Icon name="sparkle" size={16} />{status.providers[name].label}
              {status.providers[name].configured && <span className="dot-ok" style={{ marginLeft: 4 }} />}
              {provider === name && <motion.span layoutId="provider-seg" className="seg-bg" />}
            </button>
          ))}
        </div>
      </div>
      <div className="field">
        <label>{info.label} API key</label>
        <div className="row">
          <input className="input" type="password" autoComplete="off" value={keys[provider]}
            placeholder={info.configured ? "Enter a new key to replace the saved one" : provider === "openai" ? "sk-…" : "sk-ant-…"}
            onChange={(e) => setKeys((k) => ({ ...k, [provider]: e.target.value }))} />
          <button className="btn primary" disabled={!keys[provider].trim()} onClick={() => save(provider)}><Icon name="key" size={17} />Save</button>
          {info.configured && <button className="btn danger" onClick={async () => setStatus(await api<AiStatus>("DELETE", `/api/ai/key?provider=${provider}`))}>
            <Icon name="trash" size={16} />Remove</button>}
        </div>
        <div className="help">{KEY_HELP[provider]} Keys are stored only on this computer (encrypted with your Windows account on Windows) and are never shown again. Each provider keeps its own key.</div>
        {!info.sdk && <div className="banner failed">The {info.label} library is not installed. Run: pip install -r requirements.txt</div>}
      </div>
      <div className="field">
        <label>Model</label>
        {provider === "anthropic" ? (
          <select className="select" value={settings.ai_model} onChange={(e) => saveSettings({ ai_model: e.target.value })}>
            {Object.entries(status.models).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        ) : (
          <>
            <div className="row">
              <select className="select" value={settings.ai_openai_model} onChange={(e) => saveSettings({ ai_openai_model: e.target.value })}>
                {[...new Set([settings.ai_openai_model, ...openaiModels])].map((id) => <option key={id} value={id}>{id}</option>)}
              </select>
              <button className="btn" disabled={!info.configured} onClick={() => loadModels()}><Icon name="refresh" size={16} />Load my models</button>
            </div>
            <div className="help">The list comes from your OpenAI account (only the list of model names is requested).</div>
          </>
        )}
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
  const { settings, meta, error } = useApp();
  if (!settings || !meta) {
    return (
      <div className="col" style={{ gap: 18, maxWidth: 820 }}>
        <h1 className="h1">Settings</h1>
        <div className={`banner ${error ? "failed" : ""}`}>{error ? `Settings could not be loaded: ${error}` : "Loading settings…"}</div>
      </div>
    );
  }
  // Each section is isolated: a problem in one never hides the others.
  return (
    <div className="col" style={{ gap: 18, maxWidth: 820 }}>
      <h1 className="h1">Settings</h1>
      <ErrorBoundary resetKey="general" label="General settings"><GeneralSettings /></ErrorBoundary>
      <ErrorBoundary resetKey="ai" label="AI assistant settings"><AiSettings /></ErrorBoundary>
      <ErrorBoundary resetKey="plugins" label="Plugins"><Plugins /></ErrorBoundary>
      <ErrorBoundary resetKey="about" label="About"><About /></ErrorBoundary>
    </div>
  );
}

function GeneralSettings() {
  const { settings, saveSettings, meta } = useApp();
  const [browsing, setBrowsing] = useState(false);
  if (!settings || !meta) return null;
  return (
    <div className="col" style={{ gap: 18 }}>
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
      {browsing && <FileBrowser mode="folder" extensions={[]} start={settings.output_dir} onClose={() => setBrowsing(false)}
        onPick={(p) => { saveSettings({ output_dir: p[0] }); setBrowsing(false); }} />}
    </div>
  );
}

function About() {
  const { meta } = useApp();
  if (!meta) return null;
  return (
    <section className="card pad col">
      <div className="h2">About</div>
      <div>OfficeFlow {meta.version} — offline office automation (interface {process.env.NEXT_PUBLIC_UI_VERSION})</div>
      <div className="faint selectable" style={{ fontSize: 12, wordBreak: "break-all" }}>Data folder: {meta.home}</div>
    </section>
  );
}
