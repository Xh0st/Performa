import { useParams, useSearchParams } from "react-router-dom";
import { Printer } from "lucide-react";
import { useApi } from "@/lib/api";
import { money, num, date, dt } from "@/lib/format";
import { Button } from "@/components/ui/button";

const f2 = (v) => money(v, "").trim();
const addr = (...parts) => parts.filter(Boolean).join(", ") || "—";

const S = {
  th: "border border-slate-400 bg-slate-100 px-2 py-1 text-left text-[11px] font-semibold uppercase",
  td: "border border-slate-300 px-2 py-1 text-[12px]",
  tdr: "border border-slate-300 px-2 py-1 text-right font-mono text-[12px]",
};

function Header({ s, title, number, dateStr }) {
  return (
    <div className="mb-6 flex justify-between border-b-2 border-slate-900 pb-4">
      <div className="text-[12px] leading-5">
        <div className="mb-2 flex items-center gap-2">
          <img
            src={s.subscription_plan !== "BASIC" && s.custom_logo_data_url ? s.custom_logo_data_url : "/performa-logo-dark.png"}
            alt={s.subscription_plan !== "BASIC" ? s.name : "Performa"}
            className="h-6 w-14 object-contain object-left"
            data-testid="print-document-brand-logo"
          />
          {s.subscription_plan === "BASIC" && <span className="font-bold text-[#f47a2a]" data-testid="print-document-brand-name">
            Performa
          </span>}
        </div>
        <div className="text-base font-bold">{s.name}</div>
        <div>CUI: {s.cui} · Reg. Com.: {s.reg_com}</div>
        <div>{addr(s.address, s.city)}</div>
        <div>IBAN: {s.iban} · {s.bank}</div>
        {s.rar_authorization && <div>Autorizație RAR: {s.rar_authorization}</div>}
      </div>
      <div className="text-right">
        <div className="text-2xl font-extrabold uppercase tracking-tight">{title}</div>
        <div className="font-mono text-sm">Nr. {number}</div>
        <div className="text-[12px]">Data: {dateStr}</div>
      </div>
    </div>
  );
}

function PrintFooter({ settings }) {
  if (settings?.subscription_plan !== "BASIC") return null;
  return (
    <div className="print-brand-footer mt-10 border-t pt-2 text-xs text-slate-500">
      Generat cu Performa - performa.net
    </div>
  );
}

function Sign({ labels, images = [] }) {
  return (
    <div className="mt-10 grid grid-cols-2 gap-10 text-[12px]">
      {labels.map((l, i) => (
        <div key={l}><div className="font-semibold">{l}</div><div className="mt-2 flex h-20 items-end border-b border-slate-500">{images[i] && <img src={images[i]} alt="" className="h-20" />}</div></div>
      ))}
    </div>
  );
}

function Lines({ lines }) {
  return (
    <table className="w-full border-collapse">
      <thead><tr><th className={S.th}>Nr.</th><th className={S.th}>Denumire produs / serviciu</th><th className={S.th}>Cod</th><th className={S.th}>UM</th><th className={S.th}>Cant.</th>
        <th className={S.th}>Preț unitar (fără TVA)</th><th className={S.th}>Valoare</th><th className={S.th}>TVA</th></tr></thead>
      <tbody>{lines.map((l, i) => {
        const net = l.net ?? l.qty * l.unit_price * (1 - (l.discount || 0) / 100);
        return (
          <tr key={l.id || i}><td className={S.td}>{i + 1}</td><td className={S.td}>{l.description}</td><td className={S.td}>{l.code}</td><td className={S.td}>{l.unit}</td>
            <td className={S.tdr}>{num(l.qty)}</td><td className={S.tdr}>{f2(l.unit_price)}</td><td className={S.tdr}>{f2(net)}</td><td className={S.tdr}>{f2(l.vat ?? net * (l.vat_rate / 100))}</td></tr>
        );
      })}</tbody>
    </table>
  );
}

function Totals({ t }) {
  return (
    <div className="ml-auto mt-3 w-72 text-[12px]">
      <div className="flex justify-between border-b py-1"><span>Total fără TVA</span><span className="font-mono">{money(t.net)}</span></div>
      <div className="flex justify-between border-b py-1"><span>TVA</span><span className="font-mono">{money(t.vat)}</span></div>
      <div className="flex justify-between py-1 text-base font-bold"><span>TOTAL DE PLATĂ</span><span className="font-mono">{money(t.gross)}</span></div>
    </div>
  );
}

