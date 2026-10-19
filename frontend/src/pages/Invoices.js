import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, date } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Panel, Loading, Badge, PAY_STATUS, EF_STATUS, Empty, NativeSelect } from "@/components/common";
import { PaginationControls, usePagination } from "@/components/Pagination";

export default function Invoices() {
  const { tr } = useLang();
  const nav = useNavigate();
  const [type, setType] = useState("fiscal");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const { data } = useApi(`/invoices?type=${type}&status=${status}`, [type, status]);
  const rows = (data || []).filter((invoice) => {
    const value = [
      invoice.series,
      invoice.number,
      invoice.buyer?.name,
      invoice.buyer?.cui,
      invoice.vehicle?.vin,
      invoice.vehicle_vin,
      invoice.work_order_number,
    ].join(" ").toLowerCase();
    return value.includes(q.toLowerCase())
      && (!dateFrom || invoice.issue_date >= dateFrom)
      && (!dateTo || invoice.issue_date <= dateTo);
  });
  const total = rows.reduce((s, i) => s + i.totals.gross, 0);
  const pagination = usePagination(rows, `${type}:${status}:${q}:${dateFrom}:${dateTo}:${data?.length || 0}`);
  return (
    <div data-testid="invoices-page">
      <PageHeader eyebrow="ANAF · e-Factura · SPV" title={tr("Facturi", "Invoices")} />
      <Panel>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {[["fiscal", tr("Fiscale", "Fiscal")], ["proforma", tr("Proforme", "Proforma")]].map(([v, l]) => (
            <Button key={v} size="sm" variant={type === v ? "default" : "outline"} data-testid={`invoices-type-${v}`} onClick={() => setType(v)}>{l}</Button>
          ))}
          <span className="mx-2 h-5 w-px bg-border" />
          <NativeSelect data-testid="invoices-status-select" className="h-9 w-36" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">{tr("Toate", "All")}</option>
            <option value="partial">{tr("Parțial", "Partial")}</option>
            <option value="unpaid">{tr("Neîncasate", "Unpaid")}</option>
            <option value="paid">{tr("Încasate", "Paid")}</option>
          </NativeSelect>
          <Input
            className="h-9 min-w-52 flex-1"
            data-testid="invoices-search-input"
            placeholder={tr("Caută număr, client, CUI sau VIN…", "Search number, client, CUI, or VIN…")}
            value={q}
            onChange={(event) => setQ(event.target.value)}
          />
          <Input data-testid="invoices-date-from-input" className="h-9 w-36" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          <Input data-testid="invoices-date-to-input" className="h-9 w-36" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          <div className="flex-1" />
          <span className="font-mono text-sm">{rows.length} · {money(total)}</span>
        </div>
        {!data ? <Loading /> : !rows.length ? <Empty text={tr("Niciun document.", "No documents.")} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="invoices-table">
              <thead><tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-2">{tr("Serie/Nr.", "Series/No.")}</th><th className="px-2">{tr("Data", "Date")}</th><th className="px-2">{tr("Scadență", "Due")}</th>
                <th className="px-2">Client</th><th className="px-2">{tr("Comandă", "Order")}</th><th className="px-2 text-right">Total</th><th className="px-2 text-right">{tr("Rest", "Due")}</th>
                <th className="px-2 text-center">{tr("Încasare", "Payment")}</th><th className="px-2 text-center">e-Factura</th>
              </tr></thead>
              <tbody>
                {pagination.pageItems.map((i) => (
                  <tr key={i.id} data-testid={`invoice-row-${i.series}${i.number}`} onClick={() => nav(`/invoices/${i.id}`)} className="h-10 cursor-pointer border-b border-border/50 hover:bg-accent/60">
                    <td className="px-2 font-mono text-xs font-semibold text-primary">{i.series}{i.number}{i.kind === "credit_note" && <span data-testid={`invoice-storno-tag-${i.series}${i.number}`} className="ml-1 rounded-sm bg-violet-500/15 px-1 text-[10px] text-violet-500">STORNO {i.original_ref}</span>}{i.storno_status && <span className="ml-1 text-[10px] text-violet-500">{i.storno_status === "total" ? tr("stornată", "credited") : tr("storno parțial", "part. credited")}</span>}</td><td className="px-2">{date(i.issue_date)}</td>
                    <td className={`px-2 ${i.status !== "paid" && i.due_date < new Date().toISOString().slice(0, 10) ? "text-rose-500" : ""}`}>{date(i.due_date)}</td>
                    <td className="px-2">{i.buyer.name}</td><td className="px-2 font-mono text-xs">{i.work_order_number}</td>
                    <td className="px-2 text-right font-mono">{money(i.totals.gross)}</td><td className="px-2 text-right font-mono">{i.kind === "credit_note" ? "—" : money(i.totals.gross - i.paid_amount - (i.credited_amount || 0))}</td>
                    <td className="px-2 text-center">{i.type === "fiscal" && <Badge map={PAY_STATUS} value={i.status} />}</td>
                    <td className="px-2 text-center">{i.type === "fiscal" && <Badge map={EF_STATUS} value={i.efactura?.status} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <PaginationControls {...pagination} total={rows.length} testid="invoices-pagination" />
      </Panel>
    </div>
  );
}
