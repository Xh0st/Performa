import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
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
};

export default function ClosureReview() {
  const { tr } = useLang();
  const { data, reload } = useApi("/closure-exceptions/work-orders");
  const [busy, setBusy] = useState("");
  const review = async (workOrder) => {
    setBusy(workOrder.id);
    try {
      await api.post(`/work-orders/${workOrder.id}/closure-review`, { note: "Verificat administrativ" });
      toast.success(tr("Comandă verificată", "Work order reviewed"));
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
                  <th>{tr("Finalizată", "Completed")}</th>
                  <th>{tr("Revizuire", "Review")}</th>
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
                      <td className="font-mono text-xs">{dt(workOrder.finished_at || workOrder.invoiced_at)}</td>
                      <td>{workOrder.closure_review ? workOrder.closure_review.by : tr("În așteptare", "Pending")}</td>
                      <td>
                        {!workOrder.closure_review && (
                          <Button
                            variant="outline"
                            size="sm"
                            data-testid={`review-closure-${workOrder.number}`}
                            disabled={busy === workOrder.id}
                            onClick={() => review(workOrder)}
                          >
                            <CheckCircle2 className="mr-1 h-4 w-4" />
                            {tr("Verifică", "Review")}
                          </Button>
                        )}
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