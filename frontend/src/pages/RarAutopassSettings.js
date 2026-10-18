import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Save, PlugZap, ShieldAlert, ShieldCheck, Send, LockKeyhole } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { dt } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader, Panel, Loading, Field } from "@/components/common";

const ENVS = [
  ["test", "Test / Sandbox", "Test / Sandbox"],
  ["production", "Producție", "Production"],
];

function EnvironmentSelector({ value, onChange }) {
  const { tr } = useLang();
  return (
    <div className="flex flex-wrap gap-1 rounded-md border bg-background p-1" data-testid="rar-env-switch">
      {ENVS.map(([key, ro, en]) => (
        <button
          key={key}
          type="button"
          data-testid={`rar-env-${key}`}
          onClick={() => onChange(key)}
          className={`rounded px-3 py-1.5 text-xs font-semibold uppercase tracking-wider transition-colors ${
            value === key
              ? key === "production"
                ? "bg-rose-600 text-white"
                : "bg-slate-600 text-white"
              : "text-muted-foreground hover:bg-accent"
          }`}
        >
          {tr(ro, en)}
        </button>
      ))}
    </div>
  );
}

function OutboxState({ item }) {
  const { tr } = useLang();
  const blocked = item.state === "blocked";
  return (
    <tr className="border-b border-border/50" data-testid={`rar-outbox-row-${item.work_order_number}`}>
      <td className="px-2 py-2 font-mono text-xs">{item.work_order_number}</td>
      <td className="px-2 font-mono text-xs">{item.invoice_number}</td>
      <td className="px-2 text-xs">{item.environment === "production" ? "Producție" : "Test"}</td>
      <td className="px-2 text-xs">
        {item.trigger_events?.includes("work_order_closed")
          ? tr("Facturare + închidere", "Invoice + closure")
          : tr("Facturare", "Invoice")}
      </td>
      <td
        className={`px-2 text-xs font-semibold ${
          blocked ? "text-yellow-600 dark:text-yellow-400" : "text-emerald-600 dark:text-emerald-400"
        }`}
      >
        {blocked ? tr("Blocat", "Blocked") : tr("În coadă", "Queued")}
        {blocked && item.blocked_requirements?.length ? ` · ${item.blocked_requirements.join(", ")}` : ""}
      </td>
      <td className="px-2 font-mono text-[11px] text-muted-foreground">{dt(item.updated_at)}</td>
    </tr>
  );
}

