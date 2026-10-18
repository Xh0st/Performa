import { useState } from "react";
import { toast } from "sonner";
import { FilePlus2, Mail, MessageSquare, Phone, Copy, Printer, Check, X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, dt, date } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Badge, Empty, Field } from "@/components/common";
import SignaturePad from "@/components/SignaturePad";

export const Q_STATUS = {
  draft: ["Ciornă", "Draft", "bg-slate-500/10 text-slate-400 border-slate-500/30"],
  sent: ["Trimis", "Sent", "bg-blue-500/10 text-blue-500 border-blue-500/30"],
  approved: ["Aprobat", "Approved", "bg-emerald-500/10 text-emerald-500 border-emerald-500/30"],
  rejected: ["Respins", "Rejected", "bg-rose-500/10 text-rose-500 border-rose-500/30"],
  superseded: ["Înlocuit", "Superseded", "bg-muted text-muted-foreground border-border"],
};

export default function QuotesTab({ wo, onChange }) {
  const { tr } = useLang();
  const [approve, setApprove] = useState(null);
  const [sig, setSig] = useState("");
  const [name, setName] = useState("");
  const [paperApproved, setPaperApproved] = useState(false);
  const quotes = [...(wo.quotes || [])].reverse();
  const link = (q) => `${window.location.origin}/approve/${q.token}`;

  const run = async (fn, msg) => {
    try {
      await fn();
      if (msg) toast.success(msg);
      onChange();
      return true;
    } catch (e) {
      toast.error(errMsg(e));
      return false;
    }
  };
  const create = () => run(() => api.post(`/work-orders/${wo.id}/quotes`, { valid_days: 7 }), tr("Deviz generat", "Quote generated"));
  const send = (q, channel) => run(() => api.post(`/work-orders/${wo.id}/quotes/${q.version}/send`, { channel, link: link(q) }),
    tr(`Trimis prin ${channel} (SIMULAT)`, `Sent via ${channel} (SIMULATED)`));
  const decide = async (q, approved) => {
    const saved = await run(
      () => api.post(`/work-orders/${wo.id}/quotes/${q.version}/decision`, {
        approved,
        signature: approved ? sig : "",
        paper_approved: approved && paperApproved,
        name,
      }),
      approved ? tr("Deviz aprobat", "Quote approved") : tr("Deviz respins", "Quote rejected")
    );
    if (saved) setApprove(null);
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{tr("Fiecare generare creează o versiune nouă (istoric versiuni).", "Each generation creates a new version (version history).")}</p>
        <Button data-testid="create-quote-button" onClick={create} disabled={!wo.lines.length || ["facturata", "inchisa"].includes(wo.status)}>
          <FilePlus2 className="mr-1 h-4 w-4" />{tr("Generează deviz", "Generate quote")}
        </Button>
      </div>
      {!quotes.length && <Empty text={tr("Niciun deviz.", "No quotes.")} />}
      <div className="space-y-3">
        {quotes.map((q) => (
          <div key={q.version} data-testid={`quote-v${q.version}`} className="rounded border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <span className="font-mono font-semibold">{q.number}</span>
                <Badge map={Q_STATUS} value={q.status} testid={`quote-v${q.version}-status`} />
              </div>
              <span className="font-mono text-lg font-semibold text-primary">{money(q.totals.gross)}</span>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">{dt(q.created_at)} · {q.created_by} · {tr("valabil până la", "valid until")} {date(q.valid_until)} · {q.lines.length} {tr("poziții", "items")}</div>
            {q.decision && <div className="mt-1 flex flex-wrap items-center gap-1 text-xs">{tr("Decizie", "Decision")}: {q.decision.name} · {q.decision.via} · {dt(q.decision.at)}{q.decision.paper_approved && <span className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-amber-700 dark:text-amber-300" data-testid={`quote-v${q.version}-paper-approved`}>{tr("Aprobat pe hârtie", "Approved on paper")}</span>}{q.decision.invalidated_reason && <span className="rounded border border-rose-500/40 bg-rose-500/10 px-1.5 py-0.5 text-rose-700 dark:text-rose-300" data-testid={`quote-v${q.version}-invalidated`}>{tr("Invalidat după modificare", "Invalidated after changes")}</span>}</div>}
            {!!q.sent?.length && <div className="mt-1 text-xs text-muted-foreground">{tr("Trimis", "Sent")}: {q.sent.map((s) => `${s.channel} → ${s.to}`).join("; ")}</div>}
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" data-testid={`quote-v${q.version}-print`} onClick={() => window.open(`/print/quote/${wo.id}?v=${q.version}`, "_blank")}><Printer className="mr-1 h-3 w-3" />{tr("Tipărește", "Print")}</Button>
              {["draft", "sent"].includes(q.status) && (
                <>
                  <Button size="sm" variant="outline" data-testid={`quote-v${q.version}-copy-link`} onClick={() => { navigator.clipboard?.writeText(link(q)); toast.success(tr("Link aprobare copiat", "Approval link copied")); }}><Copy className="mr-1 h-3 w-3" />Link</Button>
                  <Button size="sm" variant="outline" data-testid={`quote-v${q.version}-send-email`} onClick={() => send(q, "email")}><Mail className="mr-1 h-3 w-3" />Email</Button>
                  <Button size="sm" variant="outline" data-testid={`quote-v${q.version}-send-sms`} onClick={() => send(q, "sms")}><Phone className="mr-1 h-3 w-3" />SMS</Button>
                  <Button size="sm" variant="outline" data-testid={`quote-v${q.version}-send-whatsapp`} onClick={() => send(q, "whatsapp")}><MessageSquare className="mr-1 h-3 w-3" />WhatsApp</Button>
                  <Button size="sm" data-testid={`quote-version-approve-button-${q.version}`} onClick={() => { setApprove(q); setSig(""); setName(wo.client_name); setPaperApproved(false); }}><Check className="mr-1 h-3 w-3" />{tr("Aprobă", "Approve")}</Button>
                  <Button size="sm" variant="destructive" data-testid={`quote-v${q.version}-reject`} onClick={() => decide(q, false)}><X className="mr-1 h-3 w-3" />{tr("Respinge", "Reject")}</Button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
      <Dialog open={!!approve} onOpenChange={(o) => !o && setApprove(null)}>
        <DialogContent data-testid="quote-approve-dialog">
          <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{tr("Aprobare deviz", "Approve quote")} {approve?.number}</DialogTitle></DialogHeader>
          <Field label={tr("Nume client", "Customer name")}><Input data-testid="quote-approve-name-input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <div className="eyebrow mt-2">{tr("Semnătură client", "Customer signature")}</div>
          <SignaturePad testid="quote-approve-signature" value="" onChange={setSig} />
          <label className="mt-3 flex items-center gap-2 text-sm" data-testid="quote-paper-approval-label">
            <Checkbox data-testid="quote-paper-approval-checkbox" checked={paperApproved} onCheckedChange={setPaperApproved} />
            {tr("Aprobat client (deviz semnat pe hârtie)", "Approved by customer (quote signed on paper)")}
          </label>
          <DialogFooter><Button data-testid="quote-approve-confirm-button" disabled={!sig && !paperApproved} onClick={() => decide(approve, true)}>{tr("Confirmă aprobarea", "Confirm approval")}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
