import { useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Search, Pencil } from "lucide-react";
import { api, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { date, num } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { PageHeader, Panel, Loading, Empty, StatusBadge } from "@/components/common";
import VehicleForm from "@/components/VehicleForm";
import { PaginationControls, usePagination } from "@/components/Pagination";

const todayS = () => new Date().toISOString().slice(0, 10);
function Exp({ label, d }) {
  if (!d) return null;
  const soon = d <= new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
  const past = d < todayS();
  return <span className={`rounded-sm border px-1.5 py-0.5 font-mono text-[10px] ${past ? "border-rose-500/40 text-rose-500" : soon ? "border-yellow-500/40 text-yellow-500" : "text-muted-foreground"}`}>{label} {date(d)}</span>;
}

export default function Vehicles() {
  const { tr } = useLang();
  const [q, setQ] = useState("");
  const [form, setForm] = useState({ open: false, initial: null });
  const [detail, setDetail] = useState(null);
  const { data, loading, reload } = useApi(`/vehicles?q=${encodeURIComponent(q)}`, [q]);
  const openDetail = async (id) => setDetail((await api.get(`/vehicles/${id}`)).data);
  const pagination = usePagination(data || [], `${q}:${data?.length || 0}`);
  return (
    <div data-testid="vehicles-page">
      <PageHeader eyebrow={tr("Parc auto clienți", "Client fleet")} title={tr("Vehicule", "Vehicles")}
        actions={<Button data-testid="add-vehicle-button" onClick={() => setForm({ open: true, initial: null })}><Plus className="mr-1 h-4 w-4" />{tr("Vehicul nou", "New vehicle")}</Button>} />
      <Panel>
        <div className="relative mb-4">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input data-testid="vehicles-search-input" className="pl-9" placeholder={tr("Caută VIN, nr. înmatriculare, marcă…", "Search VIN, plate, make…")} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {loading && !data ? <Loading /> : !data?.length ? <Empty text={tr("Niciun vehicul.", "No vehicles.")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="vehicles-table">
              <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">{tr("Nr.", "Plate")}</th><th className="px-2">VIN</th><th className="px-2">{tr("Vehicul", "Vehicle")}</th><th className="px-2">{tr("Motor", "Engine")}</th>
                <th className="px-2">{tr("Proprietar", "Owner")}</th><th className="px-2 text-right">Km</th><th className="px-2">{tr("Expirări", "Expiry")}</th>
              </tr></thead>
              <tbody>
                {pagination.pageItems.map((v) => (
                  <tr key={v.id} data-testid={`vehicle-row-${v.id}`} onClick={() => openDetail(v.id)} className="h-10 cursor-pointer border-b border-border/50 hover:bg-accent/60">
                    <td className="px-2"><span className="rounded-sm border bg-background px-2 py-0.5 font-mono text-xs font-semibold">{v.plate}</span></td>
                    <td className="px-2 font-mono text-xs">{v.vin}</td>
                    <td className="px-2 font-medium">{v.make} {v.model} <span className="text-muted-foreground">· {v.year}</span></td>
                    <td className="px-2 text-xs text-muted-foreground">{v.engine} · {v.power_kw} kW · {v.fuel} · E{v.euro}</td>
                    <td className="px-2">{v.client_name}</td><td className="px-2 text-right font-mono">{num(v.mileage, 0)}</td>
                    <td className="px-2"><div className="flex flex-wrap gap-1"><Exp label="ITP" d={v.itp_expiry} /><Exp label="RCA" d={v.rca_expiry} /></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <PaginationControls {...pagination} total={data?.length || 0} testid="vehicles-pagination" />
      </Panel>
      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl" data-testid="vehicle-detail-sheet">
          {detail && (
            <>
              <SheetHeader><SheetTitle className="font-heading text-2xl uppercase">{detail.make} {detail.model}</SheetTitle></SheetHeader>
              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                {[["VIN", detail.vin], [tr("Nr.", "Plate"), detail.plate], [tr("An", "Year"), detail.year], [tr("Motor", "Engine"), detail.engine],
                  [tr("Putere", "Power"), `${detail.power_kw} kW`], ["Euro", detail.euro], [tr("Combustibil", "Fuel"), detail.fuel], ["Km", num(detail.mileage, 0)],
                  [tr("Proprietar", "Owner"), detail.client_name], ["ITP", date(detail.itp_expiry)], ["RCA", date(detail.rca_expiry)], ["CASCO", date(detail.casco_expiry)],
                  [tr("Rovinietă", "Vignette"), date(detail.rovinieta_expiry)]].map(([l, v]) => (
                  <div key={l}><div className="eyebrow">{l}</div><div className="font-mono text-xs">{v || "—"}</div></div>
                ))}
              </div>
              <Button variant="outline" size="sm" className="mt-4" data-testid="edit-vehicle-button" onClick={() => { setForm({ open: true, initial: detail }); setDetail(null); }}>
                <Pencil className="mr-1 h-3 w-3" />{tr("Editează", "Edit")}
              </Button>
              <h4 className="mt-6 font-heading text-lg font-bold uppercase">{tr("Istoric intervenții", "Service history")}</h4>
              <div className="mt-2 space-y-2">
                {detail.history.map((w) => (
                  <Link key={w.id} to={`/work-orders/${w.id}`} className="block rounded border p-3 hover:border-primary/60">
                    <div className="flex items-center justify-between"><span className="font-mono text-xs text-primary">{w.number}</span><StatusBadge status={w.status} /></div>
                    <div className="mt-1 text-sm">{w.complaint}</div>
                    <div className="mt-1 font-mono text-[11px] text-muted-foreground">{date(w.created_at)} · {num(w.mileage_in, 0)} km · {w.lines?.length || 0} {tr("poziții", "items")}</div>
                  </Link>
                ))}
                {!detail.history.length && <Empty text="—" />}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
      <VehicleForm open={form.open} onOpenChange={(o) => setForm({ ...form, open: o })} initial={form.initial} onSaved={reload} />
    </div>
  );
}
