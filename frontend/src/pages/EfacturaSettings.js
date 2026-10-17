import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PlugZap, RefreshCw, Unplug, Save, ShieldCheck, ShieldAlert } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { dt } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { PageHeader, Panel, Loading, Field } from "@/components/common";

const ENVS = [["simulare", "Simulare", "Simulation"], ["test", "Test (Sandbox ANAF)", "Test (ANAF sandbox)"], ["prod", "Producție", "Production"]];

function EnvSwitch({ value, onChange }) {
  const { tr } = useLang();
  return (
    <div className="flex flex-wrap gap-1 rounded-md border bg-background p-1" data-testid="efactura-env-switch">
      {ENVS.map(([k, ro, en]) => (
        <button key={k} type="button" data-testid={`efactura-env-${k}`} onClick={() => onChange(k)}
          className={`rounded px-3 py-1.5 text-xs font-semibold uppercase tracking-wider transition-colors ${value === k ? (k === "prod" ? "bg-rose-600 text-white" : k === "test" ? "bg-yellow-500 text-slate-900" : "bg-slate-600 text-white") : "text-muted-foreground hover:bg-accent"}`}>
          {tr(ro, en)}
        </button>
      ))}
    </div>
  );
}

export default function EfacturaSettings() {
  const { tr } = useLang();
  const [sp, setSp] = useSearchParams();
  const { data, setData } = useApi("/efactura/config");
  const { data: logs, reload: reloadLogs } = useApi("/efactura/logs");
  const [f, setF] = useState(null);
  useEffect(() => {
    if (data) setF({ environment: data.environment, client_id: data.client_id, client_secret: "", redirect_uri: data.redirect_uri, auto_send: data.auto_send });
  }, [data]);
  useEffect(() => {
    const o = sp.get("oauth");
    if (o) {
      o === "ok" ? toast.success(tr("Autorizare SPV reușită", "SPV authorization successful"), { id: "oauth" }) : toast.error(tr("Autorizare SPV eșuată – vezi jurnalul", "SPV authorization failed – see log"), { id: "oauth" });
      setSp({});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!data || !f) return <Loading />;

  const run = async (fn, msg) => {
    try {
      const r = await fn();
      if (r?.data?.environment) setData(r.data);
      if (msg) toast.success(msg);
      reloadLogs();
      return r;
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const save = () => run(() => api.put("/efactura/config", { ...f, client_secret: f.client_secret || null }), tr("Setări salvate", "Settings saved"));
  const connect = async () => {
    const saved = await save();
    if (!saved) return;
    const r = await run(() => api.post("/efactura/oauth/start"));
    if (r?.data?.url) window.location.href = r.data.url;
  };
  const c = data.company;
  const okConn = data.connected && data.environment !== "simulare";

  return (
    <div data-testid="efactura-settings-page">
      <PageHeader eyebrow={tr("Administrare · RO e-Factura · OAuth 2.0 ANAF", "Administration · RO e-Invoice · ANAF OAuth 2.0")} title={tr("e-Factura / Setări API", "e-Invoice / API settings")}
        actions={<Button data-testid="efactura-save-button" onClick={save}><Save className="mr-1 h-4 w-4" />{tr("Salvează", "Save")}</Button>} />
      <div data-testid="efactura-connection-status" className={`mb-4 flex items-center gap-3 rounded-md border px-4 py-3 ${okConn ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : data.environment === "simulare" ? "border-slate-500/40 bg-slate-500/10" : "border-yellow-500/40 bg-yellow-500/10 text-yellow-700 dark:text-yellow-400"}`}>
        {okConn ? <ShieldCheck className="h-5 w-5" /> : <ShieldAlert className="h-5 w-5" />}
        <div className="flex-1"><div className="font-semibold">{data.status_text}</div>
          <div className="font-mono text-[11px] opacity-80">API: {data.api_base} · CIF {data.cif || "—"}{data.token_expires_at ? ` · access token ${tr("expiră", "expires")} ${dt(data.token_expires_at)}` : ""}</div>
          {data.last_error && <div className="text-xs text-rose-500">{data.last_error}</div>}</div>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={tr("Mediu de lucru", "Environment")}>
          <EnvSwitch value={f.environment} onChange={(v) => setF({ ...f, environment: v })} />
          <p className="mt-3 text-xs text-muted-foreground">{tr("Simulare: nu comunică cu ANAF (pentru instruire). Test: api.anaf.ro/test. Producție: api.anaf.ro/prod — facturile au valoare fiscală. Salvați după schimbare.",
            "Simulation: no ANAF calls. Test: api.anaf.ro/test. Production: api.anaf.ro/prod — invoices are legally binding. Save after switching.")}</p>
          <label className="mt-4 flex items-center gap-3 text-sm"><Switch data-testid="efactura-autosend-switch" checked={f.auto_send} onCheckedChange={(v) => setF({ ...f, auto_send: v })} />
            {tr("Trimitere automată în e-Factura la emiterea facturii fiscale", "Auto-send to e-Invoice when a fiscal invoice is issued")}</label>
        </Panel>
        <Panel title={tr("Date companie (din Setări companie)", "Company data (from Company settings)")}>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[["Denumire", c.name], ["CIF", c.cui], ["Reg. Com.", c.reg_com], [tr("Cod județ", "County"), c.county_code], [tr("Adresă", "Address"), `${c.address}, ${c.city}`], ["IBAN", c.iban]].map(([l, v]) => (
              <div key={l}><div className="eyebrow">{l}</div><div className={`font-mono text-xs ${String(v).includes("[") ? "text-rose-500" : ""}`}>{v || "—"}</div></div>
            ))}
          </div>
        </Panel>
        <Panel title={tr("Autentificare OAuth 2.0 ANAF", "ANAF OAuth 2.0")} className="xl:col-span-2">
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Client ID"><Input data-testid="efactura-client-id-input" className="font-mono" value={f.client_id} onChange={(e) => setF({ ...f, client_id: e.target.value })} /></Field>
            <Field label="Client Secret"><Input data-testid="efactura-client-secret-input" type="password" className="font-mono" value={f.client_secret}
              placeholder={data.has_secret ? tr("•••••• salvat (criptat)", "•••••• saved (encrypted)") : ""} onChange={(e) => setF({ ...f, client_secret: e.target.value })} /></Field>
            <Field label="Redirect URI"><Input data-testid="efactura-redirect-input" className="font-mono text-xs" value={f.redirect_uri} onChange={(e) => setF({ ...f, redirect_uri: e.target.value })} /></Field>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{tr("Înregistrați exact acest Redirect URI în portalul ANAF (Gestionare aplicații OAuth, serviciul e-Factura). Autorizarea se face în browser cu certificatul digital calificat al reprezentantului SPV. Token-urile se reîmprospătează automat zilnic (job CRON).",
            "Register this exact Redirect URI in the ANAF portal (OAuth applications, e-Factura service). Authorization happens in the browser with the SPV representative's qualified certificate. Tokens refresh automatically daily (CRON job).")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button data-testid="efactura-connect-button" disabled={f.environment === "simulare"} onClick={connect}><PlugZap className="mr-1 h-4 w-4" />{tr("Conectare / Autorizare SPV", "Connect / Authorize SPV")}</Button>
            <Button variant="outline" data-testid="efactura-refresh-token-button" disabled={!okConn} onClick={() => run(() => api.post("/efactura/oauth/refresh"), tr("Token reîmprospătat", "Token refreshed"))}><RefreshCw className="mr-1 h-4 w-4" />Refresh token</Button>
            <Button variant="outline" data-testid="efactura-disconnect-button" disabled={!okConn} onClick={() => run(() => api.post("/efactura/oauth/disconnect"), tr("Deconectat", "Disconnected"))}><Unplug className="mr-1 h-4 w-4" />{tr("Deconectare", "Disconnect")}</Button>
          </div>
        </Panel>
        <Panel title={tr("Jurnal e-Factura", "e-Invoice log")} className="xl:col-span-2" testid="efactura-logs">
          <div className="max-h-80 overflow-y-auto">
            <table className="w-full text-sm"><tbody>
              {(logs || []).map((l) => (
                <tr key={l.id} className="h-9 border-b border-border/50"><td className="font-mono text-xs">{dt(l.at)}</td><td className="font-mono text-[11px] uppercase text-primary">{l.op}</td>
                  <td className="text-xs">{l.env}</td><td className={`text-xs ${l.ok ? "" : "text-rose-500"}`}>{l.message}</td></tr>
              ))}
            </tbody></table>
            {!logs?.length && <div className="text-sm text-muted-foreground">—</div>}
          </div>
        </Panel>
      </div>
    </div>
  );
}
