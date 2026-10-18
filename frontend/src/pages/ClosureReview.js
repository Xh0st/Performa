import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { dt } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, Loading } from "@/components/common";

const REASONS = {
  fara_deviz_generat: ["Fără deviz generat", "No quote generated"],
  deviz_respins: ["Deviz respins", "Rejected quote"],
  fara_cost: ["Operațiune fără cost", "No-charge operation"],
  diagnoza: ["Diagnoză", "Diagnosis"],
  constatare: ["Constatare", "Assessment"],
  inchidere_nefacturata: ["Închidere fără factură", "Closed without invoice"],
};

export default function ClosureReview() {
  const { tr } = useLang();
  const { data, reload } = useApi("/closure-exceptions/work-orders");
  const [busy, setBusy] = useState("");
  const review = async (workOrder) => {
    setBusy(workOrder.id);
    try {
      await api.post(`/work-orders/${workOrder.id}/closure-review`, { note: "Aprobat administrativ" });
      toast.success(tr("Închidere aprobată", "Closure approved"));
      reload();
    } catch (error) {
      toast.error(errMsg(error));
    } finally {
      setBusy("");
    }
  };
  const reopen = async (workOrder) => {
    setBusy(workOrder.id);
    try {
      await api.post(`/work-orders/${workOrder.id}/reopen`, { note: "Redeschis din verificare închideri" });
      toast.success(tr("Comandă redeschisă", "Work order reopened"));
      reload();
    } catch (error) {
      toast.error(errMsg(error));
    } finally {
      setBusy("");
    }
  };
  if (!data) return <Loading />;
  return (
    <div data-testid="closure-review-page">
      <PageHeader
        eyebrow={tr("Administrare · conformitate financiară", "Administration · financial compliance")}
        title={tr("Verificare închideri fără deviz aprobat", "Closure review without approved quote")}
      />
      <Panel testid="closure-review-panel">
        {!data.length ? (
          <div className="py-8 text-center text-sm text-muted-foreground" data-testid="closure-review-empty">
            {tr("Nu există comenzi de verificat.", "There are no work orders to review.")}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm" data-testid="closure-review-table">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                  <th className="px-2 py-2">{tr("Comandă", "Work order")}</th>
                  <th>{tr("Client", "Client")}</th>
                  <th>{tr("Motiv", "Reason")}</th>
                  <th>{tr("Închisă", "Closed")}</th>
                  <th>{tr("Aprobare", "Approval")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((workOrder) => {
                  const reason = REASONS[workOrder.closure_quote_rule.reason] || ["—", "—"];
                  return (
                    <tr key={workOrder.id} className="border-b border-border/50">
                      <td className="px-2 py-2 font-mono">
                        <Link
                          className="text-primary underline-offset-4 hover:underline"
                          data-testid={`closure-work-order-link-${workOrder.number}`}
                          to={`/work-orders/${workOrder.id}`}
                        >
                          {workOrder.number}
                        </Link>
                      </td>
                      <td>{workOrder.client_name}</td>
                      <td>{tr(reason[0], reason[1])}</td>
                      <td className="font-mono text-xs">{dt(workOrder.closed_at)}</td>
                      <td>{tr("În așteptare", "Pending")}</td>
                      <td>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            data-testid={`approve-closure-${workOrder.number}`}
                            disabled={busy === workOrder.id}
                            onClick={() => review(workOrder)}
                          >
                            <CheckCircle2 className="mr-1 h-4 w-4" />
                            {tr("Aprobă", "Approve")}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            data-testid={`reopen-closure-${workOrder.number}`}
                            disabled={busy === workOrder.id}
                            onClick={() => reopen(workOrder)}
                          >
                            <RotateCcw className="mr-1 h-4 w-4" />
                            {tr("Redeschide", "Reopen")}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}