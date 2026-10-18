import { useState } from "react";
import { Download, FileText, Printer, Search } from "lucide-react";
import { api, downloadFile, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, NativeSelect, PageHeader, Panel } from "@/components/common";

const today = new Date().toISOString().slice(0, 10);
const firstDay = `${today.slice(0, 8)}01`;

export default function FinalInspectionReport() {
  const { tr } = useLang();
  const { data: inspectors } = useApi("/reports/final-inspections/inspectors");
  const [filters, setFilters] = useState({ start: firstDay, end: today, inspector: "" });
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const params = new URLSearchParams(filters).toString();
  const generate = async () => {
    try {
      const response = await api.get(`/reports/final-inspections?${params}`);
      setReport(response.data);
      setError("");
    } catch (requestError) {
      setError(errMsg(requestError));
    }
  };
  const exportFile = (kind) => downloadFile(`/reports/final-inspections/${kind}?${params}`, `anexa5_${filters.start}_${filters.end}.${kind}`);
  const print = () => window.open(`/reports/final-inspections/pdf?${params}`, "_blank");
  return (
    <div data-testid="final-inspection-report-page">
      <PageHeader eyebrow={tr("Rapoarte · control calitate · conformitate RAR", "Reports · quality control · RAR compliance")} title={tr("Registru inspecții finale", "Final inspections register")} />
      <Panel title={tr("Filtre raport Anexa 5 RAR", "RAR Annex 5 report filters")} testid="final-inspection-filters">
        <div className="grid gap-3 md:grid-cols-4">
          <Field label={tr("Data început", "Start date")}><Input data-testid="anexa-start-input" type="date" value={filters.start} onChange={(event) => setFilters({ ...filters, start: event.target.value })} /></Field>
          <Field label={tr("Data sfârșit", "End date")}><Input data-testid="anexa-end-input" type="date" value={filters.end} onChange={(event) => setFilters({ ...filters, end: event.target.value })} /></Field>
          <Field label={tr("Inspector / evaluator", "Inspector / evaluator")}><NativeSelect data-testid="anexa-inspector-select" value={filters.inspector} onChange={(event) => setFilters({ ...filters, inspector: event.target.value })}><option value="">{tr("Toți", "All")}</option>{(inspectors || []).map((name) => <option key={name}>{name}</option>)}</NativeSelect></Field>
          <div className="flex items-end"><Button data-testid="anexa-generate-button" onClick={generate}><Search className="mr-1 h-4 w-4" />{tr("Generează raport", "Generate report")}</Button></div>
        </div>
        {error && <div className="mt-3 text-sm text-rose-500" data-testid="anexa-error">{error}</div>}
      </Panel>
      {report && <Panel className="mt-4" title={`${tr("Punct de lucru", "Branch")}: ${report.branch}`} testid="anexa-results" actions={<div className="flex flex-wrap gap-2"><Button variant="outline" size="sm" data-testid="anexa-export-pdf" onClick={() => print()}><FileText className="mr-1 h-4 w-4" />PDF / Print</Button><Button variant="outline" size="sm" data-testid="anexa-export-csv" onClick={() => exportFile("csv")}><Download className="mr-1 h-4 w-4" />CSV</Button><Button variant="outline" size="sm" data-testid="anexa-export-xlsx" onClick={() => exportFile("xlsx")}><Download className="mr-1 h-4 w-4" />Excel</Button><Button variant="outline" size="sm" data-testid="anexa-print-button" onClick={print}><Printer className="h-4 w-4" /></Button></div>}><div className="overflow-x-auto"><table className="w-full min-w-[1500px] text-xs" data-testid="anexa-table"><thead><tr className="border-b text-left uppercase text-muted-foreground">{["#", "Comandă", "Data", "Vehicul", "Noxe", "Frâne", "Geometrie", "Faruri", "Reglaje", "Etanșeitate", "Probă", "Prezentat de", "Inspector"].map((label) => <th key={label} className="px-2 py-2">{label}</th>)}</tr></thead><tbody>{report.rows.map((row) => <tr key={row.order} className="border-b border-border/50">{row.columns.map((key) => <td key={key} className="px-2 py-2">{row[key]}</td>)}</tr>)}</tbody></table></div>{!report.rows.length && <div className="py-6 text-center text-sm text-muted-foreground" data-testid="anexa-empty">{tr("Nicio inspecție în interval.", "No inspections in this range.")}</div>}</Panel>}
    </div>
  );
}