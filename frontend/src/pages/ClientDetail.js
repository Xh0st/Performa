import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { FileDown, Pencil, Plus, Car, Search } from "lucide-react";
import { downloadFile, useApi, useDebouncedValue } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, date, num, today } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageHeader, Panel, Loading, StatusBadge, Badge, PAY_STATUS, Empty } from "@/components/common";
import ClientForm from "@/components/ClientForm";
import VehicleForm from "@/components/VehicleForm";
import { PAGE_SIZE, PaginationControls, useServerPagination } from "@/components/Pagination";

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
  const [ordersQuery, setOrdersQuery] = useState("");
  const [invoicesQuery, setInvoicesQuery] = useState("");
  const [dateFrom, setDateFrom] = useState(() => `${today().slice(0, 8)}01`);
  const [dateTo, setDateTo] = useState(today());
  const debouncedOrdersQuery = useDebouncedValue(ordersQuery);
  const debouncedInvoicesQuery = useDebouncedValue(invoicesQuery);
  const ordersPagination = useServerPagination(`${id}:${debouncedOrdersQuery}`);
  const invoicesPagination = useServerPagination(`${id}:${debouncedInvoicesQuery}`);
  const statementPagination = useServerPagination(`${id}:${dateFrom}:${dateTo}`);
  const ordersParams = new URLSearchParams({
    q: debouncedOrdersQuery,
    page: String(ordersPagination.page),
    page_size: String(PAGE_SIZE),
  });
  const invoicesParams = new URLSearchParams({
    q: debouncedInvoicesQuery,
    page: String(invoicesPagination.page),
    page_size: String(PAGE_SIZE),
  });
  const statementParams = new URLSearchParams({
    date_from: dateFrom,
    date_to: dateTo,
    page: String(statementPagination.page),
    page_size: String(PAGE_SIZE),
  });
  const { data: ordersData } = useApi(`/clients/${id}/work-orders?${ordersParams.toString()}`);
  const { data: invoicesData } = useApi(`/clients/${id}/invoices?${invoicesParams.toString()}`);
  const { data: statementData } = useApi(
    `/clients/${id}/account-statement?${statementParams.toString()}`,
  );
  if (!c) return <Loading />;
  const orders = ordersData?.items || [];
  const invoices = invoicesData?.items || [];
  const statementItems = statementData?.items || [];
  const summary = c.financial_summary || { invoiced_total: 0, outstanding: 0 };
  const paymentCondition = c.payment_terms_days
    ? `${c.payment_terms_days} ${tr("zile", "days")}`
    : "CASH";
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
            {c.type === "pj" && <Info label={tr("Condiție plată", "Payment condition")} value={paymentCondition} mono />}
            {c.type === "pj" && <Info label={tr("Limită credit", "Credit limit")} value={c.credit_limit === null || c.credit_limit === undefined ? "—" : money(c.credit_limit)} mono />}
          </div>
        </Panel>
        <Panel title={tr("Sumar financiar", "Financial summary")}>
          <div className="grid grid-cols-2 gap-4">
            <Info label={tr("Total facturat", "Total invoiced")} value={money(summary.invoiced_total)} mono />
            <Info label={tr("Sold restant", "Outstanding")} value={money(summary.outstanding)} mono />
            <Info label={tr("Comenzi", "Orders")} value={c.work_order_count} mono />
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
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="wo" data-testid="client-tab-orders">{tr("Istoric Comenzi", "Order history")}</TabsTrigger>
          <TabsTrigger value="inv" data-testid="client-tab-invoices">{tr("Facturi", "Invoices")}</TabsTrigger>
          <TabsTrigger value="statement" data-testid="client-tab-account-statement">{tr("Fișa Cont", "Account statement")}</TabsTrigger>
        </TabsList>
        <TabsContent value="wo">
          <Panel>
            <div className="relative mb-4 max-w-md">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                data-testid="client-orders-search-input"
                className="pl-9"
                placeholder={tr("Caută comandă, vehicul sau descriere…", "Search order, vehicle or description…")}
                value={ordersQuery}
                onChange={(event) => setOrdersQuery(event.target.value)}
              />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm" data-testid="client-orders-table"><tbody>
                {orders.map((w) => (
                  <tr key={w.id} data-testid={`client-order-row-${w.id}`} className="h-10 border-b border-border/50">
                    <td><Link className="font-mono text-primary hover:underline" data-testid={`client-order-link-${w.id}`} to={`/work-orders/${w.id}`}>{w.number}</Link></td>
                    <td>{date(w.created_at)}</td><td className="font-mono text-xs">{num(w.mileage_in, 0)} km</td><td>{w.vehicle_label || "—"}</td><td className="max-w-xs truncate">{w.complaint}</td><td className="text-right"><StatusBadge status={w.status} /></td>
                  </tr>
                ))}
              </tbody></table>
            </div>
            {!orders.length && <Empty text="—" />}
            <PaginationControls
              {...ordersPagination}
              total={ordersData?.total || 0}
              totalPages={ordersData?.total_pages || 1}
              testid="client-orders-pagination"
            />
          </Panel>
        </TabsContent>
        <TabsContent value="inv">
          <Panel>
            <div className="relative mb-4 max-w-md">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                data-testid="client-invoices-search-input"
                className="pl-9"
                placeholder={tr("Caută număr, vehicul sau comandă…", "Search number, vehicle or order…")}
                value={invoicesQuery}
                onChange={(event) => setInvoicesQuery(event.target.value)}
              />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm" data-testid="client-invoices-table"><tbody>
                {invoices.map((invoice) => (
                  <tr key={invoice.id} data-testid={`client-invoice-row-${invoice.id}`} className="h-10 border-b border-border/50">
                    <td><Link className="font-mono text-primary hover:underline" data-testid={`client-invoice-link-${invoice.id}`} to={`/invoices/${invoice.id}`}>{invoice.series}{invoice.number}</Link></td>
                    <td className="uppercase text-xs">{invoice.kind === "credit_note" ? tr("Stornare", "Credit") : invoice.type}</td><td>{date(invoice.issue_date)}</td><td className="text-right font-mono">{money(invoice.totals.gross)}</td>
                    <td className="text-right"><Badge map={PAY_STATUS} value={invoice.status} /></td>
                  </tr>
                ))}
              </tbody></table>
            </div>
            {!invoices.length && <Empty text="—" />}
            <PaginationControls
              {...invoicesPagination}
              total={invoicesData?.total || 0}
              totalPages={invoicesData?.total_pages || 1}
              testid="client-invoices-pagination"
            />
          </Panel>
        </TabsContent>
        <TabsContent value="statement">
          <Panel
            title={tr("Fișa Cont", "Account statement")}
            actions={<Button
              variant="outline"
              size="sm"
              data-testid="client-account-statement-pdf-button"
              onClick={() => downloadFile(`/clients/${id}/account-statement.pdf?${statementParams.toString()}`, `fisa_cont_${c.name}.pdf`)}
            ><FileDown className="mr-1 h-4 w-4" />PDF</Button>}
          >
            <div className="mb-4 flex flex-wrap items-end gap-3">
              <label className="grid gap-1 text-xs font-medium"><span>{tr("De la", "From")}</span><Input data-testid="client-statement-from-input" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
              <label className="grid gap-1 text-xs font-medium"><span>{tr("Până la", "To")}</span><Input data-testid="client-statement-to-input" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
            </div>
            <div className="mb-4 grid gap-3 text-sm sm:grid-cols-4" data-testid="client-statement-summary">
              <Info label={tr("Sold inițial", "Opening balance")} value={money(statementData?.summary?.opening)} mono />
              <Info label="Debit" value={money(statementData?.summary?.debit)} mono />
              <Info label="Credit" value={money(statementData?.summary?.credit)} mono />
              <Info label={tr("Sold final", "Closing balance")} value={money(statementData?.summary?.closing)} mono />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm" data-testid="client-account-statement-table"><tbody>
                {statementItems.map((item) => (
                  <tr key={`${item.kind}-${item.entity_id}`} data-testid={`client-statement-row-${item.kind}-${item.entity_id}`} className="h-10 border-b border-border/50">
                    <td>{date(item.date)}</td><td className="font-mono text-primary">{item.reference}</td><td>{item.description}</td><td className="text-right font-mono">{item.debit ? money(item.debit) : "—"}</td><td className="text-right font-mono">{item.credit ? money(item.credit) : "—"}</td><td className="text-right font-mono font-semibold">{money(item.balance)}</td>
                  </tr>
                ))}
              </tbody></table>
            </div>
            {!statementItems.length && <Empty text={tr("Nu există mișcări în interval.", "No movements in this period.")} />}
            <PaginationControls
              {...statementPagination}
              total={statementData?.total || 0}
              totalPages={statementData?.total_pages || 1}
              testid="client-account-statement-pagination"
            />
          </Panel>
        </TabsContent>
      </Tabs>
      <ClientForm open={edit} onOpenChange={setEdit} initial={c} onSaved={reload} />
      <VehicleForm open={addV} onOpenChange={setAddV} clientId={id} onSaved={reload} />
    </div>
  );
}