export default function RarAutopassSettings() {
  const { tr } = useLang();
  const { data, setData } = useApi("/rar-autopass/config");
  const { data: outbox, reload: reloadOutbox } = useApi("/rar-autopass/outbox");
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!data) return;
    setForm({
      branch_name: data.branch_name,
      authorization_code: data.authorization_code,
      service_cui: data.service_cui,
      environment: data.environment,
      api_token: "",
    });
  }, [data]);

  if (!data || !form) return <Loading />;

  const save = async (successMessage = true) => {
    setBusy(true);
    try {
      const response = await api.put("/rar-autopass/config", form);
      setData(response.data);
      setForm({ ...form, api_token: "" });
      if (successMessage) toast.success(tr("Setări RAR AutoPass salvate", "RAR AutoPass settings saved"));
      return response;
    } catch (error) {
      toast.error(errMsg(error));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const testConnection = async () => {
    const saved = await save(false);
    if (!saved) return;
    try {
      await api.post("/rar-autopass/test-connection");
      toast.success(tr("Conexiune RAR validată", "RAR connection validated"));
    } catch (error) {
      toast.error(errMsg(error));
    }
  };

  const transportReady = data.api_contract_configured && data.has_api_token;
  return (
    <div data-testid="rar-settings-page">
      <PageHeader
        eyebrow={tr("Administrare · punct de lucru · integrare RAR", "Administration · branch · RAR integration")}
        title="RAR AutoPass"
        testid="rar-settings-title"
        actions={(
          <Button data-testid="rar-save-button" disabled={busy} onClick={() => save()}>
            <Save className="mr-1 h-4 w-4" />
            {tr("Salvează", "Save")}
          </Button>
        )}
      />

      <div
        className={`mb-4 flex gap-3 rounded-md border px-4 py-3 ${
          transportReady
            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
            : "border-yellow-500/40 bg-yellow-500/10 text-yellow-700 dark:text-yellow-300"
        }`}
        data-testid="rar-connection-status"
      >
        {transportReady ? <ShieldCheck className="mt-0.5 h-5 w-5" /> : <ShieldAlert className="mt-0.5 h-5 w-5" />}
        <div>
          <div className="font-semibold">{data.status_text}</div>
          <div className="mt-1 text-xs opacity-90">
            {tr(
              "Transmisiile externe sunt dezactivate implicit până la validarea manuală a contractului RAR.",
              "External transmissions are disabled by default until the RAR contract is manually validated."
            )}
          </div>
        </div>
      </div>

      <div className="grid min-w-0 gap-4 xl:grid-cols-2">
        <Panel title={tr("Punct de lucru activ", "Active branch")} testid="rar-branch-panel">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={tr("Denumire punct de lucru", "Branch name")}>
              <Input
                data-testid="rar-branch-name-input"
                value={form.branch_name}
                onChange={(event) => setForm({ ...form, branch_name: event.target.value })}
              />
            </Field>
            <Field label={tr("Cod Autorizație RAR", "RAR authorization code")}>
              <Input
                data-testid="rar-authorization-code-input"
                className="font-mono"
                value={form.authorization_code}
                onChange={(event) => setForm({ ...form, authorization_code: event.target.value })}
                placeholder="BC-1234/2026"
              />
            </Field>
            <Field label={tr("CUI Service / C.I.F.", "Service VAT ID")}>
              <Input
                data-testid="rar-service-cui-input"
                className="font-mono"
                value={form.service_cui}
                onChange={(event) => setForm({ ...form, service_cui: event.target.value })}
              />
            </Field>
            <Field label={tr("Mediu API", "API environment")}>
              <EnvironmentSelector
                value={form.environment}
                onChange={(environment) => setForm({ ...form, environment })}
              />
            </Field>
          </div>
        </Panel>

        <Panel title={tr("Autentificare securizată", "Secure authentication")} testid="rar-auth-panel">
          <Field label={tr("Token de acces RAR", "RAR access token")}>
            <Input
              data-testid="rar-api-token-input"
              type="password"
              className="font-mono"
              value={form.api_token}
              placeholder={data.has_api_token ? "•••••• salvat criptat" : ""}
              onChange={(event) => setForm({ ...form, api_token: event.target.value })}
            />
          </Field>
          <div className="mt-3 flex items-start gap-2 text-xs text-muted-foreground">
            <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              {tr(
                "Tokenul este păstrat criptat pe server și nu este trimis înapoi către browser.",
                "The token is encrypted on the server and is never sent back to the browser."
              )}
            </span>
          </div>
          <Button
            className="mt-4"
            variant="outline"
            data-testid="rar-test-connection-button"
            disabled={busy}
            onClick={testConnection}
          >
            <PlugZap className="mr-1 h-4 w-4" />
            {tr("Salvează și testează conexiunea", "Save and test connection")}
          </Button>
        </Panel>

        <Panel
          title={tr("Coada transmisiilor AutoPass", "AutoPass transmission outbox")}
          className="min-w-0 xl:col-span-2"
          testid="rar-outbox-panel"
          actions={(
            <Button
              variant="outline"
              size="sm"
              data-testid="rar-refresh-outbox-button"
              onClick={reloadOutbox}
            >
              <Send className="mr-1 h-4 w-4" />
              {tr("Actualizează", "Refresh")}
            </Button>
          )}
        >
          {!outbox?.length ? (
            <div className="py-8 text-center text-sm text-muted-foreground" data-testid="rar-outbox-empty">
              {tr(
                "Nicio transmitere pregătită. Evenimentele se creează la facturare și la închiderea comenzii.",
                "No transmission is prepared. Events are created at invoicing and work-order closure."
              )}
            </div>
          ) : (
            <div className="min-w-0 overflow-x-auto">
              <table className="w-full min-w-[920px] text-sm" data-testid="rar-outbox-table">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-2 py-2">{tr("Comandă", "Work order")}</th>
                    <th className="px-2">{tr("Factură", "Invoice")}</th>
                    <th className="px-2">{tr("Mediu", "Environment")}</th>
                    <th className="px-2">{tr("Declanșator", "Trigger")}</th>
                    <th className="px-2">{tr("Stare", "State")}</th>
                    <th className="px-2">{tr("Actualizat", "Updated")}</th>
                  </tr>
                </thead>
                <tbody>{outbox.map((item) => <OutboxState key={item.id} item={item} />)}</tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}