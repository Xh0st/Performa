import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { LayoutGrid, List, Search, User } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, date } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Panel, Loading, StatusBadge, STATUS } from "@/components/common";

const COLS = ["noua", "diagnosticare", "asteapta_oferta", "aprobata", "asteapta_piese", "in_lucru", "finalizata", "facturata"];

function Card({ w }) {
  return (
    <Link to={`/work-orders/${w.id}`} draggable onDragStart={(e) => e.dataTransfer.setData("text/plain", w.id)} data-testid={`kanban-card-${w.number}`}
      className="block rounded border bg-background p-3 transition-transform duration-150 hover:-translate-y-0.5 hover:border-primary/60">
      <div className="flex items-center justify-between"><span className="font-mono text-[11px] font-semibold text-primary">{w.number}</span>
        <span className="rounded-sm border px-1.5 font-mono text-[10px]">{w.vehicle.plate}</span></div>
      <div className="mt-1 truncate text-sm font-semibold">{w.vehicle.make} {w.vehicle.model}</div>
      <div className="truncate text-xs text-muted-foreground">{w.client_name}</div>
      <div className="mt-2 line-clamp-2 text-xs">{w.complaint}</div>
      <div className="mt-2 flex items-center justify-between border-t pt-2 text-[11px]">
        <span className="flex items-center gap-1 truncate text-muted-foreground"><User className="h-3 w-3" />{w.mechanic_names.join(", ") || "—"}</span>
        <span className="font-mono font-semibold">{money(w.totals.gross)}</span>
      </div>
    </Link>
  );
}

export default function WorkOrders() {
  const { tr } = useLang();
  const nav = useNavigate();
  const [view, setView] = useState("kanban");
  const [q, setQ] = useState("");
  const { data, reload } = useApi(view === "kanban" ? "/work-orders?active=true" : "/work-orders", [view]);
  const rows = (data || []).filter((w) => !q || `${w.number} ${w.vehicle.plate} ${w.client_name} ${w.vehicle.make}`.toLowerCase().includes(q.toLowerCase()));

  const drop = async (e, status) => {
    e.preventDefault();
    const id = e.dataTransfer.getData("text/plain");
    const w = rows.find((x) => x.id === id);
    if (!w || w.status === status) return;
    try {
      await api.post(`/work-orders/${id}/status`, { status, note: "Kanban" });
      toast.success(tr("Status actualizat", "Status updated"));
      reload();
    } catch (err) {
      toast.error(errMsg(err));
    }
  };

  return (
    <div data-testid="work-orders-page">
      <PageHeader eyebrow={tr("Recepție → Deviz → Aprobare → Lucrări → CC → Facturare → Livrare", "Reception → Quote → Approval → Work → QC → Invoice → Delivery")}
        title={tr("Comenzi de lucru", "Work orders")}
        actions={<>
          <div className="relative"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input data-testid="work-orders-search-input" className="w-56 pl-9" placeholder={tr("Caută…", "Search…")} value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <Button variant={view === "kanban" ? "default" : "outline"} size="icon" data-testid="view-kanban-button" onClick={() => setView("kanban")}><LayoutGrid className="h-4 w-4" /></Button>
          <Button variant={view === "list" ? "default" : "outline"} size="icon" data-testid="view-list-button" onClick={() => setView("list")}><List className="h-4 w-4" /></Button>
        </>} />
      {!data ? <Loading /> : view === "kanban" ? (
        <div className="flex gap-3 overflow-x-auto pb-4" data-testid="kanban-board">
          {COLS.filter((c) => c !== "facturata").map((c) => {
            const items = rows.filter((w) => w.status === c);
            return (
              <div key={c} data-testid={`kanban-col-${c}`} onDragOver={(e) => e.preventDefault()} onDrop={(e) => drop(e, c)} className="w-64 shrink-0 rounded-md border bg-card/60">
                <div className="flex items-center justify-between border-b px-3 py-2">
                  <StatusBadge status={c} /><span className="font-mono text-xs text-muted-foreground">{items.length}</span>
                </div>
                <div className="min-h-[200px] space-y-2 p-2">{items.map((w) => <Card key={w.id} w={w} />)}</div>
              </div>
            );
          })}
        </div>
      ) : (
        <Panel>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="work-orders-table">
              <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">{tr("Număr", "Number")}</th><th className="px-2">{tr("Data", "Date")}</th><th className="px-2">{tr("Vehicul", "Vehicle")}</th>
                <th className="px-2">Client</th><th className="px-2">{tr("Mecanici", "Mechanics")}</th><th className="px-2 text-right">Total</th><th className="px-2 text-right">Status</th>
              </tr></thead>
              <tbody>
                {rows.map((w) => (
                  <tr key={w.id} onClick={() => nav(`/work-orders/${w.id}`)} className="h-10 cursor-pointer border-b border-border/50 hover:bg-accent/60">
                    <td className="px-2 font-mono text-xs text-primary">{w.number}</td><td className="px-2">{date(w.created_at)}</td>
                    <td className="px-2"><span className="font-mono text-xs">{w.vehicle.plate}</span> · {w.vehicle.make} {w.vehicle.model}</td>
                    <td className="px-2">{w.client_name}</td><td className="px-2 text-xs text-muted-foreground">{w.mechanic_names.join(", ")}</td>
                    <td className="px-2 text-right font-mono">{money(w.totals.gross)}</td><td className="px-2 text-right"><StatusBadge status={w.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <p className="mt-2 text-xs text-muted-foreground">{tr(`Trageți cardurile între coloane pentru a schimba statusul. ${STATUS.facturata[0]} se setează automat la emiterea facturii.`,
        "Drag cards between columns to change status. Invoiced is set automatically when the invoice is issued.")}</p>
    </div>
  );
}
