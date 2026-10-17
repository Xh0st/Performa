import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { Printer, Wallet } from "lucide-react";
import EfacturaPanel from "@/components/EfacturaPanel";
import { api, errMsg, useApi, downloadFile } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { useAuth } from "@/context/AuthContext";
import { money, date, dt, num } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { PageHeader, Panel, Loading, Badge, PAY_STATUS, EF_STATUS, Field, NativeSelect } from "@/components/common";

export const METHODS = { numerar: ["Numerar", "Cash"], pos: ["Card POS", "Card POS"], transfer: ["Transfer bancar", "Bank transfer"], online: ["Online", "Online"] };
export const DOCS = { chitanta: ["Chitanță", "Receipt"], bon_pos: ["Bon POS", "POS slip"], ordin_plata: ["Ordin de plată", "Payment order"], confirmare_online: ["Confirmare online", "Online confirmation"] };

function PayDialog({ inv, open, onOpenChange, onSaved }) {
  const { tr } = useLang();
  const due = Math.round((inv.totals.gross - inv.paid_amount) * 100) / 100;
  const [f, setF] = useState({ amount: due, method: "numerar", reference: "" });
  const save = async () => {
    try {
      await api.post("/payments", { invoice_id: inv.id, amount: Number(f.amount), method: f.method, reference: f.reference });
      toast.success(tr("Încasare înregistrată", "Payment recorded"));
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="payment-dialog">
        <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{tr("Încasare", "Payment")} · {inv.series}{inv.number}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={tr("Sumă (RON)", "Amount (RON)")}><Input data-testid="payment-amount-input" type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
          <Field label={tr("Metodă", "Method")}>
            <NativeSelect data-testid="payment-method-select" value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })}>
              {Object.entries(METHODS).map(([k, v]) => <option key={k} value={k}>{tr(v[0], v[1])}</option>)}
            </NativeSelect>
          </Field>
          <Field label={tr("Referință (nr. OP / tranzacție)", "Reference")} className="sm:col-span-2"><Input data-testid="payment-reference-input" value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></Field>
        </div>
        <div className="text-xs text-muted-foreground">{tr("Rest de plată", "Remaining")}: <span className="font-mono">{money(due)}</span></div>
        <DialogFooter><Button data-testid="payment-save-button" onClick={save}>{tr("Înregistrează", "Record")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function InvoiceDetail() {
  const { id } = useParams();
  const { tr } = useLang();
  const { can } = useAuth();
  const { data: inv, setData, reload } = useApi(`/invoices/${id}`);
  const [pay, setPay] = useState(false);
  if (!inv) return <Loading />;
  const fiscal = inv.type === "fiscal";

  return (
    <div data-testid="invoice-detail-page">
      <PageHeader eyebrow={fiscal ? tr("Factură fiscală", "Fiscal invoice") : tr("Factură proformă", "Proforma invoice")} title={`${inv.series}${inv.number}`} testid="invoice-number"
        actions={<>
          {fiscal && <Badge map={PAY_STATUS} value={inv.status} testid="invoice-pay-status" />}
          <Button variant="outline" size="sm" data-testid="print-invoice-button" onClick={() => window.open(`/print/invoice/${id}`, "_blank")}><Printer className="mr-1 h-4 w-4" />{tr("Tipărește", "Print")}</Button>
          {fiscal && can("payments") && inv.status !== "paid" && <Button size="sm" data-testid="record-payment-button" onClick={() => setPay(true)}><Wallet className="mr-1 h-4 w-4" />{tr("Încasează", "Collect")}</Button>}
        </>} />
      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <Panel>
          <div className="mb-4 grid gap-4 text-sm md:grid-cols-2">
            <div><div className="eyebrow mb-1">{tr("Furnizor", "Supplier")}</div><div className="font-semibold">{inv.seller.name}</div><div className="font-mono text-xs">{inv.seller.cui} · {inv.seller.reg_com}</div></div>
            <div><div className="eyebrow mb-1">{tr("Cumpărător", "Buyer")}</div><div className="font-semibold">{inv.buyer.name}</div><div className="font-mono text-xs">{inv.buyer.cui || inv.buyer.cnp} {inv.buyer.reg_com}</div><div className="text-xs text-muted-foreground">{inv.buyer.address}, {inv.buyer.city}</div></div>
            <div><div className="eyebrow mb-1">{tr("Vehicul", "Vehicle")}</div><div className="text-xs">{inv.vehicle} · {num(inv.mileage, 0)} km</div></div>
            <div><div className="eyebrow mb-1">{tr("Date", "Dates")}</div><div className="text-xs">{tr("Emisă", "Issued")} {date(inv.issue_date)} · {tr("Scadentă", "Due")} {date(inv.due_date)} · <Link className="text-primary" to={`/work-orders/${inv.work_order_id}`}>{inv.work_order_number}</Link></div></div>
          </div>
          <table className="w-full text-sm"><thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
            <th className="py-2">#</th><th>{tr("Denumire", "Description")}</th><th className="text-right">{tr("Cant.", "Qty")}</th><th className="text-right">{tr("Preț", "Price")}</th><th className="text-right">{tr("Valoare", "Net")}</th><th className="text-right">TVA</th>
          </tr></thead><tbody>
            {inv.lines.map((l, i) => (
              <tr key={l.id} className="h-9 border-b border-border/50"><td className="font-mono text-xs">{i + 1}</td><td>{l.description} <span className="font-mono text-[11px] text-muted-foreground">{l.code}</span></td>
                <td className="text-right font-mono">{num(l.qty)} {l.unit}</td><td className="text-right font-mono">{money(l.unit_price)}</td><td className="text-right font-mono">{money(l.net)}</td><td className="text-right font-mono">{money(l.vat)}</td></tr>
            ))}
          </tbody></table>
          <div className="ml-auto mt-4 grid max-w-xs gap-1 text-sm">
            <div className="flex justify-between"><span>{tr("Total fără TVA", "Net")}</span><span className="font-mono">{money(inv.totals.net)}</span></div>
            <div className="flex justify-between"><span>TVA</span><span className="font-mono">{money(inv.totals.vat)}</span></div>
            <div className="flex justify-between border-t pt-1 text-base font-bold"><span>Total</span><span className="font-mono text-primary" data-testid="invoice-total">{money(inv.totals.gross)}</span></div>
            {fiscal && <div className="flex justify-between text-muted-foreground"><span>{tr("Încasat", "Paid")}</span><span className="font-mono" data-testid="invoice-paid">{money(inv.paid_amount)}</span></div>}
          </div>
        </Panel>
        <div className="space-y-4">
          {fiscal && <EfacturaPanel inv={inv} setData={setData} reload={reload} />}
          {fiscal && (
            <Panel title={tr("Încasări", "Payments")}>
              {inv.payments.map((p) => (
                <div key={p.id} className="flex items-center justify-between border-b border-border/50 py-2 text-sm">
                  <div><div className="font-mono text-xs">{p.doc_number}</div><div className="text-[11px] text-muted-foreground">{tr(...DOCS[p.doc_type])} · {dt(p.date)}</div></div>
                  <div className="flex items-center gap-2"><span className="font-mono">{money(p.amount)}</span>
                    <Button variant="ghost" size="icon" data-testid={`print-receipt-${p.doc_number}`} onClick={() => window.open(`/print/receipt/${p.id}`, "_blank")}><Printer className="h-4 w-4" /></Button></div>
                </div>
              ))}
              {!inv.payments.length && <div className="text-sm text-muted-foreground">—</div>}
            </Panel>
          )}
        </div>
      </div>
      {fiscal && <PayDialog key={inv.paid_amount} inv={inv} open={pay} onOpenChange={setPay} onSaved={reload} />}
    </div>
  );
}
