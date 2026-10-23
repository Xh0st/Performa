import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search, Building2, User } from "lucide-react";
import { useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Panel, Loading, Empty } from "@/components/common";
import ClientForm from "@/components/ClientForm";
import { PAGE_SIZE, PaginationControls, useServerPagination } from "@/components/Pagination";

export default function Clients() {
  const { tr } = useLang();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [open, setOpen] = useState(false);
  const pagination = useServerPagination(`${q}:${type}`);
  const params = new URLSearchParams({
    q,
    type,
    page: String(pagination.page),
    page_size: String(PAGE_SIZE),
  });
  const { data, loading, reload } = useApi(`/clients?${params.toString()}`);
  const rows = data?.items || [];
  return (
    <div data-testid="clients-page">
      <PageHeader eyebrow="CRM" title={tr("Clienți", "Clients")}
        actions={<Button data-testid="add-client-button" onClick={() => setOpen(true)}><Plus className="mr-1 h-4 w-4" />{tr("Client nou", "New client")}</Button>} />
      <Panel>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input data-testid="clients-search-input" className="pl-9" placeholder={tr("Caută nume, CNP, CUI, telefon…", "Search name, CNP, VAT, phone…")} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="flex gap-1">
            {[["", tr("Toți", "All")], ["pf", tr("Persoane fizice", "Individuals")], ["pj", tr("Persoane juridice", "Companies")]].map(([v, l]) => (
              <Button key={v} size="sm" variant={type === v ? "default" : "outline"} data-testid={`clients-filter-${v || "all"}`} onClick={() => setType(v)}>{l}</Button>
            ))}
          </div>
        </div>
        {loading && !data ? <Loading /> : !rows.length ? <Empty text={tr("Niciun client.", "No clients.")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="clients-table">
              <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">{tr("Client", "Client")}</th><th className="px-2">CNP / CUI</th><th className="px-2">{tr("Telefon", "Phone")}</th>
                <th className="px-2">Email</th><th className="px-2">{tr("Localitate", "City")}</th><th className="px-2 text-right">{tr("Vehicule", "Vehicles")}</th>
              </tr></thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} data-testid={`client-row-${c.id}`} onClick={() => nav(`/clients/${c.id}`)} className="h-10 cursor-pointer border-b border-border/50 hover:bg-accent/60">
                    <td className="px-2 font-medium"><span className="flex items-center gap-2">{c.type === "pj" ? <Building2 className="h-4 w-4 text-cyan-500" /> : <User className="h-4 w-4 text-muted-foreground" />}{c.name}
                      {c.is_fleet && <span className="rounded-sm bg-primary/10 px-1.5 text-[10px] font-bold uppercase text-primary">{tr("Flotă", "Fleet")}</span>}</span></td>
                    <td className="px-2 font-mono text-xs">{c.type === "pj" ? c.cui : c.cnp}</td>
                    <td className="px-2 font-mono text-xs">{c.phone}</td><td className="px-2 text-muted-foreground">{c.email}</td>
                    <td className="px-2">{c.city}</td><td className="px-2 text-right font-mono">{c.vehicle_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <PaginationControls
          {...pagination}
          total={data?.total || 0}
          totalPages={data?.total_pages || 1}
          testid="clients-pagination"
        />
      </Panel>
      <ClientForm open={open} onOpenChange={setOpen} onSaved={reload} />
    </div>
  );
}
