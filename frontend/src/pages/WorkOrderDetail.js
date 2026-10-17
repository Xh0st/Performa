import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Printer, Receipt, FileText, ArrowRightLeft, Save } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { dt, date, num } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageHeader, Panel, Loading, StatusBadge, STATUS, NativeSelect, Field } from "@/components/common";
import { PartsSection, LaborSection, TotalsBar } from "@/components/wo/LineSections";
import QuotesTab from "@/components/wo/QuotesTab";
import QcTab from "@/components/wo/QcTab";
import TimeTab from "@/components/wo/TimeTab";

const PH = { front: ["Față", "Front"], back: ["Spate", "Rear"], left: ["Stânga", "Left"], right: ["Dreapta", "Right"], interior: ["Interior", "Interior"] };

function DetailsPanel({ wo, onChange, locked }) {
  const { tr } = useLang();
  const { data: mechanics } = useApi("/mechanics");
  const { data: settings } = useApi("/settings");
  const [f, setF] = useState({ diagnosis: wo.diagnosis, elevator: wo.elevator, mechanic_ids: wo.mechanic_ids });
  useEffect(() => {
    setF({ diagnosis: wo.diagnosis, elevator: wo.elevator, mechanic_ids: wo.mechanic_ids });
  }, [wo.diagnosis, wo.elevator, wo.mechanic_ids]);
  const save = async () => {
    try {
      onChange((await api.put(`/work-orders/${wo.id}`, f)).data);
      toast.success(tr("Salvat", "Saved"));
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <Panel title={tr("Diagnostic & alocare", "Diagnosis & assignment")}>
      <div className="space-y-3">
        <Field label={tr("Solicitare client", "Complaint")}><div className="text-sm">{wo.complaint}</div></Field>
        <Field label={tr("Constatare / diagnostic", "Findings / diagnosis")}><Textarea data-testid="wo-diagnosis-input" rows={3} value={f.diagnosis} disabled={locked} onChange={(e) => setF({ ...f, diagnosis: e.target.value })} /></Field>
        <Field label={tr("Elevator", "Lift")}>
          <NativeSelect data-testid="wo-elevator-select" value={f.elevator} disabled={locked} onChange={(e) => setF({ ...f, elevator: e.target.value })}>
            <option value="">—</option>{(settings?.elevators || []).map((x) => <option key={x}>{x}</option>)}
          </NativeSelect>
        </Field>
        <div>
          <div className="eyebrow mb-2">{tr("Mecanici alocați", "Assigned mechanics")}</div>
          <div className="grid grid-cols-2 gap-2">
            {(mechanics || []).map((m) => (
              <label key={m.id} className="flex items-center gap-2 text-sm">
                <Checkbox disabled={locked} data-testid={`wo-mechanic-${m.id}`} checked={f.mechanic_ids.includes(m.id)}
                  onCheckedChange={(c) => setF({ ...f, mechanic_ids: c ? [...f.mechanic_ids, m.id] : f.mechanic_ids.filter((x) => x !== m.id) })} />{m.name}
              </label>
            ))}
          </div>
        </div>
        {!locked && <Button size="sm" data-testid="wo-save-details-button" onClick={save}><Save className="mr-1 h-3 w-3" />{tr("Salvează", "Save")}</Button>}
      </div>
    </Panel>
  );
}

export default function WorkOrderDetail() {
  const { id } = useParams();
  const { tr } = useLang();
  const { can } = useAuth();
  const nav = useNavigate();
  const { data: wo, setData, reload } = useApi(`/work-orders/${id}`);
  const [next, setNext] = useState("");
  if (!wo) return <Loading />;
  const locked = ["facturata", "inchisa"].includes(wo.status);

  const changeStatus = async () => {
    try {
      setData((await api.post(`/work-orders/${id}/status`, { status: next })).data);
      toast.success(tr("Status actualizat", "Status updated"));
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const invoice = async (type) => {
    try {
      const r = await api.post(`/invoices/from-work-order/${id}`, { type });
      toast.success(`${tr("Document emis", "Document issued")} ${r.data.series}${r.data.number}`);
      nav(`/invoices/${r.data.id}`);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <div data-testid="work-order-detail-page">
      <PageHeader eyebrow={`${wo.client_name} · ${wo.vehicle.make} ${wo.vehicle.model} · ${wo.vehicle.plate}`} title={wo.number} testid="wo-number"
        actions={<>
          <StatusBadge status={wo.status} testid="wo-status-badge" />
          <Button variant="outline" size="sm" data-testid="print-reception-button" onClick={() => window.open(`/print/reception/${id}`, "_blank")}><Printer className="mr-1 h-4 w-4" />{tr("Notă recepție / PV", "Reception note")}</Button>
          {can("invoices") && !locked && <Button variant="outline" size="sm" data-testid="create-proforma-button" onClick={() => invoice("proforma")}><FileText className="mr-1 h-4 w-4" />{tr("Proformă", "Proforma")}</Button>}
          {can("invoices") && wo.status === "finalizata" && <Button size="sm" data-testid="create-invoice-button" onClick={() => invoice("fiscal")}><Receipt className="mr-1 h-4 w-4" />{tr("Emite factură", "Issue invoice")}</Button>}
          {wo.invoice_id && <Button size="sm" variant="outline" data-testid="open-invoice-button" asChild><Link to={`/invoices/${wo.invoice_id}`}>{tr("Vezi factura", "View invoice")}</Link></Button>}
        </>} />

      <div className="mb-4 grid gap-3 md:grid-cols-4">
        {[["VIN", wo.vehicle.vin], [tr("Km intrare", "Mileage in"), `${num(wo.mileage_in, 0)} km`], [tr("Recepționat", "Received"), dt(wo.created_at)], [tr("Termen promis", "Promised"), date(wo.promised_date)]].map(([l, v]) => (
          <div key={l} className="rounded border bg-card px-3 py-2"><div className="eyebrow">{l}</div><div className="font-mono text-sm">{v}</div></div>
        ))}
      </div>

      {!locked || wo.status === "facturata" ? (
        <div className="mb-4 flex flex-wrap items-end gap-2 rounded border bg-card p-3">
          <Field label={tr("Schimbă status", "Change status")} className="w-60">
            <NativeSelect data-testid="wo-status-select" value={next} onChange={(e) => setNext(e.target.value)}>
              <option value="">—</option>
              {Object.keys(STATUS).filter((k) => k !== "facturata" && k !== wo.status).map((k) => <option key={k} value={k}>{tr(STATUS[k][0], STATUS[k][1])}</option>)}
            </NativeSelect>
          </Field>
          <Button data-testid="wo-status-apply-button" disabled={!next} onClick={changeStatus}><ArrowRightLeft className="mr-1 h-4 w-4" />{tr("Aplică", "Apply")}</Button>
          <span className="text-xs text-muted-foreground">{tr("Finalizată necesită control calitate promovat; Închisă doar după facturare.", "Completed requires passed QC; Closed only after invoicing.")}</span>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <div className="min-w-0">
        <TotalsBar wo={wo} />
        <Tabs defaultValue="parts">
          <TabsList className="h-auto flex-wrap justify-start">
            <TabsTrigger value="parts" data-testid="wo-tab-parts">{tr("Piese", "Parts")} ({wo.lines.filter((l) => l.type !== "labor").length})</TabsTrigger>
            <TabsTrigger value="labor" data-testid="wo-tab-labor">{tr("Manoperă", "Labor")} ({wo.lines.filter((l) => l.type === "labor").length})</TabsTrigger>
            <TabsTrigger value="quotes" data-testid="wo-tab-quotes">{tr("Devize", "Quotes")} ({wo.quotes?.length || 0})</TabsTrigger>
            <TabsTrigger value="qc" data-testid="wo-tab-qc">{tr("Control calitate", "Quality control")}</TabsTrigger>
            <TabsTrigger value="time" data-testid="wo-tab-time">{tr("Pontaj", "Time")}</TabsTrigger>
            <TabsTrigger value="reception" data-testid="wo-tab-reception">{tr("Recepție", "Reception")}</TabsTrigger>
            <TabsTrigger value="history" data-testid="wo-tab-history">{tr("Istoric", "History")}</TabsTrigger>
          </TabsList>
          <TabsContent value="parts"><Panel><PartsSection wo={wo} onChange={setData} locked={locked} /></Panel></TabsContent>
          <TabsContent value="labor"><Panel><LaborSection wo={wo} onChange={setData} locked={locked} /></Panel></TabsContent>
          <TabsContent value="quotes"><Panel><QuotesTab wo={wo} onChange={reload} /></Panel></TabsContent>
          <TabsContent value="qc"><Panel><QcTab key={wo.qc?.at || "new"} wo={wo} onChange={setData} locked={locked} /></Panel></TabsContent>
          <TabsContent value="time"><Panel><TimeTab wo={wo} onChange={setData} /></Panel></TabsContent>
          <TabsContent value="reception">
            <Panel>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                {Object.keys(PH).map((k) => (
                  <div key={k} className="aspect-[4/3] overflow-hidden rounded border bg-muted/40">
                    {wo.reception?.photos?.[k] ? <img src={wo.reception.photos[k]} alt={k} className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-xs text-muted-foreground">{tr(...PH[k])}</div>}
                  </div>
                ))}
              </div>
              <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
                <div><div className="eyebrow">{tr("Combustibil", "Fuel")}</div>{wo.reception?.fuel_level}</div>
                <div><div className="eyebrow">{tr("Accesorii", "Accessories")}</div>{(wo.reception?.accessories || []).join(", ") || "—"}</div>
                <div><div className="eyebrow">{tr("Daune", "Damage")}</div>{(wo.reception?.damages || []).join("; ") || "—"}</div>
              </div>
              {wo.reception?.signature && <img src={wo.reception.signature} alt="signature" className="mt-4 h-24 rounded border bg-white" />}
            </Panel>
          </TabsContent>
          <TabsContent value="history">
            <Panel>
              <ol className="relative ml-2 border-l">
                {[...wo.status_history].reverse().map((h, i) => (
                  <li key={i} className="mb-4 ml-4">
                    <span className="absolute -left-1.5 mt-1 h-3 w-3 rounded-full border-2 border-primary bg-background" />
                    <div className="flex items-center gap-2"><StatusBadge status={h.status} /><span className="font-mono text-xs text-muted-foreground">{dt(h.at)}</span></div>
                    <div className="mt-1 text-sm">{h.by}{h.note ? ` — ${h.note}` : ""}</div>
                  </li>
                ))}
              </ol>
            </Panel>
          </TabsContent>
        </Tabs>
        </div>
        <DetailsPanel wo={wo} onChange={setData} locked={locked} />
      </div>
    </div>
  );
}
