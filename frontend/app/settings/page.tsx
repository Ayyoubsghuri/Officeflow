"use client";

import { useState } from "react";
import FileBrowser from "@/components/FileBrowser";
import Icon from "@/components/Icon";
import { Check } from "@/components/ParamForm";
import { useApp } from "@/lib/app-context";
import { openPath } from "@/lib/desktop";
import { nativePick } from "@/lib/pick";

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
      <section className="card pad col">
        <div className="h2">Plugins</div>
        <div className="muted">Extra tools can be added by placing plugin files in the plugin folder. They are loaded the next time OfficeFlow starts. Only install plugins from people you trust.</div>
        {meta.plugin_problems.map((p) => <div key={p} className="banner failed">{p}</div>)}
        <div><button className="btn" onClick={() => openPath(`${meta.home}/plugins`)}><Icon name="folder" size={17} />Open plugin folder</button></div>
      </section>
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
