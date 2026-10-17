import { useRef, useState } from "react";
import { toast } from "sonner";
import { RefreshCw, Upload, AlertTriangle, Link2, FilePlus2 } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, num, date } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Panel, Empty, NativeSelect } from "@/components/common";

const ST = { parsed: ["Nouă", "New", "text-blue-500"], nir_created: ["NIR creat", "GRN created", "text-emerald-500"], linked: ["Legată (overwrite)", "Linked (overwrite)", "text-cyan-500"] };

function Detail({ id, onClose, onDone }) {
  const { tr } = useLang();
  const { data: m } = useApi(id ? `/efactura/inbox/${id}` : null, [id]);
  const { data: products } = useApi("/products");
  const [map, setMap] = useState({});
  const [result, setResult] = useState(null);
  const [dup, setDup] = useState(null);
  if (!m) return null;
  const p = m.parsed;
  const duplicate = dup || m.duplicate_nir;
  const val = (idx) => map[idx] ?? (m.suggestions[idx] || "__new");
  const body = (force = false) => ({ force, mappings: p.lines.map((l) => {
    const v = val(l.idx);
    return { idx: l.idx, product_id: v.startsWith("__") ? null : v, create: v === "__new", skip: v === "__skip" };
  }) });
  const done = m.status !== "parsed";
  const create = async () => {
    try {
      const r = await api.post(`/efactura/inbox/${id}/create-nir`, body());
      toast.success(`NIR ${r.data.number} ${tr("creat din e-Factura", "created from e-Invoice")}`);
      onDone();
      onClose();
    } catch (e) {
      if (e.response?.status === 409) setDup({ number: errMsg(e).match(/NIR (\S+)/)?.[1], id: m.duplicate_nir?.id });
      toast.error(errMsg(e));
    }
  };
  const link = async () => {
    try {
      const r = await api.post(`/efactura/inbox/${id}/link/${duplicate.id}`, body());
      setResult(r.data);
      toast.success(tr("NIR actualizat și legat de e-Factura", "GRN updated and linked to e-Invoice"));
      onDone();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <div data-testid="inbox-detail">
      <div className="grid gap-3 text-sm sm:grid-cols-4">
        {[[tr("Furnizor", "Supplier"), p.supplier_name], ["CUI", p.supplier_cui], [tr("Serie / nr.", "Series / no."), p.series_number], [tr("Data", "Date"), date(p.issue_date)],
          [tr("Total fără TVA", "Net"), money(p.net)], ["TVA", money(p.vat)], ["Total", money(p.gross)], [tr("Furnizor în sistem", "Supplier in system"), m.supplier ? m.supplier.name : tr("Nu – va fi creat", "No – will be created")]].map(([l, v]) => (
          <div key={l}><div className="eyebrow">{l}</div><div className="font-mono text-xs">{v || "—"}</div></div>
        ))}
      </div>
      {duplicate && !done && (
        <div data-testid="inbox-duplicate-alert" className="mt-4 flex flex-wrap items-center gap-3 rounded border border-yellow-500/50 bg-yellow-500/10 p-3 text-sm text-yellow-700 dark:text-yellow-400">
          <AlertTriangle className="h-5 w-5" />
          <div className="flex-1"><b>{tr("Factură găsită în sistem!", "Invoice found in system!")}</b> NIR {duplicate.number} ({tr("introdus manual", "entered manually")}). {tr("Dorești să faci Overwrite / Link cu e-Factura?", "Overwrite / link with e-Invoice?")}</div>
          <Button size="sm" data-testid="inbox-overwrite-button" onClick={link}><Link2 className="mr-1 h-4 w-4" />Overwrite / Link</Button>
        </div>
      )}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm" data-testid="inbox-mapping-table">
          <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
            <th className="px-2 py-2">{tr("Articol XML furnizor", "Supplier XML item")}</th><th className="px-2">Cod</th><th className="px-2 text-right">{tr("Cant.", "Qty")}</th>
            <th className="px-2 text-right">{tr("Preț", "Price")}</th><th className="px-2 text-right">TVA</th><th className="px-2">{tr("Articol în stoc propriu", "Own stock item")}</th>
          </tr></thead>
          <tbody>{p.lines.map((l) => (
            <tr key={l.idx} className="h-11 border-b border-border/50">
              <td className="px-2">{l.name}</td><td className="px-2 font-mono text-xs">{l.seller_code || "—"}</td><td className="px-2 text-right font-mono">{num(l.qty)} {l.unit_code}</td>
              <td className="px-2 text-right font-mono">{money(l.price)}</td><td className="px-2 text-right font-mono">{l.vat_rate}%</td>
              <td className="px-2"><NativeSelect data-testid={`inbox-map-${l.idx}`} disabled={done} value={val(l.idx)} onChange={(e) => setMap({ ...map, [l.idx]: e.target.value })}>
                <option value="__new">{tr("+ Creează articol nou", "+ Create new item")}</option><option value="__skip">{tr("— Ignoră linia —", "— Skip line —")}</option>
                {(products || []).map((x) => <option key={x.id} value={x.id}>{x.code} · {x.name}</option>)}
              </NativeSelect></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {result && (
        <div data-testid="inbox-link-result" className="mt-3 rounded border border-cyan-500/40 bg-cyan-500/5 p-3 text-xs">
          <b>NIR {result.number}</b> {tr("actualizat fără mișcări duplicate:", "updated without duplicate moves:")}
          {result.changes.length ? result.changes.map((c) => <div key={c}>• {c}</div>) : <div>{tr("Nicio diferență – doar legat oficial.", "No differences – officially linked.")}</div>}
          {!!result.unmatched_nir_lines.length && <div className="text-yellow-600">{tr("Linii doar în NIR (neregăsite în XML):", "Lines only in GRN:")} {result.unmatched_nir_lines.join(", ")}</div>}
        </div>
      )}
      {!done && !duplicate && <div className="mt-4 flex justify-end"><Button data-testid="inbox-create-nir-button" onClick={create}><FilePlus2 className="mr-1 h-4 w-4" />{tr("Generează NIR din XML", "Create GRN from XML")}</Button></div>}
      {done && <div className="mt-4 text-sm text-muted-foreground">{tr("Procesată", "Processed")}: NIR {m.nir_number}</div>}
    </div>
  );
}

export default function EfacturaInbox({ onNirChange }) {
  const { tr } = useLang();
  const { data, reload } = useApi("/efactura/inbox");
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const sync = async () => {
    setBusy(true);
    try {
      const r = await api.post("/efactura/inbox/sync");
      toast.success(`${r.data.new} ${tr("facturi noi", "new invoices")}`);
      reload();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const upload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      await api.post("/efactura/inbox/upload", { filename: f.name, content: await f.text() });
      toast.success(tr("XML importat și parsat", "XML imported and parsed"));
      reload();
    } catch (err) {
      toast.error(errMsg(err));
    }
    e.target.value = "";
  };
  return (
    <Panel testid="efactura-inbox">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button data-testid="inbox-sync-button" disabled={busy} onClick={sync}><RefreshCw className={`mr-1 h-4 w-4 ${busy ? "animate-spin" : ""}`} />{tr("Sincronizare cu ANAF", "Sync with ANAF")}</Button>
        <Button variant="outline" data-testid="inbox-import-button" onClick={() => fileRef.current?.click()}><Upload className="mr-1 h-4 w-4" />{tr("Import XML", "Import XML")}</Button>
        <input ref={fileRef} type="file" accept=".xml,text/xml" className="hidden" data-testid="inbox-import-input" onChange={upload} />
        <span className="text-xs text-muted-foreground">{tr("Sincronizare automată orară (CRON) din SPV pentru CIF-ul firmei.", "Hourly automatic SPV sync (CRON) for the company VAT ID.")}</span>
      </div>
      {!data?.length ? <Empty text={tr("Nicio factură primită.", "No received invoices.")} /> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="inbox-table">
            <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
              <th className="px-2 py-2">{tr("Primită", "Received")}</th><th className="px-2">{tr("Furnizor", "Supplier")}</th><th className="px-2">CUI</th><th className="px-2">{tr("Serie / nr.", "No.")}</th>
              <th className="px-2 text-right">Total</th><th className="px-2">{tr("Sursă", "Source")}</th><th className="px-2">Status</th>
            </tr></thead>
            <tbody>{data.map((m) => (
              <tr key={m.id} data-testid={`inbox-row-${m.parsed.series_number}`} onClick={() => setOpen(m.id)} className="h-10 cursor-pointer border-b border-border/50 hover:bg-accent/60">
                <td className="px-2">{date(m.received_at)}</td><td className="px-2">{m.parsed.supplier_name}</td><td className="px-2 font-mono text-xs">{m.parsed.supplier_cui}</td>
                <td className="px-2 font-mono text-xs">{m.parsed.series_number}</td><td className="px-2 text-right font-mono">{money(m.parsed.gross)}</td>
                <td className="px-2 text-xs uppercase">{m.source}</td>
                <td className={`px-2 text-xs font-semibold ${ST[m.status]?.[2]}`}>{tr(...(ST[m.status] || [m.status, m.status]).slice(0, 2))}{m.nir_number ? ` · ${m.nir_number}` : ""}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="max-w-4xl" data-testid="inbox-dialog">
          <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{tr("Factură e-Factura primită", "Received e-Invoice")}</DialogTitle></DialogHeader>
          {open && <Detail key={open} id={open} onClose={() => setOpen(null)} onDone={() => { reload(); onNirChange?.(); }} />}
        </DialogContent>
      </Dialog>
    </Panel>
  );
}