function Reception({ s, w }) {
  const r = w.reception || {};
  return (
    <>
      <Header s={s} title="Notă de recepție / PV predare-primire" number={w.number} dateStr={dt(r.at || w.created_at)} />
      <div className="grid grid-cols-2 gap-6 text-[12px]">
        <div><b>Client:</b> {w.client_name}<br /><b>Telefon:</b> {w.client_phone}</div>
        <div><b>Vehicul:</b> {w.vehicle.make} {w.vehicle.model}{w.vehicle.year ? ` (${w.vehicle.year})` : ""}<br /><b>Nr. înmatriculare:</b> {w.vehicle.plate}<br /><b>VIN:</b> <span className="font-mono">{w.vehicle.vin}</span><br />
          <b>Km la intrare:</b> {num(w.mileage_in, 0)} · <b>Combustibil:</b> {r.fuel_level}</div>
      </div>
      <h3 className="mt-5 text-sm font-bold uppercase">Fișă intrare vehicul / constatare</h3>
      <table className="mt-1 w-full border-collapse text-[12px]"><tbody>
        <tr><td className={S.th}>Solicitare client</td><td className={S.td}>{w.complaint}</td></tr>
        <tr><td className={S.th}>Constatare</td><td className={S.td}>{w.diagnosis || "—"}</td></tr>
        <tr><td className={S.th}>Daune existente</td><td className={S.td}>{(r.damages || []).join("; ") || "Nu s-au constatat"}</td></tr>
        <tr><td className={S.th}>Accesorii predate</td><td className={S.td}>{(r.accessories || []).join(", ") || "—"}</td></tr>
        <tr><td className={S.th}>Observații</td><td className={S.td}>{r.observations || "—"}</td></tr>
        <tr><td className={S.th}>Termen estimat</td><td className={S.td}>{date(w.promised_date)}</td></tr>
      </tbody></table>
      {r.photos && Object.keys(r.photos).length > 0 && (
        <div className="mt-4 grid grid-cols-5 gap-2">{["front", "back", "left", "right", "interior"].map((k) => r.photos[k] && <img key={k} src={r.photos[k]} alt={k} className="aspect-[4/3] w-full border object-cover" />)}</div>
      )}
      <p className="mt-4 text-[11px] text-slate-600">Clientul declară că a predat vehiculul în starea descrisă mai sus și este de acord cu efectuarea diagnosticării. Lucrările suplimentare se execută numai după aprobarea devizului. Datele personale sunt prelucrate conform Regulamentului (UE) 2016/679 (GDPR).</p>
      <Sign labels={["Am predat — Client", "Am primit — Recepționer"]} images={[r.signature]} />
    </>
  );
}

function Quote({ s, w, v }) {
  const q = (w.quotes || []).find((x) => String(x.version) === String(v)) || (w.quotes || []).slice(-1)[0];
  if (!q) return <div>Deviz inexistent</div>;
  return (
    <>
      <Header s={s} title="Deviz estimativ" number={q.number} dateStr={date(q.created_at)} />
      <div className="mb-4 text-[12px]"><b>Client:</b> {w.client_name} · <b>Vehicul:</b> {w.vehicle.make} {w.vehicle.model} · {w.vehicle.plate} · VIN {w.vehicle.vin} · <b>Comandă:</b> {w.number}</div>
      <Lines lines={q.lines} />
      <Totals t={q.totals} />
      <p className="mt-3 text-[11px] text-slate-600">Deviz valabil până la {date(q.valid_until)}. Prețurile pot varia în funcție de constatările din timpul reparației; orice lucrare suplimentară se aprobă separat.</p>
      <Sign labels={["Întocmit — Consilier service", "Aprobat — Client"]} images={[null, q.decision?.signature]} />
    </>
  );
}

