import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Field, NativeSelect } from "@/components/common";

const EMPTY = {
  type: "pf",
  name: "",
  cnp: "",
  cui: "",
  reg_com: "",
  representative: "",
  phone: "",
  email: "",
  address: "",
  city: "",
  county: "RO-B",
  is_fleet: false,
  budget_limit: 0,
  payment_terms_days: null,
  credit_limit: 0,
  gdpr_consent: false,
  notes: "",
};

export default function ClientForm({ open, onOpenChange, initial, onSaved }) {
  const { tr } = useLang();
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [cuiBusy, setCuiBusy] = useState(false);
  const [cuiResult, setCuiResult] = useState(null);
  useEffect(() => {
    if (open) setF({ ...EMPTY, ...(initial || {}) });
  }, [open, initial]);
  const set = (k) => (e) => setF({ ...f, [k]: e?.target ? e.target.value : e });

  const save = async () => {
    setBusy(true);
    try {
      const isCompany = f.type === "pj";
      const body = {
        ...f,
        budget_limit: Number(f.budget_limit) || 0,
        payment_terms_days: isCompany && f.payment_terms_days !== ""
          ? Number(f.payment_terms_days) || null
          : null,
        credit_limit: isCompany && f.credit_limit !== ""
          ? Number(f.credit_limit)
          : null,
      };
      const r = initial?.id ? await api.put(`/clients/${initial.id}`, body) : await api.post("/clients", body);
      toast.success(tr("Client salvat", "Client saved"));
      onSaved?.(r.data);
      onOpenChange(false);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const lookupCui = async () => {
    setCuiBusy(true);
    try {
      const { data } = await api.post("/cui/lookup", { cui: f.cui });
      setCuiResult(data);
      if (data.anaf_found) setF({ ...f, cui: data.vat_number || data.cui, name: data.name || f.name, address: data.address || f.address, reg_com: data.reg_com || f.reg_com });
    } catch (error) { toast.error(errMsg(error)); } finally { setCuiBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="client-form-dialog">
        <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{initial?.id ? tr("Editare client", "Edit client") : tr("Client nou", "New client")}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={tr("Tip client", "Client type")}>
            <NativeSelect
              data-testid="client-type-select"
              value={f.type}
              onChange={(event) => setF({
                ...f,
                type: event.target.value,
                payment_terms_days: event.target.value === "pj" ? f.payment_terms_days : null,
                credit_limit: event.target.value === "pj" ? f.credit_limit ?? 0 : null,
              })}
            >
              <option value="pf">{tr("Persoană fizică", "Individual")}</option>
              <option value="pj">{tr("Persoană juridică", "Company")}</option>
            </NativeSelect>
          </Field>
          <Field label={f.type === "pf" ? tr("Nume complet", "Full name") : tr("Denumire firmă", "Company name")}>
            <Input data-testid="client-name-input" value={f.name} onChange={set("name")} />
          </Field>
          {f.type === "pf" ? (
            <Field label="CNP"><Input data-testid="client-cnp-input" className="font-mono" maxLength={13} value={f.cnp} onChange={set("cnp")} /></Field>
          ) : (
            <>
              <Field label="CUI"><div className="flex gap-2"><Input data-testid="client-cui-input" className="font-mono" value={f.cui} onChange={set("cui")} placeholder="RO12345678" /><Button type="button" variant="outline" data-testid="client-cui-lookup-button" disabled={cuiBusy || !f.cui} onClick={lookupCui}>{cuiBusy ? "Verific…" : "Importă"}</Button></div></Field>
              {cuiResult && <div className="sm:col-span-2 text-sm" data-testid="client-cui-vat-status">{cuiResult.anaf_found ? (cuiResult.vat_payer ? `Plătitor TVA: ${cuiResult.vat_number}` : "Nu este plătitor de TVA") : "CUI negăsit în ANAF"}</div>}
              <Field label={tr("Nr. Reg. Comerțului", "Trade register no.")}><Input data-testid="client-regcom-input" className="font-mono" value={f.reg_com} onChange={set("reg_com")} placeholder="J40/123/2020" /></Field>
              <Field label={tr("Reprezentant", "Representative")}><Input data-testid="client-rep-input" value={f.representative} onChange={set("representative")} /></Field>
            </>
          )}
          <Field label={tr("Telefon", "Phone")}><Input data-testid="client-phone-input" value={f.phone} onChange={set("phone")} /></Field>
          <Field label="Email"><Input data-testid="client-email-input" type="email" value={f.email} onChange={set("email")} /></Field>
          <Field label={tr("Adresă", "Address")} className="sm:col-span-2"><Input data-testid="client-address-input" value={f.address} onChange={set("address")} /></Field>
          <Field label={tr("Localitate", "City")}><Input data-testid="client-city-input" value={f.city} onChange={set("city")} /></Field>
          <Field label={tr("Cod județ (ISO)", "County code (ISO)")}><Input data-testid="client-county-input" className="font-mono" value={f.county} onChange={set("county")} placeholder="RO-B" /></Field>
          {f.type === "pj" && (
            <>
              <div className="flex items-center gap-3 pt-5"><Switch data-testid="client-fleet-switch" checked={f.is_fleet} onCheckedChange={set("is_fleet")} /><span className="text-sm">{tr("Client flotă", "Fleet client")}</span></div>
              <Field label={tr("Limită buget / comandă (RON)", "Budget limit / order (RON)")}><Input data-testid="client-budget-input" type="number" value={f.budget_limit} onChange={set("budget_limit")} /></Field>
              <Field label={tr("Termen de plată preferențial (zile)", "Preferred payment term (days)")}>
                <Input
                  data-testid="client-payment-terms-input"
                  type="number"
                  min="1"
                  max="365"
                  placeholder="CASH"
                  value={f.payment_terms_days ?? ""}
                  onChange={set("payment_terms_days")}
                />
              </Field>
              <Field label={tr("Limită de credit (RON)", "Credit limit (RON)")}>
                <Input
                  data-testid="client-credit-limit-input"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0,00"
                  value={f.credit_limit ?? 0}
                  onChange={set("credit_limit")}
                />
              </Field>
            </>
          )}
          <div className="flex items-center gap-3 sm:col-span-2">
            <Switch data-testid="client-gdpr-switch" checked={f.gdpr_consent} onCheckedChange={set("gdpr_consent")} />
            <span className="text-sm">{tr("Acord GDPR prelucrare date & notificări", "GDPR consent for data processing & notifications")}</span>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{tr("Anulează", "Cancel")}</Button>
          <Button data-testid="client-save-button" onClick={save} disabled={busy || !f.name}>{tr("Salvează", "Save")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
