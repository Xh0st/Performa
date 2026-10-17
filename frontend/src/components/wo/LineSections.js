import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Package, Wrench } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, num } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, NativeSelect, LABOR_CATS, Empty } from "@/components/common";

const lineNet = (l) => l.qty * l.unit_price * (1 - (l.discount || 0) / 100);
const TH = "px-2 py-2 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground";
const THR = `${TH} text-right`;

function useLineActions(wo, onChange) {
  const { tr } = useLang();
  const add = async (body) => {
    try {
      onChange((await api.post(`/work-orders/${wo.id}/lines`, body)).data);
      toast.success(tr("Poziție adăugată", "Line added"));
      return true;
    } catch (e) {
      toast.error(errMsg(e));
      return false;
    }
  };
  const del = async (lid) => {
    try {
      onChange((await api.delete(`/work-orders/${wo.id}/lines/${lid}`)).data);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return { add, del };
}

function SectionHead({ icon: Icon, title, count, subtotal, accent }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h4 className={`flex items-center gap-2 font-heading text-lg font-bold uppercase tracking-wide ${accent}`}><Icon className="h-4 w-4" />{title}
        <span className="font-mono text-xs text-muted-foreground">({count})</span></h4>
      <span className="font-mono text-sm">{money(subtotal)}</span>
    </div>
  );
}

function PartForm({ onAdd }) {
  const { tr } = useLang();
  const { data: products } = useApi("/products");
  const blank = { type: "part", product_id: "", description: "", qty: 1, unit_price: "", discount: 0 };
  const [f, setF] = useState(blank);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const prod = (products || []).find((p) => p.id === f.product_id);
  const submit = async () => {
    const ok = await onAdd({ ...f, qty: Number(f.qty), discount: Number(f.discount) || 0, unit_price: f.unit_price === "" ? null : Number(f.unit_price) });
    if (ok) setF({ ...blank, type: f.type });
  };
  return (
    <div className="mb-4 rounded border bg-muted/30 p-3" data-testid="part-add-form">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Field label={tr("Produs din stoc", "Stock product")} className="col-span-2 lg:col-span-3">
          <NativeSelect data-testid="part-product-select" value={f.product_id} onChange={set("product_id")}>
            <option value="">{tr("— articol liber (fără stoc) —", "— free item (no stock) —")}</option>
            {(products || []).map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name} · stoc {num(p.stock_qty)}</option>)}
          </NativeSelect>
        </Field>
        <Field label={tr("Tip", "Type")}>
          <NativeSelect data-testid="part-type-select" value={f.type} onChange={set("type")}>
            <option value="part">{tr("Piesă", "Part")}</option>
            <option value="consumable">{tr("Consumabil", "Consumable")}</option>
          </NativeSelect>
        </Field>
        <Field label={tr("Descriere", "Description")} className="col-span-2">
          <Input data-testid="part-description-input" value={f.description} onChange={set("description")}
            placeholder={prod ? prod.name : tr("obligatoriu pt. articol liber", "required for free item")} />
        </Field>
      </div>
      <div className="mt-3 grid grid-cols-2 items-end gap-3 lg:grid-cols-6">
        <Field label={tr("Cantitate", "Qty")}><Input data-testid="part-qty-input" type="number" min="0" step="any" value={f.qty} onChange={set("qty")} /></Field>
        <Field label={tr("Preț unitar fără TVA", "Unit price excl. VAT")}>
          <Input data-testid="part-price-input" type="number" value={f.unit_price} onChange={set("unit_price")} placeholder={prod ? String(prod.sale_price) : "0"} />
        </Field>
        <Field label={tr("Discount %", "Discount %")}><Input data-testid="part-discount-input" type="number" value={f.discount} onChange={set("discount")} /></Field>
        <div className="col-span-2 pb-2 text-xs text-muted-foreground lg:col-span-2">
          {prod && <>{tr("Raft", "Shelf")} <span className="font-mono">{prod.location || "—"}</span> · OE <span className="font-mono">{prod.oe_code || "—"}</span> · {tr("preț listă", "list price")} <span className="font-mono">{money(prod.sale_price)}</span></>}
        </div>
        <Button data-testid="add-part-button" onClick={submit} disabled={!f.product_id && !f.description}><Plus className="mr-1 h-4 w-4" />{tr("Adaugă piesă", "Add part")}</Button>
      </div>
    </div>
  );
}