function Invoice({ inv, settings }) {
  const s = { ...inv.seller, ...settings };
  const b = inv.buyer;
  return (
    <>
      <Header s={s} title={inv.kind === "credit_note" ? "Factură storno" : inv.type === "fiscal" ? "Factură" : "Factură proformă"} number={`${inv.series} ${inv.number}`} dateStr={date(inv.issue_date)} />
      {inv.kind === "credit_note" && <p className="mb-3 text-[12px]"><b>Stornare la factura nr. {inv.original_ref}</b> din {date(inv.original_issue_date)} · Motiv: {inv.storno_reason}</p>}
      <div className="mb-4 grid grid-cols-2 gap-6 text-[12px]">
        <div><div className="font-bold uppercase">Cumpărător</div>{b.name}<br />{b.cui ? `CUI: ${b.cui}` : `CNP: ${b.cnp}`} {b.reg_com && `· Reg. Com.: ${b.reg_com}`}<br />{addr(b.address, b.city)}</div>
        <div><b>Scadență:</b> {date(inv.due_date)}<br /><b>Comandă lucru:</b> {inv.work_order_number}<br /><b>Vehicul:</b> {inv.vehicle}<br /><b>Km:</b> {num(inv.mileage, 0)}<br /><b>Monedă:</b> {inv.currency}</div>
      </div>
      <Lines lines={inv.lines} />
      <Totals t={inv.totals} />
      {inv.type === "fiscal" && inv.efactura?.upload_index && <p className="mt-2 text-[11px]">e-Factura: index încărcare SPV {inv.efactura.upload_index}</p>}
      <Sign labels={["Semnătura și ștampila furnizorului", "Semnătura de primire"]} />
    </>
  );
}

function ReceiptDoc({ s, p }) {
  const title = { chitanta: "Chitanță", bon_fiscal: "Bon fiscal", dispozitie_incasare: "Dispoziție de încasare", chitanta_externa: "Chitanță externă", bon_pos: "Dovadă plată POS", ordin_plata: "Confirmare încasare OP", confirmare_online: "Confirmare plată online" }[p.doc_type];
  return (
    <>
      <Header s={s} title={title} number={p.doc_number} dateStr={dt(p.document_issue_date || p.date)} />
      <p className="text-[13px] leading-7">Am primit de la <b>{p.client_name}</b> suma de <b className="font-mono">{money(p.amount)}</b>, reprezentând contravaloarea {p.allocations?.length > 1 ? "facturilor" : "facturii"} <b>{p.invoice_ref}</b>.{p.reference && ` Referință: ${p.reference}.`}</p>
      <Sign labels={["Casier", "Client"]} />
    </>
  );
}

function NirDoc({ s, n }) {
  return (
    <>
      <Header s={s} title="Notă de intrare-recepție" number={n.number} dateStr={date(n.date)} />
      <div className="mb-4 text-[12px]"><b>Furnizor:</b> {n.supplier_name} · <b>Factură:</b> {n.invoice_no || "—"} · <b>Aviz:</b> {n.aviz_no || "—"} · <b>Gestiune:</b> {n.warehouse}</div>
      <table className="w-full border-collapse"><thead><tr>{["Nr.", "Cod", "Denumire", "UM", "Cant.", "Preț achiziție", "Valoare", "TVA"].map((h) => <th key={h} className={S.th}>{h}</th>)}</tr></thead>
        <tbody>{n.lines.map((l, i) => <tr key={l.id || `${l.code}-${l.name}-${l.unit}`}><td className={S.td}>{i + 1}</td><td className={S.td}>{l.code}</td><td className={S.td}>{l.name}</td><td className={S.td}>{l.unit}</td>
          <td className={S.tdr}>{num(l.qty)}</td><td className={S.tdr}>{f2(l.unit_cost)}</td><td className={S.tdr}>{f2(l.value)}</td><td className={S.tdr}>{f2(l.vat)}</td></tr>)}</tbody></table>
      <Totals t={{ net: n.total, vat: n.total_vat, gross: n.total + n.total_vat }} />
      <Sign labels={["Comisia de recepție", "Gestionar"]} />
    </>
  );
}

