import { useLang } from "@/lib/prefs";
import { cn } from "@/lib/utils";

export const STATUS = {
  noua: ["Nouă", "New", "bg-blue-500/10 text-blue-500 border-blue-500/30"],
  diagnosticare: ["În diagnosticare", "Diagnosing", "bg-purple-500/10 text-purple-500 border-purple-500/30"],
  asteapta_oferta: ["Așteaptă ofertă", "Awaiting quote", "bg-yellow-500/10 text-yellow-500 border-yellow-500/30"],
  aprobata: ["Aprobată", "Approved", "bg-emerald-500/10 text-emerald-500 border-emerald-500/30"],
  in_lucru: ["În lucru", "In progress", "bg-orange-500/10 text-orange-500 border-orange-500/30"],
  asteapta_piese: ["Așteaptă piese", "Awaiting parts", "bg-rose-500/10 text-rose-500 border-rose-500/30"],
  finalizata: ["Finalizată", "Completed", "bg-teal-500/10 text-teal-500 border-teal-500/30"],
  facturata: ["Facturată", "Invoiced", "bg-cyan-500/10 text-cyan-500 border-cyan-500/30"],
  inchisa: ["Închisă", "Closed", "bg-slate-500/10 text-slate-400 border-slate-500/30"],
};

export const PAY_STATUS = {
  unpaid: ["Neîncasată", "Unpaid", "bg-rose-500/10 text-rose-500 border-rose-500/30"],
  partial: ["Parțial", "Partial", "bg-yellow-500/10 text-yellow-500 border-yellow-500/30"],
  paid: ["Încasată", "Paid", "bg-emerald-500/10 text-emerald-500 border-emerald-500/30"],
};

export const EF_STATUS = {
  not_sent: ["Netransmisă", "Not sent", "bg-slate-500/10 text-slate-400 border-slate-500/30"],
  generated: ["XML generat", "XML generated", "bg-blue-500/10 text-blue-500 border-blue-500/30"],
  in_processing: ["În prelucrare", "Processing", "bg-yellow-500/10 text-yellow-500 border-yellow-500/30"],
  pending: ["În prelucrare ANAF", "Pending ANAF", "bg-yellow-500/10 text-yellow-500 border-yellow-500/30"],
  nok: ["Respinsă ANAF", "Rejected by ANAF", "bg-rose-500/10 text-rose-500 border-rose-500/30"],
  error: ["Eroare structură", "Structure error", "bg-rose-500/10 text-rose-500 border-rose-500/30"],
  invalid: ["Validare internă eșuată", "Internal validation failed", "bg-rose-500/10 text-rose-500 border-rose-500/30"],
  ok: ["Validată ANAF", "ANAF validated", "bg-emerald-500/10 text-emerald-500 border-emerald-500/30"],
};

export const LABOR_CATS = {
  mecanic_junior: ["Mecanic junior", "Junior mechanic"],
  mecanic_senior: ["Mecanic senior", "Senior mechanic"],
  electrician: ["Electrician", "Electrician"],
  tinichigiu: ["Tinichigiu", "Body repair"],
  vopsitor: ["Vopsitor", "Painter"],
  diagnoza: ["Diagnoză", "Diagnostics"],
};

export const ROLE_LABELS = {
  admin: ["Administrator", "Administrator"], director: ["Director", "Director"], sef_service: ["Șef Service", "Service Manager"],
  consilier: ["Consilier Service", "Service Advisor"], receptioner: ["Recepționer", "Receptionist"], magazioner: ["Magazioner", "Storekeeper"],
  mecanic: ["Mecanic", "Mechanic"], electrician: ["Electrician", "Electrician"], tinichigiu: ["Tinichigiu", "Body repair"],
  vopsitor: ["Vopsitor", "Painter"], contabil: ["Contabil", "Accountant"], casier: ["Casier", "Cashier"],
  manager_flota: ["Manager flotă", "Fleet manager"], client: ["Client Portal", "Client Portal"],
};

export function Badge({ map, value, testid }) {
  const { tr } = useLang();
  const m = map[value] || [value, value, "bg-muted text-muted-foreground border-border"];
  return (
    <span data-testid={testid} className={cn("inline-flex items-center whitespace-nowrap rounded-sm border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide", m[2])}>
      {tr(m[0], m[1])}
    </span>
  );
}

export const StatusBadge = ({ status, testid }) => <Badge map={STATUS} value={status} testid={testid} />;

export function PageHeader({ eyebrow, title, actions, testid }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between fade-up">
      <div>
        {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
        <h1 data-testid={testid} className="font-heading text-3xl font-extrabold uppercase tracking-tight sm:text-4xl">{title}</h1>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ title, actions, children, className, testid }) {
  return (
    <section data-testid={testid} className={cn("rounded-md border bg-card fade-up", className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
          <h3 className="font-heading text-lg font-bold uppercase tracking-wide">{title}</h3>
          <div className="flex items-center gap-2">{actions}</div>
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, icon: Icon, accent = "text-primary", testid }) {
  return (
    <div data-testid={testid} className="group rounded-md border bg-card p-4 transition-colors duration-200 hover:border-primary/50 fade-up">
      <div className="flex items-start justify-between">
        <span className="eyebrow">{label}</span>
        {Icon && <Icon className={cn("h-4 w-4", accent)} />}
      </div>
      <div className="mt-2 font-mono text-2xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

export function Field({ label, children, className }) {
  return (
    <label className={cn("flex flex-col gap-1.5", className)}>
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

export function NativeSelect({ className, children, ...props }) {
  return (
    <select
      {...props}
      className={cn("h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring", className)}
    >
      {children}
    </select>
  );
}

export function Empty({ text }) {
  return <div className="py-10 text-center text-sm text-muted-foreground">{text}</div>;
}

export function Loading() {
  return <div className="py-10 text-center font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading…</div>;
}
