import { useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2, XCircle } from "lucide-react";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, num, date } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import SignaturePad from "@/components/SignaturePad";
import { Field } from "@/components/common";

export default function PublicQuote() {
  const { token } = useParams();
  const { tr, lang, setLang } = useLang();
  const { data, error, reload } = useApi(`/public/quotes/${token}`);
  const [sig, setSig] = useState("");
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const decide = async (approved) => {
    try {
      await api.post(`/public/quotes/${token}/decision`, { approved, signature: approved ? sig : "", name });
      reload();
    } catch (e) {
      setMsg(errMsg(e));
    }
  };
  if (error) return <div className="p-10 text-center" data-testid="public-quote-error">{error}</div>;
  if (!data) return null;
  const q = data.quote;
  const open = ["draft", "sent"].includes(q.status);
  return (
    <div className="grid-bg min-h-screen p-4 sm:p-10" data-testid="public-quote-page">
      <div className="mx-auto max-w-3xl rounded-md border bg-card p-6 shadow-xl sm:p-8">
        <div className="flex items-start justify-between">
          <div><div className="eyebrow">{data.company}</div><h1 className="font-heading text-3xl font-extrabold uppercase">{tr("Deviz", "Quote")} {q.number}</h1>
            <div className="text-sm text-muted-foreground">{data.client} · {data.vehicle} · {data.work_order}</div></div>
          <Button variant="outline" size="sm" className="font-mono" onClick={() => setLang(lang === "ro" ? "en" : "ro")}>{lang.toUpperCase()}</Button>
        </div>
        <table className="mt-6 w-full text-sm"><thead><tr className="border-b text-left text-xs uppercase text-muted-foreground"><th className="py-2">{tr("Descriere", "Description")}</th><th className="text-right">{tr("Cant.", "Qty")}</th><th className="text-right">{tr("Valoare", "Net")}</th></tr></thead>
          <tbody>{q.lines.map((l) => <tr key={l.id} className="h-9 border-b border-border/50"><td>{l.description}</td><td className="text-right font-mono">{num(l.qty)} {l.unit}</td><td className="text-right font-mono">{money(l.net)}</td></tr>)}</tbody></table>
        <div className="ml-auto mt-4 grid max-w-xs gap-1 text-sm">
          <div className="flex justify-between"><span>{tr("Fără TVA", "Net")}</span><span className="font-mono">{money(q.totals.net)}</span></div>
          <div className="flex justify-between"><span>TVA</span><span className="font-mono">{money(q.totals.vat)}</span></div>
          <div className="flex justify-between border-t pt-1 text-lg font-bold"><span>Total</span><span className="font-mono text-primary">{money(q.totals.gross)}</span></div>
          <div className="text-xs text-muted-foreground">{tr("Valabil până la", "Valid until")} {date(q.valid_until)}</div>
        </div>
        {open ? (
          <div className="mt-6 space-y-3 border-t pt-6">
            <Field label={tr("Numele dvs.", "Your name")}><Input data-testid="public-quote-name-input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <div className="eyebrow">{tr("Semnătură", "Signature")}</div>
            <SignaturePad testid="public-quote-signature" value="" onChange={setSig} />
            {msg && <div className="text-sm text-destructive">{msg}</div>}
            <div className="flex gap-2">
              <Button data-testid="public-quote-approve-button" disabled={!sig || !name} onClick={() => decide(true)}><CheckCircle2 className="mr-1 h-4 w-4" />{tr("Aprob devizul", "Approve quote")}</Button>
              <Button variant="outline" data-testid="public-quote-reject-button" onClick={() => decide(false)}><XCircle className="mr-1 h-4 w-4" />{tr("Refuz", "Reject")}</Button>
            </div>
          </div>
        ) : (
          <div data-testid="public-quote-result" className={`mt-6 rounded border p-4 text-center font-semibold ${q.status === "approved" ? "border-emerald-500/40 text-emerald-500" : "border-rose-500/40 text-rose-500"}`}>
            {q.status === "approved" ? tr("Deviz aprobat. Vă mulțumim!", "Quote approved. Thank you!") : q.status === "rejected" ? tr("Deviz refuzat.", "Quote rejected.") : tr("Acest deviz nu mai este activ.", "This quote is no longer active.")}
          </div>
        )}
      </div>
    </div>
  );
}