export function PartsSection({ wo, onChange, locked }) {
  const { tr } = useLang();
  const { add, del } = useLineActions(wo, onChange);
  const lines = wo.lines.filter((l) => l.type !== "labor");
  return (
    <section data-testid="parts-section">
      <SectionHead icon={Package} title={tr("Piese & consumabile", "Parts & consumables")} count={lines.length} accent="text-primary"
        subtotal={lines.reduce((s, l) => s + lineNet(l), 0)} />
      {!locked && <PartForm onAdd={add} />}
      {!lines.length ? <Empty text={tr("Nicio piesă adăugată.", "No parts added.")} /> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="parts-table">
            <thead><tr className="border-b">
              <th className={TH}>Cod</th><th className={TH}>{tr("Denumire", "Name")}</th><th className={TH}>{tr("Tip", "Type")}</th><th className={THR}>{tr("Cant.", "Qty")}</th>
              <th className={THR}>{tr("Preț unitar", "Unit price")}</th><th className={THR}>Disc.</th><th className={THR}>{tr("Valoare", "Net")}</th><th className="w-10" />
            </tr></thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={l.id} className="h-10 border-b border-border/50" data-testid={`part-row-${i}`}>
                  <td className="px-2 font-mono text-xs">{l.code || "—"}</td><td className="px-2">{l.description}</td>
                  <td className="px-2 text-xs text-muted-foreground">{l.type === "part" ? tr("Piesă", "Part") : tr("Consumabil", "Consumable")}</td>
                  <td className="px-2 text-right font-mono">{num(l.qty)} {l.unit}</td><td className="px-2 text-right font-mono">{money(l.unit_price)}</td>
                  <td className="px-2 text-right font-mono">{l.discount || 0}%</td><td className="px-2 text-right font-mono font-semibold">{money(lineNet(l))}</td>
                  <td className="px-2 text-right">{!locked && <Button variant="ghost" size="icon" data-testid={`delete-part-${i}`} onClick={() => del(l.id)}><Trash2 className="h-4 w-4 text-rose-500" /></Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function LaborForm({ onAdd, mechanics, rates }) {
  const { tr } = useLang();
  const blank = { type: "labor", description: "", labor_category: "mecanic_senior", norm_source: "Autodata", qty: 1, mechanic_id: "", discount: 0, unit_price: null };
  const [f, setF] = useState(blank);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const rate = rates?.[f.labor_category] || 0;
  const submit = async () => {
    const ok = await onAdd({ ...f, qty: Number(f.qty) });
    if (ok) setF({ ...blank, labor_category: f.labor_category, mechanic_id: f.mechanic_id });
  };
  return (
    <div className="mb-4 rounded border bg-muted/30 p-3" data-testid="labor-add-form">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Field label={tr("Operațiune", "Operation")} className="col-span-2 lg:col-span-3">
          <Input data-testid="labor-description-input" value={f.description} onChange={set("description")} placeholder={tr("ex. Înlocuire kit distribuție", "e.g. Timing belt replacement")} />
        </Field>
        <Field label={tr("Categorie tarif", "Rate category")} className="col-span-2 lg:col-span-1">
          <NativeSelect data-testid="labor-category-select" value={f.labor_category} onChange={set("labor_category")}>
            {Object.entries(LABOR_CATS).map(([k, v]) => <option key={k} value={k}>{tr(v[0], v[1])}</option>)}
          </NativeSelect>
        </Field>
        <Field label={tr("Mecanic", "Mechanic")} className="col-span-2">
          <NativeSelect data-testid="labor-mechanic-select" value={f.mechanic_id} onChange={set("mechanic_id")}>
            <option value="">—</option>{(mechanics || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </NativeSelect>
        </Field>
      </div>
      <div className="mt-3 grid grid-cols-2 items-end gap-3 lg:grid-cols-6">
        <Field label={tr("Sursă normă", "Norm source")}>
          <NativeSelect data-testid="labor-norm-select" value={f.norm_source} onChange={set("norm_source")}>{["RAR", "Autodata", "HaynesPro", "Manual"].map((x) => <option key={x}>{x}</option>)}</NativeSelect>
        </Field>
        <Field label={tr("Ore normate", "Norm hours")}><Input data-testid="labor-hours-input" type="number" min="0" step="0.1" value={f.qty} onChange={set("qty")} /></Field>
        <Field label={tr("Tarif (RON/oră)", "Rate (RON/h)")}><div className="flex h-9 items-center rounded-md border bg-background px-3 font-mono text-sm text-muted-foreground">{num(rate)}</div></Field>
        <div className="col-span-2 pb-2 text-sm lg:col-span-2">
          {tr("Valoare", "Amount")}: <span className="font-mono font-semibold" data-testid="labor-calc">{num(f.qty)} h × {num(rate)} = {money((Number(f.qty) || 0) * rate)}</span>
        </div>
        <Button data-testid="add-labor-button" onClick={submit} disabled={!f.description || !(Number(f.qty) > 0)}><Plus className="mr-1 h-4 w-4" />{tr("Adaugă manoperă", "Add labor")}</Button>
      </div>
    </div>
  );
}

export function LaborSection({ wo, onChange, locked }) {
  const { tr } = useLang();
  const { add, del } = useLineActions(wo, onChange);
  const { data: mechanics } = useApi("/mechanics");
  const { data: settings } = useApi("/settings");
  const names = Object.fromEntries((mechanics || []).map((m) => [m.id, m.name]));
  const lines = wo.lines.filter((l) => l.type === "labor");
  return (
    <section data-testid="labor-section">
      <SectionHead icon={Wrench} title={tr("Manoperă", "Labor")} count={lines.length} accent="text-cyan-500"
        subtotal={lines.reduce((s, l) => s + lineNet(l), 0)} />
      {!locked && <LaborForm onAdd={add} mechanics={mechanics} rates={settings?.labor_rates} />}
      {!lines.length ? <Empty text={tr("Nicio operațiune de manoperă.", "No labor operations.")} /> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="labor-table">
            <thead><tr className="border-b">
              <th className={TH}>{tr("Operațiune", "Operation")}</th><th className={TH}>{tr("Categorie", "Category")}</th><th className={TH}>{tr("Normă", "Norm")}</th>
              <th className={TH}>{tr("Mecanic", "Mechanic")}</th><th className={THR}>{tr("Ore", "Hours")}</th><th className={THR}>{tr("Tarif", "Rate")}</th>
              <th className={THR}>{tr("Valoare", "Net")}</th><th className="w-10" />
            </tr></thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={l.id} className="h-10 border-b border-border/50" data-testid={`labor-row-${i}`}>
                  <td className="px-2">{l.description}</td><td className="px-2 text-xs">{tr(...(LABOR_CATS[l.labor_category] || ["—", "—"]))}</td>
                  <td className="px-2 text-xs text-muted-foreground">{l.norm_source}</td><td className="px-2 text-xs">{names[l.mechanic_id] || "—"}</td>
                  <td className="px-2 text-right font-mono">{num(l.qty)}</td><td className="px-2 text-right font-mono">{money(l.unit_price)}</td>
                  <td className="px-2 text-right font-mono font-semibold">{money(lineNet(l))}</td>
                  <td className="px-2 text-right">{!locked && <Button variant="ghost" size="icon" data-testid={`delete-labor-${i}`} onClick={() => del(l.id)}><Trash2 className="h-4 w-4 text-rose-500" /></Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function TotalsBar({ wo }) {
  const { tr } = useLang();
  const t = wo.totals;
  const items = [
    [tr("Piese & consumabile", "Parts & consumables"), (t.by_type.part || 0) + (t.by_type.consumable || 0)],
    [tr("Manoperă", "Labor"), t.by_type.labor || 0],
    [tr("Total fără TVA", "Net total"), t.net],
    ["TVA", t.vat],
  ];
  return (
    <div className="mb-3 grid grid-cols-2 gap-2 rounded border bg-card p-3 md:grid-cols-5" data-testid="wo-totals">
      {items.map(([l, v]) => <div key={l}><div className="eyebrow">{l}</div><div className="font-mono text-sm">{money(v)}</div></div>)}
      <div><div className="eyebrow">Total</div><div className="font-mono text-lg font-bold text-primary" data-testid="wo-grand-total">{money(t.gross)}</div></div>
    </div>
  );
}
