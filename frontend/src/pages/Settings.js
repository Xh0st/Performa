import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Panel, Loading, Field, LABOR_CATS } from "@/components/common";

const COMPANY = [["name", "Denumire firmă", "Company name"], ["cui", "CUI / CIF", "VAT ID"], ["reg_com", "Nr. Reg. Com.", "Trade reg. no."], ["capital", "Capital social", "Share capital"],
  ["address", "Adresă", "Address"], ["city", "Localitate", "City"], ["county_code", "Cod județ ISO", "County ISO code"], ["iban", "IBAN", "IBAN"], ["bank", "Bancă", "Bank"],
  ["phone", "Telefon", "Phone"], ["email", "Email", "Email"], ["rar_authorization", "Autorizație RAR", "RAR authorization"]];

export default function SettingsPage() {
  const { tr } = useLang();
  const { data } = useApi("/settings");
  const [f, setF] = useState(null);
  useEffect(() => {
    if (data) setF({ ...data, elevators_text: (data.elevators || []).join(", ") });
  }, [data]);
  if (!f) return <Loading />;
  const save = async () => {
    try {
      const { elevators_text, ...rest } = f;
      const body = { ...rest, elevators: elevators_text.split(",").map((s) => s.trim()).filter(Boolean), vat_rate: Number(f.vat_rate), payment_terms_days: Number(f.payment_terms_days),
        labor_rates: Object.fromEntries(Object.entries(f.labor_rates).map(([k, v]) => [k, Number(v)])) };
      await api.put("/settings", body);
      toast.success(tr("Setări salvate", "Settings saved"));
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <div data-testid="settings-page">
      <PageHeader eyebrow={tr("Date apar pe facturi, e-Factura și documente", "Shown on invoices, e-Invoice and documents")} title={tr("Setări companie", "Company settings")}
        actions={<Button data-testid="settings-save-button" onClick={save}>{tr("Salvează", "Save")}</Button>} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={tr("Date firmă", "Company data")}>
          <div className="grid gap-3 sm:grid-cols-2">
            {COMPANY.map(([k, ro, en]) => <Field key={k} label={tr(ro, en)}><Input data-testid={`settings-${k}-input`} value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>)}
          </div>
        </Panel>
        <div className="space-y-4">
          <Panel title={tr("Tarife manoperă (RON/oră, fără TVA)", "Labor rates (RON/h, excl. VAT)")}>
            <div className="grid gap-3 sm:grid-cols-3">
              {Object.keys(LABOR_CATS).map((k) => (
                <Field key={k} label={tr(...LABOR_CATS[k])}>
                  <Input data-testid={`settings-rate-${k}`} type="number" value={f.labor_rates?.[k] ?? ""} onChange={(e) => setF({ ...f, labor_rates: { ...f.labor_rates, [k]: e.target.value } })} />
                </Field>
              ))}
            </div>
          </Panel>
          <Panel title={tr("Facturare & atelier", "Billing & workshop")}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={tr("Serie facturi", "Invoice series")}><Input data-testid="settings-invoice-series" value={f.invoice_series} onChange={(e) => setF({ ...f, invoice_series: e.target.value })} /></Field>
              <Field label={tr("Serie proforme", "Proforma series")}><Input value={f.proforma_series} onChange={(e) => setF({ ...f, proforma_series: e.target.value })} /></Field>
              <Field label={tr("Cotă TVA %", "VAT rate %")}><Input data-testid="settings-vat-input" type="number" value={f.vat_rate} onChange={(e) => setF({ ...f, vat_rate: e.target.value })} /></Field>
              <Field label={tr("Termen plată (zile)", "Payment terms (days)")}><Input type="number" value={f.payment_terms_days} onChange={(e) => setF({ ...f, payment_terms_days: e.target.value })} /></Field>
              <Field label={tr("Elevatoare (separate prin virgulă)", "Lifts (comma separated)")} className="sm:col-span-2">
                <Input data-testid="settings-elevators-input" value={f.elevators_text} onChange={(e) => setF({ ...f, elevators_text: e.target.value })} />
              </Field>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
