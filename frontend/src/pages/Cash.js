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
import { CashDepositForm, PaymentEntryForm } from "@/components/CashPaymentForms";

export default function Cash() {
  const { tr } = useLang();
  const [day, setDay] = useState(today());
  const { data: reg, reload: reloadRegister } = useApi(`/cash-register?day=${day}`);
  const cashPagination = useServerPagination("cash-payments");
  const cashlessPagination = useServerPagination("cashless-payments");
  const { data: cashPaymentsData, reload: reloadCashPayments } = useApi(
    `/payments?method=numerar&page=${cashPagination.page}&page_size=${PAGE_SIZE}`,
  );
  const { data: cashlessPaymentsData, reload: reloadCashlessPayments } = useApi(
    `/payments?method=pos,transfer,online&page=${cashlessPagination.page}&page_size=${PAGE_SIZE}`,
  );
  const reloadCash = () => {
    reloadRegister();
    reloadCashPayments();
  };
  const reloadCashless = () => reloadCashlessPayments();
  return (
    <div data-testid="cash-page">
      <PageHeader eyebrow={tr("Numerar · POS · transfer · online", "Cash · POS · transfer · online")} title={tr("Încasări & registru de casă", "Payments & cash register")} />
      <Tabs defaultValue="register">
        <TabsList>
          <TabsTrigger value="register" data-testid="cash-tab-register">{tr("Registru de casă", "Cash register")}</TabsTrigger>
          <TabsTrigger value="cash" data-testid="cash-tab-cash-payments">{tr("Încasări numerar", "Cash receipts")}</TabsTrigger>
          <TabsTrigger value="cashless" data-testid="cash-tab-cashless-payments">POS / OP</TabsTrigger>
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
                <Kpi testid="cash-out" label={tr("Depuneri bancă", "Bank deposits")} value={money(reg.total_out)} accent="text-rose-500" />
                <Kpi testid="cash-closing" label={tr("Sold final", "Closing")} value={money(reg.closing)} />
              </div>
              <Panel>
                {!reg.entries.length ? <Empty text={tr("Nicio operațiune în numerar.", "No cash operations.")} /> : (
                  <table className="w-full min-w-[720px] text-sm"><tbody>
                    {reg.entries.map((e) => (
                      <tr key={e.id} className="h-10 border-b border-border/50"><td className="font-mono text-xs">{e.doc_number}</td><td>{dt(e.date)}</td><td>{e.client_name}</td>
                        <td className="font-mono text-xs">{e.invoice_ref || e.reference}</td><td className={`text-right font-mono ${e.direction === "out" ? "text-rose-500" : "text-emerald-500"}`}>{e.direction === "out" ? "-" : "+"}{money(e.amount)}</td></tr>
                    ))}
                  </tbody></table>
                )}
              </Panel>
              <CashDepositForm available={reg.closing} onSaved={reloadCash} />
            </>
          )}
        </TabsContent>
        <TabsContent value="cash">
          <Panel>
            <PaymentEntryForm cashOnly onSaved={reloadCash} />
            {!cashPaymentsData ? <Loading /> : (
              <div className="overflow-x-auto">
                <table className="mt-4 w-full min-w-[760px] text-sm" data-testid="cash-payments-table"><thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-2 py-2">{tr("Document", "Document")}</th><th className="px-2">{tr("Data", "Date")}</th><th className="px-2">{tr("Metodă", "Method")}</th>
                  <th className="px-2">Client</th><th className="px-2">{tr("Factură", "Invoice")}</th><th className="px-2 text-right">{tr("Sumă", "Amount")}</th><th />
                </tr></thead><tbody>
                  {(cashPaymentsData.items || []).map((p) => (
                    <tr key={p.id} className="h-10 border-b border-border/50">
                      <td className="px-2"><div className="font-mono text-xs">{p.doc_number}</div><div className="text-[11px] text-muted-foreground">{tr(...DOCS[p.doc_type])}</div></td>
                      <td className="px-2">{dt(p.date)}</td><td className="px-2">{tr(...METHODS[p.method])}</td><td className="px-2">{p.client_name}</td>
                      <td className="px-2"><Link className="font-mono text-xs text-primary" to={`/invoices/${p.invoice_id}`}>{p.invoice_ref}</Link></td>
                      <td className="px-2 text-right font-mono">{money(p.amount)}</td>
                      <td className="px-2 text-right"><Button variant="ghost" size="icon" data-testid={`cash-payment-print-${p.id}`} onClick={() => window.open(`/print/receipt/${p.id}`, "_blank")}><Printer className="h-4 w-4" /></Button></td>
                    </tr>
                  ))}
                </tbody></table>
              </div>
            )}
            <PaginationControls {...cashPagination} total={cashPaymentsData?.total || 0} totalPages={cashPaymentsData?.total_pages || 1} testid="cash-payments-pagination" />
          </Panel>
        </TabsContent>
        <TabsContent value="cashless">
          <Panel>
            <PaymentEntryForm onSaved={reloadCashless} />
            {!cashlessPaymentsData ? <Loading /> : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[720px] text-sm" data-testid="cashless-payments-table"><thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground"><th className="px-2 py-2">{tr("Document", "Document")}</th><th className="px-2">{tr("Data", "Date")}</th><th className="px-2">{tr("Metodă", "Method")}</th><th className="px-2">Client</th><th className="px-2 text-right">{tr("Sumă", "Amount")}</th></tr></thead><tbody>
                  {(cashlessPaymentsData.items || []).map((p) => (
                    <tr key={p.id} className="h-10 border-b border-border/50"><td className="font-mono text-xs">{p.doc_number}</td><td>{dt(p.date)}</td><td>{tr(...METHODS[p.method])}</td><td>{p.client_name}</td><td className="text-right font-mono">{money(p.amount)}</td></tr>
                  ))}
                </tbody></table>
              </div>
            )}
            <PaginationControls {...cashlessPagination} total={cashlessPaymentsData?.total || 0} totalPages={cashlessPaymentsData?.total_pages || 1} testid="cashless-payments-pagination" />
          </Panel>
        </TabsContent>
      </Tabs>
    </div>
  );
}
