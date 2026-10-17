import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, num } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, NativeSelect, LABOR_CATS, Empty } from "@/components/common";

const TYPE = { part: ["Piesă", "Part"], labor: ["Manoperă", "Labor"], consumable: ["Consumabil", "Consumable"] };

function AddLine({ wo, onChange }) {
  const { tr } = useLang();
  const { data: products } = useApi("/products");
  const { data: mechanics } = useApi("/mechanics");
  const { data: settings } = useApi("/settings");
  const blank = { type: "part", product_id: "", description: "", qty: 1, unit_price: "", discount: 0, labor_category: "mecanic_senior", norm_source: "Autodata", mechanic_id: "" };
  const [f, setF] = useState(blank);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const isLabor = f.type === "labor";
  const rate = settings?.labor_rates?.[f.labor_category];

  const add = async () => {
    try {
      const body = { ...f, qty: Number(f.qty), discount: Number(f.discount) || 0, unit_price: f.unit_price === "" ? null : Number(f.unit_price) };
      onChange((await api.post(`/work-orders/${wo.id}/lines`, body)).data);
      setF({ ...blank, type: f.type });
      toast.success(tr("Poziție adăugată", "Line added"));
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <div className="mb-4 grid gap-3 rounded border bg-muted/30 p-3 md:grid-cols-12">
      <Field label={tr("Tip", "Type")} className="md:col-span-2">
        <NativeSelect data-testid="line-type-select" value={f.type} onChange={set("type")}>
          {Object.entries(TYPE).map(([k, v]) => <option key={k} value={k}>{tr(v[0], v[1])}</option>)}
        </NativeSelect>
      </Field>
      {isLabor ? (
        <>
          <Field label={tr("Operațiune", "Operation")} className="md:col-span-3"><Input data-testid="line-description-input" value={f.description} onChange={set("description")} /></Field>
          <Field label={tr("Categorie tarif", "Rate category")} className="md:col-span-2">
            <NativeSelect data-testid="line-labor-category-select" value={f.labor_category} onChange={set("labor_category")}>
              {Object.entries(LABOR_CATS).map(([k, v]) => <option key={k} value={k}>{tr(v[0], v[1])} · {settings?.labor_rates?.[k]} RON/h</option>)}
            </NativeSelect>
          </Field>
          <Field label={tr("Normă", "Norm")} className="md:col-span-1">
            <NativeSelect data-testid="line-norm-source-select" value={f.norm_source} onChange={set("norm_source")}>{["RAR", "Autodata", "HaynesPro", "Manual"].map((x) => <option key={x}>{x}</option>)}</NativeSelect>
          </Field>
          <Field label={tr("Ore normate", "Norm hours")} className="md:col-span-1"><Input data-testid="line-qty-input" type="number" step="0.1" value={f.qty} onChange={set("qty")} /></Field>
          <Field label={tr("Mecanic", "Mechanic")} className="md:col-span-2">
            <NativeSelect data-testid="line-mechanic-select" value={f.mechanic_id} onChange={set("mechanic_id")}>
              <option value="">—</option>{(mechanics || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </NativeSelect>
          </Field>
        </>
      ) : (
        <>
          <Field label={tr("Produs din stoc", "Stock product")} className="md:col-span-4">
            <NativeSelect data-testid="line-product-select" value={f.product_id} onChange={set("product_id")}>
              <option value="">{tr("— articol liber —", "— free item —")}</option>
              {(products || []).map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name} · {money(p.sale_price)} · stoc {num(p.stock_qty)}</option>)}
            </NativeSelect>
          </Field>
          {!f.product_id && <Field label={tr("Descriere", "Description")} className="md:col-span-2"><Input data-testid="line-description-input" value={f.description} onChange={set("description")} /></Field>}
          <Field label={tr("Cantitate", "Qty")} className="md:col-span-1"><Input data-testid="line-qty-input" type="number" value={f.qty} onChange={set("qty")} /></Field>
          <Field label={tr("Preț unitar", "Unit price")} className="md:col-span-1"><Input data-testid="line-price-input" type="number" placeholder="auto" value={f.unit_price} onChange={set("unit_price")} /></Field>
          <Field label={tr("Disc. %", "Disc. %")} className="md:col-span-1"><Input data-testid="line-discount-input" type="number" value={f.discount} onChange={set("discount")} /></Field>
        </>
      )}
      <div className="flex items-end md:col-span-1">
        <Button data-testid="add-line-button" className="w-full" onClick={add}><Plus className="h-4 w-4" /></Button>
      </div>
      {isLabor && <div className="text-xs text-muted-foreground md:col-span-12">{tr("Calcul", "Calc")}: {f.qty} h × {rate} RON = <span className="font-mono">{money((Number(f.qty) || 0) * (rate || 0))}</span> {tr("fără TVA", "excl. VAT")}</div>}
    </div>
  );
}

export default function LinesTab({ wo, onChange, locked }) {
  const { tr } = useLang();
  const del = async (lid) => {
    try {
      onChange((await api.delete(`/work-orders/${wo.id}/lines/${lid}`)).data);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const t = wo.totals;
  return (
    <div>
      {!locked && <AddLine wo={wo} onChange={onChange} />}
      {!wo.lines.length ? <Empty text={tr("Nicio poziție. Adăugați piese și manoperă.", "No lines. Add parts and labor.")} /> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="wo-lines-table">
            <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
              <th className="px-2 py-2">{tr("Tip", "Type")}</th><th className="px-2">Cod</th><th className="px-2">{tr("Descriere", "Description")}</th>
              <th className="px-2 text-right">{tr("Cant.", "Qty")}</th><th className="px-2 text-right">{tr("Preț", "Price")}</th><th className="px-2 text-right">Disc.</th>
              <th className="px-2 text-right">{tr("Valoare", "Net")}</th><th className="px-2 text-right">TVA</th><th />
            </tr></thead>
            <tbody>
              {wo.lines.map((l, i) => (
                <tr key={l.id} className="h-10 border-b border-border/50">
                  <td className="px-2"><span className={`text-[11px] font-bold uppercase ${l.type === "labor" ? "text-cyan-500" : "text-primary"}`}>{tr(...TYPE[l.type])}</span></td>
                  <td className="px-2 font-mono text-xs">{l.code}</td>
                  <td className="px-2">{l.description}{l.type === "labor" && <span className="ml-2 text-[11px] text-muted-foreground">({tr(...(LABOR_CATS[l.labor_category] || ["", ""]))} · {l.norm_source})</span>}</td>
                  <td className="px-2 text-right font-mono">{num(l.qty)} {l.unit}</td><td className="px-2 text-right font-mono">{money(l.unit_price)}</td>
                  <td className="px-2 text-right font-mono">{l.discount || 0}%</td><td className="px-2 text-right font-mono">{money(t && wo.totals ? (l.qty * l.unit_price * (1 - (l.discount || 0) / 100)) : 0)}</td>
                  <td className="px-2 text-right font-mono text-muted-foreground">{l.vat_rate}%</td>
                  <td className="px-2 text-right">{!locked && <Button variant="ghost" size="icon" data-testid={`delete-line-${i}`} onClick={() => del(l.id)}><Trash2 className="h-4 w-4 text-rose-500" /></Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-4 ml-auto grid max-w-xs gap-1 text-sm" data-testid="wo-totals">
            <div className="flex justify-between"><span className="text-muted-foreground">{tr("Piese & consumabile", "Parts & consumables")}</span><span className="font-mono">{money((t.by_type.part || 0) + (t.by_type.consumable || 0))}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">{tr("Manoperă", "Labor")}</span><span className="font-mono">{money(t.by_type.labor || 0)}</span></div>
            <div className="flex justify-between border-t pt-1"><span>{tr("Total fără TVA", "Net total")}</span><span className="font-mono">{money(t.net)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">TVA</span><span className="font-mono">{money(t.vat)}</span></div>
            <div className="flex justify-between border-t pt-1 text-base font-bold"><span>Total</span><span className="font-mono text-primary" data-testid="wo-grand-total">{money(t.gross)}</span></div>
          </div>
        </div>
      )}
    </div>
  );
}