function ReturnDoc({ s, r }) {
  return (
    <>
      <Header s={s} title="Aviz retur către furnizor" number={r.number} dateStr={date(r.date)} />
      <div className="mb-4 text-[12px]"><b>Furnizor:</b> {r.supplier_name} {r.supplier_cui && `(CUI ${r.supplier_cui})`} · <b>NIR origine:</b> {r.nir_number || "—"} · <b>Factură furnizor:</b> {r.nir_invoice_no || "—"}<br /><b>Motiv retur:</b> {r.reason}</div>
      <table className="w-full border-collapse"><thead><tr>{["Nr.", "Cod", "Denumire", "UM", "Cant.", "Preț achiziție", "Valoare", "TVA"].map((h) => <th key={h} className={S.th}>{h}</th>)}</tr></thead>
        <tbody>{r.lines.map((l, i) => <tr key={l.id || `${l.code}-${l.name}-${l.unit}`}><td className={S.td}>{i + 1}</td><td className={S.td}>{l.code}</td><td className={S.td}>{l.name}</td><td className={S.td}>{l.unit}</td>
          <td className={S.tdr}>{num(l.qty)}</td><td className={S.tdr}>{f2(l.unit_cost)}</td><td className={S.tdr}>{f2(l.value)}</td><td className={S.tdr}>{f2(l.vat)}</td></tr>)}</tbody></table>
      <Totals t={{ net: r.total, vat: r.total_vat, gross: r.total + r.total_vat }} />
      <Sign labels={["Predat — Gestionar", "Primit — Delegat furnizor"]} />
    </>
  );
}

function RegisterDoc({ s, r }) {
  return (
    <>
      <Header s={s} title="Registru de casă" number={r.day} dateStr={date(r.day)} />
      <table className="w-full border-collapse"><thead><tr>{["Nr. document", "Explicație", "Încasări", "Plăți"].map((h) => <th key={h} className={S.th}>{h}</th>)}</tr></thead>
        <tbody>
          <tr><td className={S.td} colSpan={2}><b>Sold inițial</b></td><td className={S.tdr}>{f2(r.opening)}</td><td className={S.tdr} /></tr>
          {r.entries.map((e) => <tr key={e.id}><td className={S.td}>{e.doc_number}</td><td className={S.td}>Încasare {e.invoice_ref} — {e.client_name}</td><td className={S.tdr}>{f2(e.amount)}</td><td className={S.tdr}>0,00</td></tr>)}
          <tr><td className={S.td} colSpan={2}><b>Total rulaj zi</b></td><td className={S.tdr}>{f2(r.total_in)}</td><td className={S.tdr}>{f2(r.total_out)}</td></tr>
          <tr><td className={S.td} colSpan={2}><b>Sold final</b></td><td className={S.tdr}>{f2(r.closing)}</td><td className={S.tdr} /></tr>
        </tbody></table>
      <Sign labels={["Casier", "Compartiment financiar-contabil"]} />
    </>
  );
}

const PATHS = { reception: (id) => `/work-orders/${id}`, quote: (id) => `/work-orders/${id}`, invoice: (id) => `/invoices/${id}`, receipt: (id) => `/payments/${id}`, nir: (id) => `/nirs/${id}`, return: (id) => `/supplier-returns/${id}`, register: (id) => `/cash-register?day=${id}` };

export default function PrintDoc() {
  const { kind, id } = useParams();
  const [sp] = useSearchParams();
  const { data: s } = useApi("/settings");
  const { data, error } = useApi(PATHS[kind]?.(id));
  return (
    <div className="min-h-screen bg-slate-200 py-6 text-slate-900">
      {!error && <div className="no-print mx-auto mb-4 flex max-w-[210mm] justify-end"><Button data-testid="print-now-button" onClick={() => window.print()}><Printer className="mr-1 h-4 w-4" />Print / PDF</Button></div>}
      <div data-testid={`print-doc-${kind}`} className="print-doc mx-auto min-h-[297mm] max-w-[210mm] bg-white p-[14mm] shadow-xl">
        {error && <div className="rounded border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive" data-testid="print-doc-error">{error}</div>}
        {s && data && kind === "reception" && <Reception s={s} w={data} />}
        {s && data && kind === "quote" && <Quote s={s} w={data} v={sp.get("v")} />}
        {s && data && kind === "invoice" && <Invoice inv={data} settings={s} />}
        {s && data && kind === "receipt" && <ReceiptDoc s={s} p={data} />}
        {s && data && kind === "nir" && <NirDoc s={s} n={data} />}
        {s && data && kind === "register" && <RegisterDoc s={s} r={data} />}
        {s && data && kind === "return" && <ReturnDoc s={s} r={data} />}
        {s && data && <PrintFooter settings={s} />}
      </div>
    </div>
  );
}
