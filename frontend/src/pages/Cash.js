import { useState } from "react";
import { Link } from "react-router-dom";
import { Printer } from "lucide-react";
import { useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, dt, today } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageHeader, Panel, Kpi, Loading, Empty } from "@/components/common";
import { METHODS, DOCS } from "@/pages/InvoiceDetail";
import { PAGE_SIZE, PaginationControls, useServerPagination } from "@/components/Pagination";

export default function Cash() {
  const { tr } = useLang();
  const [day, setDay] = useState(today());
  const { data: reg } = useApi(`/cash-register?day=${day}`, [day]);
  const pagination = useServerPagination("payments");
  const { data: paymentsData } = useApi(
    `/payments?page=${pagination.page}&page_size=${PAGE_SIZE}`,
  );
  const pays = paymentsData?.items;
  return (
    <div data-testid="cash-page">
      <PageHeader eyebrow={tr("Numerar · POS · transfer · online", "Cash · POS · transfer · online")} title={tr("Încasări & registru de casă", "Payments & cash register")} />
      <Tabs defaultValue="register">
        <TabsList>
          <TabsTrigger value="register" data-testid="cash-tab-register">{tr("Registru de casă", "Cash register")}</TabsTrigger>
          <TabsTrigger value="payments" data-testid="cash-tab-payments">{tr("Toate încasările", "All payments")}</TabsTrigger>
        </TabsList>
        <TabsContent value="register">
          <div className="mb-4 flex items-center gap-2">
            <Input type="date" data-testid="cash-day-input" className="w-48" value={day} onChange={(e) => setDay(e.target.value)} />
            <Button variant="outline" data-testid="print-register-button" onClick={() => window.open(`/print/register/${day}`, "_blank")}><Printer className="mr-1 h-4 w-4" />{tr("Tipărește registrul", "Print register")}</Button>
          </div>
          {!reg ? <Loading /> : (
            <>
              <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                <Kpi testid="cash-opening" label={tr("Sold inițial", "Opening")} value={money(reg.opening)} />
                <Kpi testid="cash-in" label={tr("Încasări", "Receipts")} value={money(reg.total_in)} accent="text-emerald-500" />
                <Kpi testid="cash-out" label={tr("Plăți", "Payouts")} value={money(reg.total_out)} accent="text-rose-500" />
                <Kpi testid="cash-closing" label={tr("Sold final", "Closing")} value={money(reg.closing)} />
              </div>
              <Panel>
                {!reg.entries.length ? <Empty text={tr("Nicio operațiune în numerar.", "No cash operations.")} /> : (
                  <table className="w-full text-sm"><tbody>
                    {reg.entries.map((e) => (
                      <tr key={e.id} className="h-10 border-b border-border/50"><td className="font-mono text-xs">{e.doc_number}</td><td>{dt(e.date)}</td><td>{e.client_name}</td>
                        <td className="font-mono text-xs">{e.invoice_ref}</td><td className="text-right font-mono text-emerald-500">+{money(e.amount)}</td></tr>
                    ))}
                  </tbody></table>
                )}
              </Panel>
            </>
          )}
        </TabsContent>
        <TabsContent value="payments">
          <Panel>
            {!pays ? <Loading /> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="payments-table"><thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-2 py-2">{tr("Document", "Document")}</th><th className="px-2">{tr("Data", "Date")}</th><th className="px-2">{tr("Metodă", "Method")}</th>
                  <th className="px-2">Client</th><th className="px-2">{tr("Factură", "Invoice")}</th><th className="px-2 text-right">{tr("Sumă", "Amount")}</th><th />
                </tr></thead><tbody>
                  {pays.map((p) => (
                    <tr key={p.id} className="h-10 border-b border-border/50">
                      <td className="px-2"><div className="font-mono text-xs">{p.doc_number}</div><div className="text-[11px] text-muted-foreground">{tr(...DOCS[p.doc_type])}</div></td>
                      <td className="px-2">{dt(p.date)}</td><td className="px-2">{tr(...METHODS[p.method])}</td><td className="px-2">{p.client_name}</td>
                      <td className="px-2"><Link className="font-mono text-xs text-primary" to={`/invoices/${p.invoice_id}`}>{p.invoice_ref}</Link></td>
                      <td className="px-2 text-right font-mono">{money(p.amount)}</td>
                      <td className="px-2 text-right"><Button variant="ghost" size="icon" onClick={() => window.open(`/print/receipt/${p.id}`, "_blank")}><Printer className="h-4 w-4" /></Button></td>
                    </tr>
                  ))}
                </tbody></table>
              </div>
            )}
            <PaginationControls
              {...pagination}
              total={paymentsData?.total || 0}
              totalPages={paymentsData?.total_pages || 1}
              testid="payments-pagination"
            />
          </Panel>
        </TabsContent>
      </Tabs>
    </div>
  );
}
