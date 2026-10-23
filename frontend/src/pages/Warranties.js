import { useState } from "react";
import { FileDown, Plus, Wrench } from "lucide-react";
import { toast } from "sonner";
import { api, downloadFile, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Link } from "react-router-dom";
import { date } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, Loading, NativeSelect, PageHeader, Panel } from "@/components/common";
import { PAGE_SIZE, PaginationControls, useServerPagination } from "@/components/Pagination";

const STATUS = {
  in_asteptare: "În așteptare",
  conform: "Conform",
  neconform: "Neconform",
  nu_este_cazul: "Nu este cazul",
  trimis: "Trimis furnizor",
  acceptat: "Acceptat furnizor",
  respins: "Respins furnizor",
  in_analiza: "În analiză",
  admis_inlocuit: "Admis · înlocuit",
  admis_rambursat: "Admis · rambursat",
};

function ClaimDialog({ open, onOpenChange, onSaved }) {
  const { tr } = useLang();
  const { data: invoices } = useApi(open ? "/warranties/invoices" : null, [open]);
  const [invoiceId, setInvoiceId] = useState("");
  const { data: certificate } = useApi(invoiceId ? `/warranties/invoices/${invoiceId}` : null, [invoiceId]);
  const [description, setDescription] = useState("");
  const [lines, setLines] = useState({});
  const [busy, setBusy] = useState(false);
  const save = async () => {
    const selected = Object.entries(lines)
      .filter(([, qty]) => Number(qty) > 0)
      .map(([source_line_id, qty]) => ({ source_line_id, qty: Number(qty) }));
    setBusy(true);
    try {
      const response = await api.post("/warranty-claims", { invoice_id: invoiceId, description, lines: selected });
      toast.success(`${tr("Dosar garanție creat", "Warranty claim created")}: ${response.data.number}`);
      onSaved();
      onOpenChange(false);
      setInvoiceId("");
      setDescription("");
      setLines({});
    } catch (error) {
      toast.error(errMsg(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="warranty-claim-dialog">
        <DialogHeader>
          <DialogTitle>{tr("Reclamație garanție", "Warranty claim")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Field label={tr("Factura originală", "Original invoice")}>
            <NativeSelect
              data-testid="warranty-invoice-select"
              value={invoiceId}
              onChange={(event) => {
                setInvoiceId(event.target.value);
                setLines({});
              }}
            >
              <option value="">—</option>
              {(invoices || []).map((invoice) => (
                <option key={invoice.id} value={invoice.id}>
                  {invoice.series}{invoice.number} · {invoice.buyer.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          {certificate && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="warranty-coverage-lines">
                <thead>
                  <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                    <th className="py-2">{tr("Acoperire", "Coverage")}</th>
                    <th>{tr("Valabil până", "Valid until")}</th>
                    <th className="text-right">{tr("Reclamat", "Claim")}</th>
                  </tr>
                </thead>
                <tbody>
                  {certificate.lines.map((line) => (
                    <tr key={line.source_line_id} className="border-b">
                      <td className="py-2">
                        <label className="flex items-center gap-2">
                          <Checkbox
                            data-testid={`warranty-line-${line.source_line_id}`}
                            checked={Number(lines[line.source_line_id] || 0) > 0}
                            onCheckedChange={(checked) => setLines({
                              ...lines,
                              [line.source_line_id]: checked ? line.qty : 0,
                            })}
                          />
                          {line.label} · {line.description}
                        </label>
                      </td>
                      <td>{date(line.valid_to)}</td>
                      <td className="w-28">
                        <Input
                          data-testid={`warranty-qty-${line.source_line_id}`}
                          type="number"
                          min="0"
                          max={line.qty}
                          value={lines[line.source_line_id] || ""}
                          onChange={(event) => setLines({
                            ...lines,
                            [line.source_line_id]: event.target.value,
                          })}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Field label={tr("Defect reclamat", "Claimed issue")}>
            <Textarea
              data-testid="warranty-claim-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>
        </div>
        <DialogFooter>
          <Button
            data-testid="warranty-claim-save-button"
            disabled={busy || !invoiceId || !description.trim()
              || !Object.values(lines).some((qty) => Number(qty) > 0)}
            onClick={save}
          >
            {tr("Deschide dosar", "Open claim")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Warranties() {
  const { tr } = useLang();
  const warrantyPagination = useServerPagination("warranties");
  const claimPagination = useServerPagination("warranty-claims");
  const { data: warrantiesData, reload: reloadWarranties } = useApi(
    `/warranties?status=&page=${warrantyPagination.page}&page_size=${PAGE_SIZE}`,
  );
  const { data: claimsData, reload: reloadClaims } = useApi(
    `/warranty-claims?page=${claimPagination.page}&page_size=${PAGE_SIZE}`,
  );
  const warranties = warrantiesData?.items;
  const claims = claimsData?.items;
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(null);
  if (!warranties || !claims) return <Loading />;
  const reload = () => {
    reloadWarranties();
    reloadClaims();
  };
  const edit = (claim) => {
    setSelected(claim);
    setForm({
      technical_result: claim.technical_result,
      supplier_return_status: claim.supplier_return_status,
      supplier_return_id: claim.supplier_return_id || "",
      resolution: claim.resolution,
      notes: claim.notes || "",
    });
  };
  const save = async () => {
    try {
      await api.put(`/warranty-claims/${selected.id}`, form);
      toast.success(tr("Dosar actualizat", "Claim updated"));
      setSelected(null);
      reload();
    } catch (error) {
      toast.error(errMsg(error));
    }
  };
  return (
    <div data-testid="warranties-page">
      <PageHeader
        eyebrow={tr("Facturi · trasabilitate · protecție client", "Invoices · traceability · customer protection")}
        title={tr("Garanții și reclamații", "Warranties and claims")}
        actions={<Button data-testid="new-warranty-claim-button" onClick={() => setOpen(true)}><Plus className="mr-1 h-4 w-4" />{tr("Reclamație", "Claim")}</Button>}
      />
      <div className="grid min-w-0 gap-4 xl:grid-cols-[.8fr_1.2fr]">
        <Panel
          title={tr("Certificate active", "Active certificates")}
          testid="warranty-certificates-panel"
          className="min-w-0"
        >
          <div className="space-y-2">
            {warranties.map((certificate) => (
              <div key={certificate.id} className="border-b pb-2 text-sm" data-testid={`warranty-certificate-${certificate.number}`}>
                <div className="flex justify-between gap-2"><span className="font-mono font-semibold">{certificate.number}</span><Button variant="ghost" size="icon" data-testid={`download-warranty-${certificate.number}`} onClick={() => downloadFile(`/warranties/invoices/${certificate.invoice_id}/certificate`, `${certificate.number}.pdf`)}><FileDown className="h-4 w-4" /></Button></div>
                <div>{certificate.invoice_ref} · {certificate.client_name}</div><div className="text-xs text-muted-foreground">{certificate.active_lines.length} {tr("acoperiri active", "active coverages")}</div>
              </div>
            ))}
            {!warranties.length && <div className="py-6 text-center text-sm text-muted-foreground" data-testid="warranty-certificates-empty">{tr("Nu există certificate.", "No certificates.")}</div>}
            <PaginationControls
              {...warrantyPagination}
              total={warrantiesData?.total || 0}
              totalPages={warrantiesData?.total_pages || 1}
              testid="warranty-certificates-pagination"
            />
          </div>
        </Panel>
        <Panel
          title={tr("Dosare de garanție", "Warranty claims")}
          testid="warranty-claims-panel"
          className="min-w-0"
        >
          <div className="min-w-0 overflow-x-auto">
            <table className="w-full min-w-[850px] text-sm" data-testid="warranty-claims-table"><thead><tr className="border-b text-left text-xs uppercase text-muted-foreground"><th className="px-2 py-2">{tr("Dosar", "Claim")}</th><th>{tr("Factură", "Invoice")}</th><th>{tr("Comandă", "Work order")}</th><th>{tr("Tehnic", "Technical")}</th><th>{tr("Retur", "Return")}</th><th>{tr("Soluție", "Resolution")}</th><th /></tr></thead><tbody>{claims.map((claim) => <tr key={claim.id} className="border-b"><td className="px-2 py-2 font-mono">{claim.number}</td><td>{claim.invoice_ref}</td><td className="font-mono"><Link className="text-primary" to={`/work-orders/${claim.work_order_id}`}>{claim.work_order_number}</Link></td><td>{STATUS[claim.technical_result]}</td><td>{STATUS[claim.supplier_return_status]}</td><td>{STATUS[claim.resolution]}</td><td><Button variant="ghost" size="icon" data-testid={`edit-warranty-claim-${claim.number}`} onClick={() => edit(claim)}><Wrench className="h-4 w-4" /></Button></td></tr>)}</tbody></table>
          </div>
          {!claims.length && <div className="py-6 text-center text-sm text-muted-foreground" data-testid="warranty-claims-empty">{tr("Nu există dosare deschise.", "No open claims.")}</div>}
          <PaginationControls
            {...claimPagination}
            total={claimsData?.total || 0}
            totalPages={claimsData?.total_pages || 1}
            testid="warranty-claims-pagination"
          />
        </Panel>
      </div>
      <ClaimDialog open={open} onOpenChange={setOpen} onSaved={reload} />
      <Dialog open={!!selected} onOpenChange={(value) => !value && setSelected(null)}>
        <DialogContent data-testid="warranty-claim-edit-dialog"><DialogHeader><DialogTitle>{selected?.number}</DialogTitle></DialogHeader>{form && <div className="grid gap-3"><Field label={tr("Rezultat tehnic", "Technical result")}><NativeSelect data-testid="warranty-technical-result-select" value={form.technical_result} onChange={(event) => setForm({ ...form, technical_result: event.target.value })}>{["in_asteptare", "conform", "neconform"].map((key) => <option key={key} value={key}>{STATUS[key]}</option>)}</NativeSelect></Field><Field label={tr("Retur furnizor", "Supplier return")}><NativeSelect data-testid="warranty-supplier-status-select" value={form.supplier_return_status} onChange={(event) => setForm({ ...form, supplier_return_status: event.target.value })}>{["nu_este_cazul", "in_asteptare", "trimis", "acceptat", "respins"].map((key) => <option key={key} value={key}>{STATUS[key]}</option>)}</NativeSelect></Field><Field label={tr("Soluție", "Resolution")}><NativeSelect data-testid="warranty-resolution-select" value={form.resolution} onChange={(event) => setForm({ ...form, resolution: event.target.value })}>{["in_analiza", "admis_inlocuit", "admis_rambursat", "respins"].map((key) => <option key={key} value={key}>{STATUS[key]}</option>)}</NativeSelect></Field><Field label={tr("Note", "Notes")}><Textarea data-testid="warranty-claim-notes" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></Field></div>}<DialogFooter><Button data-testid="warranty-claim-update-button" onClick={save}>{tr("Salvează", "Save")}</Button></DialogFooter></DialogContent>
      </Dialog>
    </div>
  );
}