import { useState } from "react";
import { toast } from "sonner";
import { ShieldCheck } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { dt } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import SignaturePad from "@/components/SignaturePad";

const ITEMS = [["frane", "Frâne", "Brakes"], ["directie", "Direcție", "Steering"], ["suspensie", "Suspensie", "Suspension"], ["lumini", "Lumini", "Lights"],
  ["niveluri", "Niveluri lichide", "Fluid levels"], ["anvelope", "Anvelope / presiune", "Tyres / pressure"], ["test_drive", "Test drive", "Test drive"]];
const OPTS = [["ok", "OK", "bg-emerald-500 text-white"], ["nok", "NOK", "bg-rose-500 text-white"], ["na", "N/A", "bg-slate-500 text-white"]];

export default function QcTab({ wo, onChange, locked }) {
  const { tr } = useLang();
  const qc = wo.qc || {};
  const [items, setItems] = useState(qc.items || {});
  const [notes, setNotes] = useState(qc.notes || "");
  const [mSig, setMSig] = useState(qc.mechanic_signature || "");
  const [cSig, setCSig] = useState(qc.chief_signature || "");

  const save = async () => {
    try {
      const r = await api.put(`/work-orders/${wo.id}/qc`, { items, notes, mechanic_signature: mSig, chief_signature: cSig });
      onChange(r.data);
      toast[r.data.qc.passed ? "success" : "warning"](r.data.qc.passed ? tr("Control calitate promovat", "QC passed") : tr("Salvat — incomplet sau neconform", "Saved — incomplete or non-compliant"));
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div>
        {qc.at && (
          <div data-testid="qc-status" className={`mb-4 flex items-center gap-2 rounded border px-3 py-2 text-sm ${qc.passed ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500" : "border-yellow-500/40 bg-yellow-500/10 text-yellow-500"}`}>
            <ShieldCheck className="h-4 w-4" />{qc.passed ? tr("Promovat", "Passed") : tr("Nepromovat", "Not passed")} · {qc.by} · {dt(qc.at)}
          </div>
        )}
        <div className="space-y-2">
          {ITEMS.map(([k, ro, en]) => (
            <div key={k} className="flex items-center justify-between rounded border px-3 py-2">
              <span className="text-sm font-medium">{tr(ro, en)}</span>
              <div className="flex gap-1">
                {OPTS.map(([v, l, cls]) => (
                  <button key={v} type="button" disabled={locked} data-testid={`qc-${k}-${v}`} onClick={() => setItems({ ...items, [k]: v })}
                    className={`rounded px-3 py-1 font-mono text-xs font-semibold transition-colors ${items[k] === v ? cls : "bg-muted text-muted-foreground hover:bg-accent"}`}>{l}</button>
                ))}
              </div>
            </div>
          ))}
        </div>
        <Textarea className="mt-3" rows={2} placeholder={tr("Observații control", "QC notes")} value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="qc-notes-input" />
      </div>
      <div className="space-y-4">
        <div><div className="eyebrow mb-2">{tr("Semnătură mecanic", "Mechanic signature")}</div><SignaturePad testid="qc-mechanic-signature" value={mSig} onChange={setMSig} height={130} /></div>
        <div><div className="eyebrow mb-2">{tr("Semnătură șef service", "Service manager signature")}</div><SignaturePad testid="qc-chief-signature" value={cSig} onChange={setCSig} height={130} /></div>
        {!locked && <Button data-testid="qc-save-button" className="w-full" onClick={save}>{tr("Salvează control calitate", "Save quality control")}</Button>}
      </div>
    </div>
  );
}
