import { useState } from "react";
import { Link } from "react-router-dom";
import { Printer } from "lucide-react";
import { api, downloadFile, errMsg, useApi } from "@/lib/api";
import { toast } from "sonner";
import { useLang } from "@/lib/prefs";
import { dateOnly, money, dt, today } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Empty, Field, Kpi, Loading, PageHeader, Panel } from "@/components/common";
import { METHODS, DOCS } from "@/pages/InvoiceDetail";
import { PAGE_SIZE, PaginationControls, useServerPagination } from "@/components/Pagination";
import { CashDepositForm, CashPayoutForm, PaymentEntryForm } from "@/components/CashPaymentForms";

const documentLabel = (translate, documentType) => {
  const labels = DOCS[documentType] || [documentType || "Document", documentType || "Document"];
  return translate(labels[0], labels[1]);
};

export default function Cash() {
  const { tr } = useLang();
  const [day, setDay] = useState(today());
  const [cashQuery, setCashQuery] = useState("");
  const [cashlessQuery, setCashlessQuery] = useState("");
  const [payoutQuery, setPayoutQuery] = useState("");
  const [reportFrom, setReportFrom] = useState(`${today().slice(0, 8)}01`);
  const [reportTo, setReportTo] = useState(today());
  const [reversePayment, setReversePayment] = useState(null);
  const [reverseReason, setReverseReason] = useState("");
  const [reverseError, setReverseError] = useState("");
  const [reversing, setReversing] = useState(false);
  const { data: reg, reload: reloadRegister } = useApi(`/cash-register?day=${day}`);
  const cashPagination = useServerPagination("cash-payments");
  const cashlessPagination = useServerPagination("cashless-payments");
  const payoutPagination = useServerPagination(payoutQuery);
  const { data: cashPaymentsData, reload: reloadCashPayments } = useApi(
    `/payments?method=numerar&q=${encodeURIComponent(cashQuery)}&page=${cashPagination.page}&page_size=${PAGE_SIZE}`,
  );
  const { data: cashlessPaymentsData, reload: reloadCashlessPayments } = useApi(
    `/payments?method=pos,transfer,online&q=${encodeURIComponent(cashlessQuery)}&page=${cashlessPagination.page}&page_size=${PAGE_SIZE}`,
  );
  const { data: cashReport } = useApi(
    `/cash-register/report?date_from=${reportFrom}&date_to=${reportTo}&cash_only=true`,
  );
  const { data: payoutsData, reload: reloadPayouts } = useApi(
    `/cash-movements?q=${encodeURIComponent(payoutQuery)}&page=${payoutPagination.page}&page_size=${PAGE_SIZE}`,
  );
  const reloadCash = () => {
    reloadRegister();
    reloadCashPayments();
  };
  const reloadCashless = () => reloadCashlessPayments();
  const reverseReceipt = async () => {
    setReversing(true);
    setReverseError("");
    try {
      await api.post(`/payments/${reversePayment.id}/reverse`, { reason: reverseReason });
      toast.success(tr("Document stornat", "Document reversed"));
      setReversePayment(null);
      setReverseReason("");
      reloadCash();
    } catch (error) {
      const message = errMsg(error);
      setReverseError(message);
      toast.error(message);
    } finally {
      setReversing(false);
    }
  };
  return (
    <div data-testid="cash-page">
      <PageHeader eyebrow={tr("Numerar · POS · transfer · online", "Cash · POS · transfer · online")} title={tr("Încasări & registru de casă", "Payments & cash register")} />
      <Tabs defaultValue="register">
        <div className="mb-2 max-w-full overflow-x-auto pb-1">
        <TabsList className="w-max min-w-max whitespace-nowrap">
          <TabsTrigger value="register" data-testid="cash-tab-register">{tr("Registru de casă", "Cash register")}</TabsTrigger>
          <TabsTrigger value="cash" data-testid="cash-tab-cash-payments">{tr("Încasări numerar", "Cash receipts")}</TabsTrigger>
          <TabsTrigger value="cashless" data-testid="cash-tab-cashless-payments">POS / OP</TabsTrigger>
          <TabsTrigger value="payouts" data-testid="cash-tab-payouts">{tr("Plăți", "Payouts")}</TabsTrigger>
          <TabsTrigger value="registers" data-testid="cash-tab-registers">{tr("Registre", "Registers")}</TabsTrigger>
        </TabsList>
        </div>
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
                <Kpi testid="cash-out" label={tr("Ieșiri numerar", "Cash outflows")} value={money(reg.total_out)} accent="text-rose-500" />
                <Kpi testid="cash-closing" label={tr("Sold final", "Closing")} value={money(reg.closing)} />
              </div>
              <Panel>
                {!reg.entries.length ? <Empty text={tr("Nicio operațiune în numerar.", "No cash operations.")} /> : (
                  <>
                  <div className="space-y-2 md:hidden" data-testid="cash-register-mobile-entries">
                    {reg.entries.map((entry) => (
                      <div key={entry.id} className="grid grid-cols-[1fr_auto] gap-2 border-b border-border/50 pb-2 text-xs">
                        <div className="min-w-0"><div className="font-mono">{entry.doc_number} · {dt(entry.date)}</div><div className="truncate text-muted-foreground">{entry.client_name}</div></div>
                        <div className={`self-center font-mono font-semibold ${entry.direction === "out" ? "text-rose-500" : "text-emerald-500"}`}>{entry.direction === "out" ? "-" : "+"}{money(entry.amount)}</div>
                      </div>
                    ))}
                  </div>
                  <div className="hidden overflow-x-auto md:block"><table className="w-full min-w-[720px] text-sm" data-testid="cash-register-entries-table"><tbody>
                    {reg.entries.map((e) => (
                      <tr key={e.id} className="h-10 border-b border-border/50"><td className="font-mono text-xs">{e.doc_number}</td><td>{dt(e.date)}</td><td>{e.client_name}</td>
                        <td className="font-mono text-xs">{e.invoice_ref || e.reference}</td><td className={`text-right font-mono ${e.direction === "out" ? "text-rose-500" : "text-emerald-500"}`}>{e.direction === "out" ? "-" : "+"}{money(e.amount)}</td></tr>
                    ))}
                  </tbody></table></div>
                  </>
                )}
              </Panel>
              <CashDepositForm available={reg.closing} onSaved={reloadCash} />
            </>
          )}
        </TabsContent>
        <TabsContent value="cash">
          <Panel>
            <PaymentEntryForm cashOnly onSaved={reloadCash} />
            <div className="mt-4 max-w-md"><Input data-testid="cash-payments-search-input" placeholder={tr("Caută client, CUI, nr. chitanță sau bon fiscal…", "Search client, tax ID or receipt number…")} value={cashQuery} onChange={(event) => setCashQuery(event.target.value)} /></div>
            {!cashPaymentsData ? <Loading /> : (
              <div className="overflow-x-auto">
                <table className="mt-4 w-full min-w-[760px] text-sm" data-testid="cash-payments-table"><thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-2 py-2">{tr("Document", "Document")}</th><th className="px-2">{tr("Data", "Date")}</th><th className="px-2">{tr("Metodă", "Method")}</th>
                  <th className="px-2">Client</th><th className="px-2">{tr("Factură", "Invoice")}</th><th className="px-2 text-right">{tr("Sumă", "Amount")}</th><th />
                </tr></thead><tbody>
                  {(cashPaymentsData.items || []).map((p) => (
                    <tr key={p.id} className="h-10 border-b border-border/50">
                      <td className="px-2"><div className="font-mono text-xs">{p.doc_number}</div><div className="text-[11px] text-muted-foreground">{documentLabel(tr, p.doc_type)}</div></td>
                      <td className="px-2">{p.document_issue_date ? dateOnly(p.document_issue_date) : dt(p.date)}</td><td className="px-2">{tr(...METHODS[p.method])}</td><td className="px-2">{p.client_name}</td>
                      <td className="px-2"><Link className="font-mono text-xs text-primary" to={`/invoices/${p.invoice_id}`}>{p.invoice_ref}</Link></td>
                      <td className="px-2 text-right font-mono">{money(p.amount)}</td>
                      <td className="px-2 text-right"><Button variant="ghost" size="icon" data-testid={`cash-payment-print-${p.id}`} onClick={() => window.open(`/print/receipt/${p.id}`, "_blank")}><Printer className="h-4 w-4" /></Button><Button variant="destructive" size="sm" data-testid={`cash-payment-reverse-${p.id}`} disabled={!!p.reversed_at} onClick={() => setReversePayment(p)}>{p.reversed_at ? tr("Stornată", "Reversed") : tr("Stornează", "Reverse")}</Button></td>
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
            <div className="mt-4 max-w-md"><Input data-testid="cashless-payments-search-input" placeholder={tr("Caută client, CUI sau document…", "Search client, tax ID or document…")} value={cashlessQuery} onChange={(event) => setCashlessQuery(event.target.value)} /></div>
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
        <TabsContent value="payouts">
          <Panel title={tr("Ieșiri de numerar", "Cash payouts")}>
            <CashPayoutForm available={reg?.closing || 0} onSaved={() => { reloadCash(); reloadPayouts(); }} />
            <div className="mt-6 border-t border-border pt-5">
              <h3 className="mb-3 text-sm font-semibold">{tr("Chitanță externă de la client", "External receipt from client")}</h3>
              <PaymentEntryForm cashOnly externalReceiptOnly onSaved={reloadCash} />
            </div>
            <Input data-testid="cash-payouts-search-input" className="mt-4 max-w-md" placeholder={tr("Caută beneficiar sau document…", "Search beneficiary or document…")} value={payoutQuery} onChange={(event) => setPayoutQuery(event.target.value)} />
            <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[680px] text-sm" data-testid="cash-payouts-table"><tbody>{(payoutsData?.items || []).map((movement) => <tr key={movement.id} className="h-10 border-b border-border/50"><td className="font-mono">{movement.doc_number}</td><td>{dt(movement.date)}</td><td>{movement.beneficiary}</td><td>{movement.kind}</td><td className="text-right font-mono">{money(movement.amount)}</td></tr>)}</tbody></table></div>
            <PaginationControls {...payoutPagination} total={payoutsData?.total || 0} totalPages={payoutsData?.total_pages || 1} testid="cash-payouts-pagination" />
          </Panel>
        </TabsContent>
        <TabsContent value="registers">
          <Panel title={tr("Registre pe interval", "Registers by period")}>
            <div className="flex flex-wrap items-end gap-3">
              <Field label={tr("De la", "From")}><Input data-testid="cash-register-from-input" type="date" value={reportFrom} onChange={(event) => setReportFrom(event.target.value)} /></Field>
              <Field label={tr("Până la", "To")}><Input data-testid="cash-register-to-input" type="date" value={reportTo} onChange={(event) => setReportTo(event.target.value)} /></Field>
              <Button data-testid="cash-register-cash-pdf-button" onClick={() => downloadFile(`/cash-register/report.pdf?date_from=${reportFrom}&date_to=${reportTo}&cash_only=true`, "registru_incasari_numerar.pdf")}>{tr("PDF încasări numerar", "Cash receipts PDF")}</Button>
              <Button variant="outline" data-testid="cash-register-all-pdf-button" onClick={() => downloadFile(`/cash-register/report.pdf?date_from=${reportFrom}&date_to=${reportTo}&cash_only=false`, "registru_toate_miscarile.pdf")}>{tr("PDF toate mișcările", "All movements PDF")}</Button>
            </div>
            <div className="mt-5 overflow-x-auto"><table className="w-full min-w-[680px] text-sm" data-testid="cash-register-report-table"><tbody>{(cashReport?.items || []).map((item) => <tr key={`${item.date}-${item.document}`} className="h-9 border-b border-border/50"><td>{dt(item.date)}</td><td className="font-mono">{item.document}</td><td>{item.label}</td><td className="text-right font-mono">{item.in ? money(item.in) : "—"}</td><td className="text-right font-mono">{item.out ? money(item.out) : "—"}</td><td className="text-right font-mono">{money(item.balance)}</td></tr>)}</tbody></table></div>
          </Panel>
        </TabsContent>
      </Tabs>
      <Dialog open={!!reversePayment} onOpenChange={(open) => {
        if (!open) {
          setReversePayment(null);
          setReverseReason("");
          setReverseError("");
        }
      }}>
        <DialogContent data-testid="cash-reversal-dialog">
          <DialogHeader><DialogTitle>{tr("Stornare document numerar", "Reverse cash document")}</DialogTitle></DialogHeader>
          <Field label={tr("Motiv obligatoriu", "Required reason")}><Input data-testid="cash-reversal-reason-input" value={reverseReason} onChange={(event) => setReverseReason(event.target.value)} /></Field>
          {reverseError && <p data-testid="cash-reversal-error" className="text-sm text-destructive">{reverseError}</p>}
          <DialogFooter><Button variant="outline" onClick={() => setReversePayment(null)}>{tr("Renunță", "Cancel")}</Button><Button data-testid="cash-reversal-confirm-button" disabled={reversing || !reverseReason.trim()} onClick={reverseReceipt}>{reversing ? tr("Se stornează…", "Reversing…") : tr("Confirmă stornarea", "Confirm reversal")}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
