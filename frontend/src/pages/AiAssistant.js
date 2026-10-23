import { useState } from "react";
import { Sparkles, Stethoscope, Send } from "lucide-react";
import Markdown from "react-markdown";
import { API_URL, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { dt } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader, Panel, Field, NativeSelect } from "@/components/common";

const QUICK = {
  advisor: [["Ce lucrări recomanzi la următoarea vizită?", "What work do you recommend at the next visit?"], ["Estimează costul reviziei mari.", "Estimate the cost of a major service."]],
  obd: [["P0300 – rateuri aleatorii, motorul tremură la ralanti", "P0300 – random misfire, rough idle"], ["P0401 + P2002, lipsă putere", "P0401 + P2002, lack of power"]],
};

export default function AiAssistant() {
  const { tr, lang } = useLang();
  const [mode, setMode] = useState("advisor");
  const [vehicleId, setVehicleId] = useState("");
  const [msg, setMsg] = useState("");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: vehicles } = useApi("/vehicles");
  const { data: history, reload } = useApi("/ai/history");

  const ask = async (text) => {
    const message = text || msg;
    if (!message.trim()) return;
    setBusy(true);
    setAnswer("");
    try {
      const res = await fetch(`${API_URL}/ai/stream`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, message, vehicle_id: vehicleId, lang }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        setAnswer((a) => a + dec.decode(value, { stream: true }));
      }
      reload();
    } catch (e) {
      setAnswer(`[${e.message}]`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="ai-page">
      <PageHeader eyebrow="Gemini · AI Service Advisor · AI Diagnostic OBD" title={tr("Asistent AI", "AI Assistant")} />
      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <Panel>
          <div className="mb-4 flex gap-2">
            <Button variant={mode === "advisor" ? "default" : "outline"} data-testid="ai-mode-advisor" onClick={() => setMode("advisor")}><Sparkles className="mr-1 h-4 w-4" />Service Advisor</Button>
            <Button variant={mode === "obd" ? "default" : "outline"} data-testid="ai-mode-obd" onClick={() => setMode("obd")}><Stethoscope className="mr-1 h-4 w-4" />{tr("Diagnostic OBD", "OBD Diagnostic")}</Button>
          </div>
          <Field label={tr("Vehicul (context istoric)", "Vehicle (history context)")}>
            <NativeSelect data-testid="ai-vehicle-select" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
              <option value="">{tr("— fără vehicul —", "— no vehicle —")}</option>
              {(vehicles || []).map((v) => <option key={v.id} value={v.id}>{v.plate} · {v.make} {v.model} · {v.client_name}</option>)}
            </NativeSelect>
          </Field>
          <Textarea data-testid="ai-message-input" className="mt-3" rows={3} value={msg} onChange={(e) => setMsg(e.target.value)}
            placeholder={mode === "obd" ? tr("Introduceți coduri DTC și simptome…", "Enter DTC codes and symptoms…") : tr("Întrebați despre lucrări recomandate, costuri…", "Ask about recommended work, costs…")} />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {QUICK[mode].map(([ro, en]) => <button key={ro} type="button" className="rounded-full border px-3 py-1 text-xs hover:border-primary" onClick={() => { setMsg(tr(ro, en)); ask(tr(ro, en)); }}>{tr(ro, en)}</button>)}
            <div className="flex-1" />
            <Button data-testid="ai-advisor-ask-button" disabled={busy || !msg.trim()} onClick={() => ask()}><Send className="mr-1 h-4 w-4" />{busy ? tr("Analizează…", "Analysing…") : tr("Întreabă", "Ask")}</Button>
          </div>
          <div data-testid="ai-answer" className="ai-md mt-4 min-h-[200px] rounded border border-purple-500/30 bg-purple-500/5 p-4 text-sm leading-relaxed">
            {answer ? <Markdown>{answer}</Markdown> : <span className="text-muted-foreground">{tr("Răspunsul AI va apărea aici în timp real.", "The AI answer will stream here.")}</span>}
          </div>
        </Panel>
        <Panel title={tr("Istoric", "History")}>
          <div className="max-h-[60vh] space-y-2 overflow-y-auto">
            {(history || []).map((h) => (
              <button key={h.id} type="button" onClick={() => { setAnswer(h.answer); setMsg(h.question); setMode(h.mode); }} className="block w-full rounded border p-2 text-left hover:border-primary/60">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{h.mode} · {dt(h.at)}</div>
                <div className="line-clamp-2 text-xs">{h.question}</div>
              </button>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
