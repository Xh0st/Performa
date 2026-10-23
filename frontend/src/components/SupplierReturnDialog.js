import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, num, date, today } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Field, NativeSelect } from "@/components/common";

const createFreeLine = () => ({
  row_id: window.crypto?.randomUUID?.() || `row-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  product_id: "",
  qty: 1,
});

function NirLines({ nirId, qty, setQty }) {
  const { tr } = useLang();
  const { data: n } = useApi(`/nirs/${nirId}`, [nirId]);
  if (!n) return null;
  return (
    <table className="w-full text-sm" data-testid="return-nir-lines"><thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
      <th className="py-2">{tr("Articol", "Item")}</th><th className="text-right">NIR</th><th className="text-right">{tr("Returnat", "Returned")}</th><th className="w-28 text-right">{tr("Retur", "Return")}</th>
    </tr></thead><tbody>
      {n.lines.map((l) => {
        const max = Math.max(l.qty - (l.returned_qty || 0), 0);
        return (
          <tr key={l.product_id} className="h-11 border-b border-border/50">
            <td><span className="font-mono text-xs text-primary">{l.code}</span> {l.name}<div className="text-[11px] text-muted-foreground">{money(l.unit_cost)} / {l.unit}</div></td>
            <td className="text-right font-mono">{num(l.qty)}</td><td className="text-right font-mono">{num(l.returned_qty || 0)}</td>
            <td className="pl-2"><Input data-testid={`return-qty-${l.code}`} type="number" min={0} max={max} disabled={max <= 0} className="h-8 text-right font-mono" placeholder="0"
              value={qty[l.product_id] ?? ""} onChange={(e) => setQty({ ...qty, [l.product_id]: e.target.value })} /></td>
          </tr>
        );
      })}
    </tbody></table>
  );
}

function FreeLines({ lines, setLines }) {
  const { tr } = useLang();
  const { data: products } = useApi("/products");
  const set = (i, k, v) => setLines(lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  return (
    <div className="space-y-2">
      {lines.map((l, i) => (
        <div key={l.row_id} className="grid grid-cols-12 gap-2">
          <NativeSelect data-testid={`return-line-${i}-product`} className="col-span-8" value={l.product_id} onChange={(e) => set(i, "product_id", e.target.value)}>
            <option value="">—</option>{(products || []).filter((p) => p.stock_qty > 0).map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name} ({tr("stoc", "stock")} {num(p.stock_qty)})</option>)}
          </NativeSelect>
          <Input data-testid={`return-line-${i}-qty`} className="col-span-3" type="number" value={l.qty} onChange={(e) => set(i, "qty", e.target.value)} />
          <Button variant="ghost" size="icon" className="col-span-1" onClick={() => setLines(lines.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4 text-rose-500" /></Button>
        </div>
      ))}
      <Button variant="outline" size="sm" data-testid="return-add-line-button" onClick={() => setLines([...lines, createFreeLine()])}><Plus className="mr-1 h-3 w-3" />{tr("Linie", "Line")}</Button>
    </div>
  );
}

export default function SupplierReturnDialog({ open, onOpenChange, onSaved, preset }) {
  const { tr } = useLang();
  const { data: suppliers } = useApi(open ? "/suppliers" : null, [open]);
  const { data: nirs } = useApi(open ? "/nirs" : null, [open]);
  const [f, setF] = useState({ supplier_id: preset?.supplier_id || "", nir_id: preset?.id || "", reason: "", date: today() });
  const [qty, setQty] = useState({});
  const [lines, setLines] = useState(() => [createFreeLine()]);
  const [busy, setBusy] = useState(false);
  const supNirs = (nirs || []).filter((n) => n.supplier_id === f.supplier_id);
  const save = async () => {
    setBusy(true);
    try {
      const body = f.nir_id ? Object.entries(qty).filter(([, q]) => Number(q) > 0).map(([product_id, q]) => ({ product_id, qty: Number(q) }))
        : lines
          .filter((line) => line.product_id)
          .map(({ product_id, qty }) => ({ product_id, qty: Number(qty) }));
      const r = await api.post("/supplier-returns", { ...f, date: new Date(f.date).toISOString(), lines: body });
      toast.success(`${tr("Retur înregistrat, stoc scăzut", "Return saved, stock reduced")}: ${r.data.number}`);
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" data-testid="supplier-return-dialog">
        <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{tr("Retur piese către furnizor", "Return parts to supplier")}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={tr("Furnizor", "Supplier")}>
            <NativeSelect data-testid="return-supplier-select" value={f.supplier_id} onChange={(e) => { setF({ ...f, supplier_id: e.target.value, nir_id: "" }); setQty({}); }}>
              <option value="">—</option>{(suppliers || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </NativeSelect>
          </Field>
          <Field label={tr("NIR de origine (opțional)", "Source GRN (optional)")}>
            <NativeSelect data-testid="return-nir-select" value={f.nir_id} disabled={!f.supplier_id} onChange={(e) => { setF({ ...f, nir_id: e.target.value }); setQty({}); }}>
              <option value="">{tr("— Fără NIR (FIFO) —", "— No GRN (FIFO) —")}</option>
              {supNirs.map((n) => <option key={n.id} value={n.id}>{n.number} · {n.invoice_no || n.aviz_no} · {date(n.date)}</option>)}
            </NativeSelect>
          </Field>
          <Field label={tr("Motiv retur", "Reason")}><Input data-testid="return-reason-input" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder={tr("ex. piesă greșită, defectă", "e.g. wrong / defective part")} /></Field>
          <Field label={tr("Data", "Date")}>
            <Input
              data-testid="return-date-input"
              type="date"
              value={f.date}
              onChange={(e) => setF({ ...f, date: e.target.value })}
            />
          </Field>
        </div>
        <div className="max-h-[40vh] overflow-y-auto">
          {f.nir_id ? <NirLines nirId={f.nir_id} qty={qty} setQty={setQty} /> : <FreeLines lines={lines} setLines={setLines} />}
        </div>
        <DialogFooter><Button data-testid="return-save-button" disabled={busy || !f.supplier_id || !f.reason.trim()} onClick={save}>{tr("Înregistrează retur", "Save return")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
