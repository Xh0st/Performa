import { useState } from "react";
import { toast } from "sonner";
import { Plus, Search, Trash2, Printer, AlertTriangle, FileText, Undo2 } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, num, date, today } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { PageHeader, Panel, Loading, Field, NativeSelect, Empty } from "@/components/common";
import EfacturaInbox from "@/components/EfacturaInbox";
import SupplierReturnDialog from "@/components/SupplierReturnDialog";
import NirEfacturaView from "@/components/NirEfacturaView";
import { PaginationControls, usePagination } from "@/components/Pagination";

const P_EMPTY = { code: "", name: "", oe_code: "", aftermarket_code: "", brand: "", category: "piese", unit: "buc", location: "", warehouse: "Depozit Central", sale_price: 0, min_stock: 0, vat_rate: 21, warranty_months: 24 };
const createRowId = () => {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `row-${Date.now()}-${Math.random().toString(36).slice(2)}`;
};
const createNirLine = () => ({ row_id: createRowId(), product_id: "", qty: 1, unit_cost: 0, lot: "" });

function ProductDialog({ open, onOpenChange, initial, onSaved }) {
  const { tr } = useLang();
  const [f, setF] = useState(P_EMPTY);
  const [prev, setPrev] = useState(null);
  if (open && prev !== (initial || "new")) {
    setPrev(initial || "new");
    setF({ ...P_EMPTY, ...(initial || {}) });
  }
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try {
      const body = { ...f, sale_price: Number(f.sale_price), min_stock: Number(f.min_stock), vat_rate: Number(f.vat_rate), warranty_months: Number(f.warranty_months) };
      initial?.id ? await api.put(`/products/${initial.id}`, body) : await api.post("/products", body);
      toast.success(tr("Produs salvat", "Product saved"));
      onSaved();
      onOpenChange(false);
      setPrev(null);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) setPrev(null); }}>
      <DialogContent className="max-w-2xl" data-testid="product-dialog">
        <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{initial?.id ? tr("Editare produs", "Edit product") : tr("Produs nou", "New product")}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={tr("Cod produs", "Product code")}><Input data-testid="product-code-input" className="font-mono" value={f.code} onChange={set("code")} /></Field>
          <Field label={tr("Denumire", "Name")} className="sm:col-span-2"><Input data-testid="product-name-input" value={f.name} onChange={set("name")} /></Field>
          <Field label="Cod OE"><Input data-testid="product-oe-input" className="font-mono" value={f.oe_code} onChange={set("oe_code")} /></Field>
          <Field label={tr("Cod aftermarket", "Aftermarket code")}><Input className="font-mono" value={f.aftermarket_code} onChange={set("aftermarket_code")} /></Field>
          <Field label={tr("Marcă", "Brand")}><Input value={f.brand} onChange={set("brand")} /></Field>
          <Field label={tr("Locație raft", "Shelf location")}><Input data-testid="product-location-input" className="font-mono" value={f.location} onChange={set("location")} /></Field>
          <Field label={tr("Gestiune", "Warehouse")}><Input value={f.warehouse} onChange={set("warehouse")} /></Field>
          <Field label="UM"><Input value={f.unit} onChange={set("unit")} /></Field>
          <Field label={tr("Preț vânzare (fără TVA)", "Sale price (net)")}><Input data-testid="product-price-input" type="number" value={f.sale_price} onChange={set("sale_price")} /></Field>
          <Field label={tr("Stoc minim", "Min stock")}><Input data-testid="product-min-input" type="number" value={f.min_stock} onChange={set("min_stock")} /></Field>
          <Field label={tr("Garanție (luni)", "Warranty (months)")}><Input type="number" value={f.warranty_months} onChange={set("warranty_months")} /></Field>
        </div>
        <DialogFooter><Button data-testid="product-save-button" disabled={!f.code || !f.name} onClick={save}>{tr("Salvează", "Save")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NirDialog({ open, onOpenChange, onSaved }) {
  const { tr } = useLang();
  const { data: suppliers } = useApi(open ? "/suppliers" : null, [open]);
  const { data: products } = useApi(open ? "/products" : null, [open]);
  const [f, setF] = useState({ supplier_id: "", invoice_no: "", aviz_no: "", date: today(), lines: [createNirLine()] });
  const setLine = (i, k, v) => setF({ ...f, lines: f.lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)) });
  const total = f.lines.reduce((s, l) => s + Number(l.qty) * Number(l.unit_cost), 0);
  const save = async () => {
    try {
      await api.post("/nirs", {
        ...f,
        date: new Date(f.date).toISOString(),
        lines: f.lines
          .filter((line) => line.product_id)
          .map(({ row_id, ...line }) => ({
            ...line,
            qty: Number(line.qty),
            unit_cost: Number(line.unit_cost),
          })),
      });
      toast.success(tr("NIR înregistrat, stoc actualizat", "GRN saved, stock updated"));
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" data-testid="nir-dialog">
        <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{tr("Notă de intrare-recepție (NIR)", "Goods received note (NIR)")}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label={tr("Furnizor", "Supplier")} className="sm:col-span-2">
            <NativeSelect data-testid="nir-supplier-select" value={f.supplier_id} onChange={(e) => setF({ ...f, supplier_id: e.target.value })}>
              <option value="">—</option>{(suppliers || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </NativeSelect>
          </Field>
          <Field label={tr("Nr. factură", "Invoice no.")}><Input data-testid="nir-invoice-input" value={f.invoice_no} onChange={(e) => setF({ ...f, invoice_no: e.target.value })} /></Field>
          <Field label={tr("Nr. aviz", "Delivery note")}><Input value={f.aviz_no} onChange={(e) => setF({ ...f, aviz_no: e.target.value })} /></Field>
          <Field label={tr("Data recepției", "Receipt date")}><Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
        </div>
        <div className="max-h-[40vh] space-y-2 overflow-y-auto">
          {f.lines.map((l, i) => (
            <div key={l.row_id} className="grid grid-cols-12 gap-2">
              <NativeSelect data-testid={`nir-line-${i}-product`} className="col-span-6" value={l.product_id} onChange={(e) => setLine(i, "product_id", e.target.value)}>
                <option value="">—</option>{(products || []).map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
              </NativeSelect>
              <Input data-testid={`nir-line-${i}-qty`} className="col-span-2" type="number" value={l.qty} onChange={(e) => setLine(i, "qty", e.target.value)} placeholder="Cant." />
              <Input data-testid={`nir-line-${i}-cost`} className="col-span-2" type="number" value={l.unit_cost} onChange={(e) => setLine(i, "unit_cost", e.target.value)} placeholder="Cost" />
              <Input className="col-span-1" value={l.lot} onChange={(e) => setLine(i, "lot", e.target.value)} placeholder="Lot" />
              <Button variant="ghost" size="icon" className="col-span-1" onClick={() => setF({ ...f, lines: f.lines.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4 text-rose-500" /></Button>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between">
          <Button variant="outline" size="sm" data-testid="nir-add-line-button" onClick={() => setF({ ...f, lines: [...f.lines, createNirLine()] })}><Plus className="mr-1 h-3 w-3" />{tr("Linie", "Line")}</Button>
          <span className="font-mono text-sm">{tr("Total fără TVA", "Net total")}: {money(total)}</span>
        </div>
        <DialogFooter><Button data-testid="nir-save-button" disabled={!f.supplier_id} onClick={save}>{tr("Înregistrează NIR", "Save GRN")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SupplierForm({ onSaved }) {
  const { tr } = useLang();
  const [f, setF] = useState({ name: "", cui: "", phone: "", email: "" });
  const save = async () => {
    try {
      await api.post("/suppliers", f);
      setF({ name: "", cui: "", phone: "", email: "" });
      onSaved();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <div className="mb-4 grid gap-2 sm:grid-cols-5">
      {["name", "cui", "phone", "email"].map((k) => <Input key={k} data-testid={`supplier-${k}-input`} placeholder={{ name: tr("Denumire", "Name"), cui: "CUI", phone: tr("Telefon", "Phone"), email: "Email" }[k]} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />)}
      <Button data-testid="supplier-save-button" disabled={!f.name} onClick={save}><Plus className="mr-1 h-4 w-4" />{tr("Adaugă", "Add")}</Button>
    </div>
  );
}

export default function Stock() {
  const { tr } = useLang();
  const [q, setQ] = useState("");
  const [low, setLow] = useState(false);
  const [pd, setPd] = useState({ open: false, initial: null });
  const [nirOpen, setNirOpen] = useState(false);
  const [moves, setMoves] = useState(null);
  const [ret, setRet] = useState(null);
  const [efNir, setEfNir] = useState(null);
  const { data: returns, reload: reloadR } = useApi("/supplier-returns");
  const { data: products, reload } = useApi(`/products?q=${encodeURIComponent(q)}&low=${low}`, [q, low]);
  const { data: nirs, reload: reloadN } = useApi("/nirs");
  const { data: suppliers, reload: reloadS } = useApi("/suppliers");
  const value = (products || []).reduce((s, p) => s + Math.max(p.stock_qty, 0) * p.avg_cost, 0);
  const productPagination = usePagination(products || [], `${q}:${low}:${products?.length || 0}`);
  const nirPagination = usePagination(nirs || [], String(nirs?.length || 0));
  const returnPagination = usePagination(returns || [], String(returns?.length || 0));
  const openMoves = async (p) => setMoves({ p, ...(await api.get(`/products/${p.id}/moves`)).data });

  return (
    <div data-testid="stock-page">
      <PageHeader eyebrow={tr("Magazie · FIFO · loturi · multi-gestiune", "Warehouse · FIFO · lots · multi-location")} title={tr("Stocuri & NIR", "Stock & GRN")}
        actions={<>
          <Button variant="outline" data-testid="add-product-button" onClick={() => setPd({ open: true, initial: null })}><Plus className="mr-1 h-4 w-4" />{tr("Produs", "Product")}</Button>
          <Button variant="outline" data-testid="add-return-button" onClick={() => setRet({ preset: null })}><Undo2 className="mr-1 h-4 w-4" />{tr("Retur furnizor", "Supplier return")}</Button>
          <Button data-testid="add-nir-button" onClick={() => setNirOpen(true)}><Plus className="mr-1 h-4 w-4" />NIR</Button>
        </>} />
      <Tabs defaultValue="products">
        <div className="app-scroll overflow-x-auto">
        <TabsList className="w-max">
          <TabsTrigger value="products" data-testid="stock-tab-products">{tr("Produse", "Products")}</TabsTrigger>
          <TabsTrigger value="nir" data-testid="stock-tab-nir">NIR</TabsTrigger>
          <TabsTrigger value="returns" data-testid="stock-tab-returns">{tr("Retururi furnizor", "Supplier returns")}</TabsTrigger>
          <TabsTrigger value="suppliers" data-testid="stock-tab-suppliers">{tr("Furnizori", "Suppliers")}</TabsTrigger>
          <TabsTrigger value="einbox" data-testid="stock-tab-efactura">{tr("Facturi e-Factura primite", "Received e-Invoices")}</TabsTrigger>
        </TabsList>
        </div>
        <TabsContent value="products">
          <Panel>
            <div className="mb-4 flex flex-col gap-2 sm:flex-row">
              <div className="relative flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input data-testid="stock-search-input" className="pl-9" placeholder={tr("Cod, cod OE, aftermarket, denumire…", "Code, OE, aftermarket, name…")} value={q} onChange={(e) => setQ(e.target.value)} /></div>
              <Button variant={low ? "default" : "outline"} data-testid="stock-low-filter" onClick={() => setLow(!low)}><AlertTriangle className="mr-1 h-4 w-4" />{tr("Sub stoc minim", "Below minimum")}</Button>
              <div className="flex items-center rounded border px-3 font-mono text-sm">{tr("Valoare stoc", "Stock value")}: {money(value)}</div>
            </div>
            {!products ? <Loading /> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="products-table">
                  <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-2 py-2">Cod</th><th className="px-2">{tr("Denumire", "Name")}</th><th className="px-2">Cod OE</th><th className="px-2">Aftermarket</th>
                    <th className="px-2">{tr("Raft", "Shelf")}</th><th className="px-2 text-right">Stoc</th><th className="px-2 text-right">{tr("Cost mediu", "Avg cost")}</th>
                    <th className="px-2 text-right">{tr("Preț vânzare", "Sale price")}</th><th className="px-2 text-right">{tr("Marjă", "Margin")}</th>
                  </tr></thead>
                  <tbody>
                    {productPagination.pageItems.map((p) => {
                      const lowS = p.stock_qty <= p.min_stock;
                      return (
                        <tr key={p.id} data-testid={`product-row-${p.code}`} onClick={() => openMoves(p)} className="h-10 cursor-pointer border-b border-border/50 hover:bg-accent/60">
                          <td className="px-2 font-mono text-xs text-primary">{p.code}</td><td className="px-2 font-medium">{p.name} <span className="text-xs text-muted-foreground">{p.brand}</span></td>
                          <td className="px-2 font-mono text-xs">{p.oe_code}</td><td className="px-2 font-mono text-xs">{p.aftermarket_code}</td><td className="px-2 font-mono text-xs">{p.location}</td>
                          <td className={`px-2 text-right font-mono font-semibold ${lowS ? "text-rose-500" : ""}`}>{num(p.stock_qty)}</td>
                          <td className="px-2 text-right font-mono">{money(p.avg_cost)}</td><td className="px-2 text-right font-mono">{money(p.sale_price)}</td>
                          <td className="px-2 text-right font-mono text-emerald-500">{p.sale_price ? num(((p.sale_price - p.avg_cost) / p.sale_price) * 100, 0) : 0}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <PaginationControls {...productPagination} total={products?.length || 0} testid="products-pagination" />
          </Panel>
        </TabsContent>
        <TabsContent value="nir">
          <Panel>
            {!nirs?.length ? <Empty text="—" /> : (
              <table className="w-full text-sm" data-testid="nirs-table"><thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">{tr("Număr", "Number")}</th><th className="px-2">{tr("Data", "Date")}</th><th className="px-2">{tr("Furnizor", "Supplier")}</th>
                <th className="px-2">{tr("Factură / aviz", "Invoice / note")}</th><th className="px-2 text-right">{tr("Valoare", "Value")}</th><th />
              </tr></thead><tbody>
                {nirPagination.pageItems.map((n) => (
                  <tr key={n.id} className="h-10 border-b border-border/50">
                    <td className="px-2 font-mono text-xs text-primary">{n.number}</td><td className="px-2">{date(n.date)}</td><td className="px-2">{n.supplier_name}</td>
                    <td className="px-2 font-mono text-xs">{n.invoice_no} {n.aviz_no}</td><td className="px-2 text-right font-mono">{money(n.total)}</td>
                    <td className="whitespace-nowrap px-2 text-right">
                      {n.efactura_message_id && <Button variant="ghost" size="sm" data-testid={`nir-efactura-pdf-${n.number}`} onClick={() => setEfNir(n)}><FileText className="mr-1 h-4 w-4" />PDF e-Factura</Button>}
                      <Button variant="ghost" size="icon" title={tr("Retur din acest NIR", "Return from this GRN")} data-testid={`nir-return-${n.number}`} onClick={() => setRet({ preset: n })}><Undo2 className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="icon" data-testid={`print-nir-${n.number}`} onClick={() => window.open(`/print/nir/${n.id}`, "_blank")}><Printer className="h-4 w-4" /></Button></td>
                  </tr>
                ))}
              </tbody></table>
            )}
            <PaginationControls {...nirPagination} total={nirs?.length || 0} testid="nirs-pagination" />
          </Panel>
        </TabsContent>
        <TabsContent value="returns">
          <Panel testid="supplier-returns-panel">
            {!returns?.length ? <Empty text={tr("Niciun retur înregistrat.", "No returns yet.")} /> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="returns-table"><thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-2 py-2">{tr("Număr", "Number")}</th><th className="px-2">{tr("Data", "Date")}</th><th className="px-2">{tr("Furnizor", "Supplier")}</th>
                  <th className="px-2">NIR</th><th className="px-2">{tr("Motiv", "Reason")}</th><th className="px-2 text-right">{tr("Articole", "Items")}</th><th className="px-2 text-right">{tr("Valoare", "Value")}</th><th />
                </tr></thead><tbody>
                  {returnPagination.pageItems.map((r) => (
                    <tr key={r.id} data-testid={`return-row-${r.number}`} className="h-10 border-b border-border/50">
                      <td className="px-2 font-mono text-xs text-primary">{r.number}</td><td className="px-2">{date(r.date)}</td><td className="px-2">{r.supplier_name}</td>
                      <td className="px-2 font-mono text-xs">{r.nir_number || "FIFO"}</td><td className="px-2 text-xs">{r.reason}</td>
                      <td className="px-2 text-right font-mono">{r.lines.reduce((s, l) => s + l.qty, 0)}</td><td className="px-2 text-right font-mono">{money(r.total)}</td>
                      <td className="px-2 text-right"><Button variant="ghost" size="icon" data-testid={`print-return-${r.number}`} onClick={() => window.open(`/print/return/${r.id}`, "_blank")}><Printer className="h-4 w-4" /></Button></td>
                    </tr>
                  ))}
                </tbody></table>
              </div>
            )}
            <PaginationControls {...returnPagination} total={returns?.length || 0} testid="returns-pagination" />
          </Panel>
        </TabsContent>
        <TabsContent value="einbox"><EfacturaInbox onNirChange={() => { reload(); reloadN(); reloadS(); }} /></TabsContent>
        <TabsContent value="suppliers">
          <Panel>
            <SupplierForm onSaved={reloadS} />
            <div className="grid gap-2 md:grid-cols-3">
              {(suppliers || []).map((s) => (
                <div key={s.id} className="rounded border p-3"><div className="font-medium">{s.name}</div>
                  <div className="font-mono text-xs text-muted-foreground">{s.cui || "—"} · {s.phone || "—"}</div>
                  <div className="mt-1 text-[11px] uppercase tracking-wider text-muted-foreground">{s.api_enabled ? "API activ" : tr("Import API: neconfigurat", "API import: not configured")}</div>
                </div>
              ))}
            </div>
          </Panel>
        </TabsContent>
      </Tabs>
      <ProductDialog open={pd.open} initial={pd.initial} onOpenChange={(o) => setPd({ ...pd, open: o })} onSaved={reload} />
      {ret && <SupplierReturnDialog key={ret.preset?.id || "new"} open preset={ret.preset} onOpenChange={(o) => !o && setRet(null)} onSaved={() => { reload(); reloadN(); reloadR(); }} />}
      <NirEfacturaView nir={efNir} onClose={() => setEfNir(null)} />
      <NirDialog open={nirOpen} onOpenChange={setNirOpen} onSaved={() => { reload(); reloadN(); }} />
      <Sheet open={!!moves} onOpenChange={(o) => !o && setMoves(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-lg" data-testid="product-moves-sheet">
          {moves && (
            <>
              <SheetHeader><SheetTitle className="font-heading text-2xl uppercase">{moves.p.name}</SheetTitle></SheetHeader>
              <Button size="sm" variant="outline" className="mt-2" data-testid="edit-product-button" onClick={() => { setPd({ open: true, initial: moves.p }); setMoves(null); }}>{tr("Editează", "Edit")}</Button>
              <h4 className="mt-4 eyebrow">{tr("Loturi FIFO active", "Active FIFO lots")}</h4>
              {moves.lots.map((l) => <div key={l.id} className="mt-1 flex justify-between font-mono text-xs"><span>{date(l.date)} · {l.ref}</span><span>{num(l.qty_remaining)} × {money(l.unit_cost)}</span></div>)}
              <h4 className="mt-4 eyebrow">{tr("Mișcări stoc", "Stock moves")}</h4>
              {moves.moves.map((m) => (
                <div key={m.id} className="mt-1 flex justify-between font-mono text-xs">
                  <span>{date(m.at)} · {m.ref}</span><span className={m.kind === "in" ? "text-emerald-500" : "text-rose-500"}>{m.kind === "in" ? "+" : "−"}{num(m.qty)}</span>
                </div>
              ))}
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
