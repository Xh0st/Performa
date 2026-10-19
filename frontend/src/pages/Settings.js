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
  const [cuiResult, setCuiResult] = useState(null);
  useEffect(() => {
    if (data) setF({ ...data, elevators_text: (data.elevators || []).join(", ") });
  }, [data]);
  if (!f) return <Loading />;
  const isPremium = f.subscription_plan === "FULL" || f.subscription_plan === "ENTERPRISE";
  const save = async () => {
    try {
      const { elevators_text, ...rest } = f;
      const body = {
        ...rest,
        elevators: (elevators_text || "").split(",").map((s) => s.trim()).filter(Boolean),
        vat_rate: Number(f.vat_rate) || 21,
        payment_terms_days: Number(f.payment_terms_days) || 30,
        labor_rates: Object.fromEntries(
          Object.entries(f.labor_rates || {}).map(([key, value]) => [key, Number(value)]),
        ),
      };
      await api.put("/settings", body);
      toast.success(tr("Setări salvate", "Settings saved"));
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const uploadLogo = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!isPremium || !["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 1024 * 1024) {
      toast.error(tr("Logo acceptat: PNG, JPEG sau WebP, maximum 1 MB", "Logo must be PNG, JPEG, or WebP, maximum 1 MB"));
      return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const { data } = await api.put("/settings/logo", { data_url: reader.result });
        setF((current) => ({ ...current, ...data, elevators_text: (data.elevators || []).join(", ") }));
        toast.success(tr("Logo personalizat salvat", "Custom logo saved"));
      } catch (error) {
        toast.error(errMsg(error));
      }
    };
    reader.readAsDataURL(file);
  };
  const deleteLogo = async () => {
    try {
      const { data } = await api.delete("/settings/logo");
      setF((current) => ({ ...current, ...data, custom_logo_data_url: undefined, custom_logo_mime: undefined, elevators_text: (data.elevators || []).join(", ") }));
      toast.success(tr("Logo personalizat eliminat", "Custom logo removed"));
    } catch (error) { toast.error(errMsg(error)); }
  };
  const lookupCompanyCui = async () => {
    try {
      const { data } = await api.post("/cui/lookup", { cui: f.cui });
      setCuiResult(data);
      if (data.anaf_found) setF({ ...f, cui: data.vat_number || data.cui, name: data.name || f.name, address: data.address || f.address, reg_com: data.reg_com || f.reg_com });
    } catch (error) { toast.error(errMsg(error)); }
  };
  return (
    <div data-testid="settings-page">
      <PageHeader eyebrow={tr("Date apar pe facturi, e-Factura și documente", "Shown on invoices, e-Invoice and documents")} title={tr("Setări companie", "Company settings")}
        actions={<Button data-testid="settings-save-button" onClick={save}>{tr("Salvează", "Save")}</Button>} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={tr("Date firmă", "Company data")}>
          <div className="grid gap-3 sm:grid-cols-2">
            {COMPANY.map(([k, ro, en]) => <Field key={k} label={tr(ro, en)}><div className="flex gap-2"><Input data-testid={`settings-${k}-input`} value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} />{k === "cui" && <Button type="button" variant="outline" data-testid="settings-cui-lookup-button" onClick={lookupCompanyCui}>Importă</Button>}</div></Field>)}
            {cuiResult && <p className="sm:col-span-2 text-sm" data-testid="settings-cui-vat-status">{cuiResult.anaf_found ? (cuiResult.vat_payer ? `Plătitor TVA: ${cuiResult.vat_number}` : "Nu este plătitor de TVA") : "CUI negăsit în ANAF"}</p>}
          </div>
        </Panel>
        <div className="space-y-4">
          <Panel title={tr("Plan & branding", "Plan & branding")}>
            <div className="space-y-3 text-sm">
              <div data-testid="settings-subscription-plan" className="font-semibold">
                {f.subscription_plan || "BASIC"}
              </div>
              <p className="text-muted-foreground" data-testid="settings-plan-limits">
                {`${f.plan_limits?.branches === 999 ? "Locații multiple" : `${f.plan_limits?.branches || 1} locație`}`}
                {` · ${(f.plan_limits?.storage_mb || 500) >= 1024 ? `${(f.plan_limits.storage_mb || 500) / 1024} GB` : `${f.plan_limits?.storage_mb || 500} MB`} storage · `}
                {f.plan_limits?.work_orders_monthly ? `${f.plan_limits.work_orders_monthly} comenzi/lună` : "comenzi nelimitate"}
              </p>
              <Field label={tr("Subdomeniu dedicat", "Dedicated subdomain")}>
                <Input
                  data-testid="settings-custom-subdomain-input"
                  disabled={!isPremium}
                  placeholder="serviceul-meu"
                  value={f.custom_subdomain || ""}
                  onChange={(e) => setF({ ...f, custom_subdomain: e.target.value })}
                />
              </Field>
              <p className="text-muted-foreground" data-testid="settings-logo-plan-note">
                {isPremium
                  ? tr("Logo personalizat pentru documente, maximum 1 MB.", "Custom document logo, maximum 1 MB.")
                  : tr("Planul BASIC folosește branding Performa pe documente.", "BASIC uses Performa branding on documents.")}
              </p>
              <Input
                data-testid="settings-custom-logo-input"
                disabled={!isPremium}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={uploadLogo}
              />
              {isPremium && f.custom_logo_data_url && <div className="flex items-center gap-2"><img src={f.custom_logo_data_url} alt="Logo personalizat" className="h-14 max-w-40 object-contain object-left" data-testid="settings-custom-logo-preview" /><Button type="button" variant="outline" data-testid="settings-custom-logo-delete-button" onClick={deleteLogo}>Elimină logo</Button></div>}
            </div>
          </Panel>
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
              <Field label={tr("Serie facturi", "Invoice series")}><Input data-testid="settings-invoice-series" value={f.invoice_series ?? ""} onChange={(e) => setF({ ...f, invoice_series: e.target.value })} /></Field>
              <Field label={tr("Serie proforme", "Proforma series")}><Input value={f.proforma_series ?? ""} onChange={(e) => setF({ ...f, proforma_series: e.target.value })} /></Field>
              <Field label={tr("Cotă TVA %", "VAT rate %")}><Input data-testid="settings-vat-input" type="number" value={f.vat_rate ?? 21} onChange={(e) => setF({ ...f, vat_rate: e.target.value })} /></Field>
              <Field label={tr("Termen plată (zile)", "Payment terms (days)")}><Input type="number" value={f.payment_terms_days ?? 30} onChange={(e) => setF({ ...f, payment_terms_days: e.target.value })} /></Field>
              <Field label={tr("Elevatoare (separate prin virgulă)", "Lifts (comma separated)")} className="sm:col-span-2">
                <Input data-testid="settings-elevators-input" value={f.elevators_text ?? ""} onChange={(e) => setF({ ...f, elevators_text: e.target.value })} />
              </Field>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
