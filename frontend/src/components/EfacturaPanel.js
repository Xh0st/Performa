import { useState } from "react";
import { toast } from "sonner";
import { FileCode2, Send, RefreshCw, Download, CheckCheck } from "lucide-react";
import { api, errMsg, downloadFile } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { dt } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Panel, Badge, EF_STATUS } from "@/components/common";

export default function EfacturaPanel({ inv, setData, reload }) {
  const { tr } = useLang();
  const [val, setVal] = useState(null);
  const ef = inv.efactura || {};
  const act = async (path, msg) => {
    try {
      setData((await api.post(`/invoices/${inv.id}/efactura/${path}`)).data);
      toast.success(msg);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const validate = async (anaf) => {
    try {
      setVal((await api.post(`/invoices/${inv.id}/efactura/validate?anaf=${anaf}`)).data);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const dl = async (path, name) => {
    try {
      await downloadFile(path, name);
      reload();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <Panel title="e-Factura ANAF" testid="efactura-panel">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <Badge map={EF_STATUS} value={ef.status} testid="efactura-status" />
        {ef.upload_index && <span className="font-mono text-xs" data-testid="efactura-upload-index">index {ef.upload_index}{ef.env ? ` · ${ef.env}` : ""}</span>}
      </div>
      <div className="grid gap-2">
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" size="sm" data-testid="efactura-validate-button" onClick={() => validate(false)}><CheckCheck className="mr-1 h-4 w-4" />{tr("Validare internă", "Internal check")}</Button>
          <Button variant="outline" size="sm" data-testid="efactura-validate-anaf-button" onClick={() => validate(true)}><CheckCheck className="mr-1 h-4 w-4" />{tr("Validare ANAF", "ANAF validation")}</Button>
        </div>
        {val && (
          <div data-testid="efactura-validation-result" className={`rounded border p-2 text-xs ${val.errors.length || (val.anaf && !val.anaf.ok) ? "border-rose-500/40 text-rose-500" : "border-emerald-500/40 text-emerald-600 dark:text-emerald-400"}`}>
            {val.errors.length ? val.errors.map((e) => <div key={e}>• {e}</div>) : <div>{tr("Validare internă OK (CIUS-RO, UN/ECE, TVA, totaluri)", "Internal validation OK")}</div>}
            {val.anaf && <div className="mt-1">ANAF: {val.anaf.ok ? "OK" : (val.anaf.messages || []).join("; ") || String(val.anaf.raw)}</div>}
          </div>
        )}
        <Button variant="outline" size="sm" data-testid="efactura-download-xml-button" onClick={() => dl(`/invoices/${inv.id}/efactura/xml`, `efactura_${inv.series}${inv.number}.xml`)}><FileCode2 className="mr-1 h-4 w-4" />{tr("Descarcă XML UBL (CIUS-RO)", "Download UBL XML")}</Button>
        <Button size="sm" data-testid="efactura-submit-button" disabled={["pending", "ok"].includes(ef.status)} onClick={() => act("submit", tr("Trimis în e-Factura", "Sent to e-Invoice"))}><Send className="mr-1 h-4 w-4" />{tr("Trimite în e-Factura", "Send to e-Invoice")}</Button>
        <Button variant="outline" size="sm" data-testid="efactura-refresh-button" disabled={ef.status !== "pending"} onClick={() => act("refresh", tr("Stare interogată", "Status checked"))}><RefreshCw className="mr-1 h-4 w-4" />{tr("Verifică stare / recipisă", "Check status / receipt")}</Button>
        {ef.has_receipt && <Button variant="outline" size="sm" data-testid="efactura-receipt-button" onClick={() => dl(`/invoices/${inv.id}/efactura/receipt`, `recipisa_${inv.series}${inv.number}.zip`)}><Download className="mr-1 h-4 w-4" />{tr("Descarcă recipisa ZIP (semnătură MF)", "Download signed receipt ZIP")}</Button>}
      </div>
      {!!ef.errors?.length && <div data-testid="efactura-errors" className="mt-3 rounded border border-rose-500/40 bg-rose-500/10 p-2 text-xs text-rose-500">{ef.errors.map((error) => <div key={error}>• {error}</div>)}</div>}
      {ef.env === "simulare" && <p className="mt-3 rounded border border-yellow-500/30 bg-yellow-500/10 p-2 text-[11px] text-yellow-600 dark:text-yellow-400">{tr("Transmis în mod SIMULARE – fără valoare fiscală. Configurați mediul în Administrare › eFactura.", "Sent in SIMULATION mode – no fiscal value. Configure in Administration › e-Invoice.")}</p>}
      <div className="mt-3 space-y-1">{(ef.history || []).map((h) => <div key={`${h.at}-${h.event}`} className="text-[11px]"><span className="font-mono text-muted-foreground">{dt(h.at)}</span> · {h.event}</div>)}</div>
    </Panel>
  );
}
