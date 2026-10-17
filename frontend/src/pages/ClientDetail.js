import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Pencil, Plus, Car } from "lucide-react";
import { useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, date, num } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageHeader, Panel, Loading, StatusBadge, Badge, PAY_STATUS, Empty } from "@/components/common";
import ClientForm from "@/components/ClientForm";
import VehicleForm from "@/components/VehicleForm";

function Info({ label, value, mono }) {
  return (
    <div><div className="eyebrow">{label}</div><div className={`mt-0.5 text-sm ${mono ? "font-mono" : ""}`}>{value || "—"}</div></div>
  );
}

export default function ClientDetail() {
  const { id } = useParams();
  const { tr } = useLang();
  const { data: c, reload } = useApi(`/clients/${id}`);
  const [edit, setEdit] = useState(false);
  const [addV, setAddV] = useState(false);
  if (!c) return <Loading />;
  const totalInv = c.invoices.filter((i) => i.type === "fiscal").reduce((s, i) => s + i.totals.gross, 0);
  const due = c.invoices.filter((i) => i.type === "fiscal").reduce((s, i) => s + i.totals.gross - i.paid_amount, 0);
  return (
    <div data-testid="client-detail-page">
      <PageHeader eyebrow={c.type === "pj" ? tr("Persoană juridică", "Company") : tr("Persoană fizică", "Individual")} title={c.name} testid="client-detail-name"
        actions={<Button variant="outline" data-testid="edit-client-button" onClick={() => setEdit(true)}><Pencil className="mr-1 h-4 w-4" />{tr("Editează", "Edit")}</Button>} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title={tr("Date client", "Client data")}>
          <div className="grid grid-cols-2 gap-4">
            {c.type === "pj" ? (<><Info label="CUI" value={c.cui} mono /><Info label="Reg. Com." value={c.reg_com} mono /><Info label={tr("Reprezentant", "Representative")} value={c.representative} /></>)
              : <Info label="CNP" value={c.cnp} mono />}
            <Info label={tr("Telefon", "Phone")} value={c.phone} mono /><Info label="Email" value={c.email} />
            <Info label={tr("Adresă", "Address")} value={[c.address, c.city].filter(Boolean).join(", ") + (c.county ? ` (${c.county})` : "")} />
            <Info label="GDPR" value={c.gdpr_consent ? tr("Acord dat", "Consented") : tr("Fără acord", "No consent")} />
            {c.is_fleet && <Info label={tr("Limită buget", "Budget limit")} value={money(c.budget_limit)} mono />}
          </div>
        </Panel>
        <Panel title={tr("Sumar financiar", "Financial summary")}>
          <div className="grid grid-cols-2 gap-4">
            <Info label={tr("Total facturat", "Total invoiced")} value={money(totalInv)} mono />
            <Info label={tr("Sold restant", "Outstanding")} value={money(due)} mono />
            <Info label={tr("Comenzi", "Orders")} value={c.work_orders.length} mono />
            <Info label={tr("Vehicule", "Vehicles")} value={c.vehicles.length} mono />
          </div>
        </Panel>
        <Panel title={tr("Vehicule", "Vehicles")} actions={<Button size="sm" variant="outline" data-testid="client-add-vehicle-button" onClick={() => setAddV(true)}><Plus className="h-4 w-4" /></Button>}>
          <div className="space-y-2">
            {c.vehicles.map((v) => (
              <div key={v.id} className="flex items-center gap-3 rounded border px-3 py-2">
                <Car className="h-4 w-4 text-primary" />
                <div className="min-w-0 flex-1"><div className="text-sm font-medium">{v.make} {v.model} · {v.year}</div><div className="truncate font-mono text-[11px] text-muted-foreground">{v.vin}</div></div>
                <span className="rounded-sm border bg-background px-2 py-0.5 font-mono text-xs">{v.plate}</span>
              </div>
            ))}
            {!c.vehicles.length && <Empty text={tr("Fără vehicule", "No vehicles")} />}
          </div>
        </Panel>
      </div>
      <Tabs defaultValue="wo" className="mt-6">
        <TabsList><TabsTrigger value="wo" data-testid="client-tab-orders">{tr("Istoric reparații", "Repair history")}</TabsTrigger><TabsTrigger value="inv" data-testid="client-tab-invoices">{tr("Facturi", "Invoices")}</TabsTrigger></TabsList>
        <TabsContent value="wo">
          <Panel>
            <table className="w-full text-sm"><tbody>
              {c.work_orders.map((w) => (
                <tr key={w.id} className="h-10 border-b border-border/50">
                  <td><Link className="font-mono text-primary hover:underline" to={`/work-orders/${w.id}`}>{w.number}</Link></td>
                  <td>{date(w.created_at)}</td><td className="font-mono text-xs">{num(w.mileage_in, 0)} km</td><td className="max-w-xs truncate">{w.complaint}</td><td className="text-right"><StatusBadge status={w.status} /></td>
                </tr>
              ))}
            </tbody></table>
            {!c.work_orders.length && <Empty text="—" />}
          </Panel>
        </TabsContent>
        <TabsContent value="inv">
          <Panel>
            <table className="w-full text-sm"><tbody>
              {c.invoices.map((i) => (
                <tr key={i.id} className="h-10 border-b border-border/50">
                  <td><Link className="font-mono text-primary hover:underline" to={`/invoices/${i.id}`}>{i.series}{i.number}</Link></td>
                  <td className="uppercase text-xs">{i.type}</td><td>{date(i.issue_date)}</td><td className="text-right font-mono">{money(i.totals.gross)}</td>
                  <td className="text-right"><Badge map={PAY_STATUS} value={i.status} /></td>
                </tr>
              ))}
            </tbody></table>
            {!c.invoices.length && <Empty text="—" />}
          </Panel>
        </TabsContent>
      </Tabs>
      <ClientForm open={edit} onOpenChange={setEdit} initial={c} onSaved={reload} />
      <VehicleForm open={addV} onOpenChange={setAddV} clientId={id} onSaved={reload} />
    </div>
  );
}
