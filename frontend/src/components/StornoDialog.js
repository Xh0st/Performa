import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, num } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Field } from "@/components/common";

const avail = (l) => Math.round((l.qty - (l.credited_qty || 0)) * 10000) / 10000;

export default function StornoDialog({ inv, open, onOpenChange }) {
  const { tr } = useLang();
  const nav = useNavigate();
  const [qty, setQty] = useState({});
  const [reason, setReason] = useState("");
  const [restock, setRestock] = useState(false);
  const [busy, setBusy] = useState(false);
  const hasParts = inv.lines.some((l) => ["part", "consumable"].includes(l.type) && l.product_id);
  const total = inv.lines.reduce((s, l) => s + (Number(qty[l.id]) || 0) * l.unit_price * (1 - (l.discount || 0) / 100) * (1 + l.vat_rate / 100), 0);
  const fillAll = () => setQty(Object.fromEntries(inv.lines.map((l) => [l.id, avail(l)])));
  const save = async () => {
    setBusy(true);
    try {
      const lines = inv.lines.filter((l) => Number(qty[l.id]) > 0).map((l) => ({ line_id: l.id, qty: Number(qty[l.id]) }));
      const r = await api.post(`/invoices/${inv.id}/storno`, { reason, restock, lines });
      toast.success(`${tr("Factură de stornare emisă", "Credit note issued")}: ${r.data.series}${r.data.number}`);
      onOpenChange(false);
      nav(`/invoices/${r.data.id}`);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" data-testid="storno-dialog">
        <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{tr("Stornare factură", "Credit note")} · {inv.series}{inv.number}</DialogTitle></DialogHeader>
        <div className="flex justify-end"><Button variant="outline" size="sm" data-testid="storno-fill-all-button" onClick={fillAll}>{tr("Stornare totală", "Full credit")}</Button></div>
        <div className="max-h-[45vh] overflow-auto">
          <table className="w-full min-w-[560px] text-sm"><thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
            <th className="py-2">{tr("Denumire", "Description")}</th><th className="text-right">{tr("Facturat", "Invoiced")}</th><th className="text-right">{tr("Stornat", "Credited")}</th><th className="w-28 text-right">{tr("De stornat", "To credit")}</th>
          </tr></thead><tbody>
            {inv.lines.map((l) => (
              <tr key={l.id} className="h-11 border-b border-border/50">
                <td>{l.description} <span className="text-[11px] uppercase text-muted-foreground">{l.type === "labor" ? tr("manoperă", "labor") : tr("piesă", "part")}</span></td>
                <td className="text-right font-mono">{num(l.qty)}</td><td className="text-right font-mono">{num(l.credited_qty || 0)}</td>
                <td className="pl-2"><Input data-testid={`storno-qty-${l.id}`} type="number" min={0} max={avail(l)} step="0.01" disabled={avail(l) <= 0}
                  className="h-8 text-right font-mono" value={qty[l.id] ?? ""} placeholder="0" onChange={(e) => setQty({ ...qty, [l.id]: e.target.value })} /></td>
              </tr>
            ))}
          </tbody></table>
        </div>
        <Field label={tr("Motivul stornării", "Reason")}><Input data-testid="storno-reason-input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder={tr("ex. piesă returnată de client, eroare de facturare", "e.g. part returned, billing error")} /></Field>
        {hasParts && (
          <label className="flex items-center gap-2 text-sm" data-testid="storno-restock-label">
            <Checkbox data-testid="storno-restock-checkbox" checked={restock} onCheckedChange={(v) => setRestock(!!v)} />
            {tr("Piesele stornate reintră în stoc (la costul de ieșire)", "Credited parts return to stock (at issue cost)")}
          </label>
        )}
        <div className="text-right font-mono text-sm" data-testid="storno-total">{tr("Total stornare", "Credit total")}: −{money(total)}</div>
        <DialogFooter><Button data-testid="storno-save-button" disabled={busy || total <= 0 || !reason.trim()} onClick={save}>{tr("Emite factura de stornare", "Issue credit note")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
