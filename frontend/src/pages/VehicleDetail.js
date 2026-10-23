import { Link, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";

import { useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { date, num } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Empty, Loading, PageHeader, Panel, StatusBadge } from "@/components/common";


function Info({ label, value, mono = false }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className={`mt-0.5 text-sm ${mono ? "font-mono" : ""}`}>{value || "—"}</div>
    </div>
  );
}


export default function VehicleDetail() {
  const { id } = useParams();
  const { tr } = useLang();
  const { data: vehicle } = useApi(`/vehicles/${id}`);

  if (!vehicle) return <Loading />;

  return (
    <div data-testid="vehicle-detail-page">
      <PageHeader
        eyebrow={tr("Parc auto clienți", "Client fleet")}
        title={`${vehicle.make} ${vehicle.model}`}
        testid="vehicle-detail-name"
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/vehicles" data-testid="vehicle-detail-back-link">
                <ChevronLeft className="mr-1 h-4 w-4" />
                {tr("Înapoi", "Back")}
              </Link>
            </Button>
          </div>
        )}
      />
      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <Panel title={tr("Date vehicul", "Vehicle data")}>
          <div className="grid grid-cols-2 gap-4">
            <Info label="VIN" value={vehicle.vin} mono />
            <Info label={tr("Nr. înmatriculare", "Plate")} value={vehicle.plate} mono />
            <Info label={tr("An", "Year")} value={vehicle.year} mono />
            <Info label={tr("Kilometraj", "Mileage")} value={`${num(vehicle.mileage, 0)} km`} mono />
            <Info label={tr("Motor", "Engine")} value={vehicle.engine} />
            <Info label={tr("Putere", "Power")} value={`${vehicle.power_kw || "—"} kW`} />
            <Info label={tr("Combustibil", "Fuel")} value={vehicle.fuel} />
            <Info label="Euro" value={vehicle.euro} />
          </div>
        </Panel>
        <Panel title={tr("Proprietar și expirări", "Owner and expiry dates")}>
          <div className="grid grid-cols-2 gap-4">
            <Info label={tr("Proprietar", "Owner")} value={vehicle.client_name} />
            <Info label="ITP" value={date(vehicle.itp_expiry)} mono />
            <Info label="RCA" value={date(vehicle.rca_expiry)} mono />
            <Info label="CASCO" value={date(vehicle.casco_expiry)} mono />
            <Info label={tr("Rovinietă", "Vignette")} value={date(vehicle.rovinieta_expiry)} mono />
          </div>
          <Button asChild variant="outline" size="sm" className="mt-5">
            <Link to={`/clients/${vehicle.client_id}`} data-testid="vehicle-owner-link">
              {tr("Deschide client", "Open client")}
            </Link>
          </Button>
        </Panel>
      </div>
      <Panel title={tr("Istoric Comenzi", "Order history")} className="mt-4">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm" data-testid="vehicle-history-table">
            <tbody>
              {vehicle.history.map((workOrder) => (
                <tr key={workOrder.id} className="h-10 border-b border-border/50">
                  <td>
                    <Link
                      to={`/work-orders/${workOrder.id}`}
                      data-testid={`vehicle-work-order-link-${workOrder.id}`}
                      className="font-mono text-primary hover:underline"
                    >
                      {workOrder.number}
                    </Link>
                  </td>
                  <td>{date(workOrder.created_at)}</td>
                  <td className="max-w-md truncate">{workOrder.complaint}</td>
                  <td className="text-right"><StatusBadge status={workOrder.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!vehicle.history.length && <Empty text="—" />}
      </Panel>
    </div>
  );
}