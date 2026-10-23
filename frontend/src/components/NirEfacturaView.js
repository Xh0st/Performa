import { useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { money, num, date } from "@/lib/format";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loading } from "@/components/common";
import PdfFrame from "@/components/PdfFrame";

function NirSummary({ id }) {
  const { tr } = useLang();
  const { data: n } = useApi(`/nirs/${id}`, [id]);
  if (!n) return <Loading />;
  return (
    <div data-testid="nir-efactura-summary">
      <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
        <div><div className="eyebrow">NIR</div><div className="font-mono">{n.number}</div></div>
        <div><div className="eyebrow">{tr("Data", "Date")}</div>{date(n.date)}</div>
        <div><div className="eyebrow">{tr("Furnizor", "Supplier")}</div>{n.supplier_name}</div>
        <div><div className="eyebrow">{tr("Factură", "Invoice")}</div><span className="font-mono">{n.invoice_no}</span></div>
      </div>
      <table className="w-full text-xs"><thead><tr className="border-b text-left uppercase tracking-wider text-muted-foreground">
        <th className="py-1">Cod</th><th>{tr("Denumire", "Name")}</th><th className="text-right">{tr("Cant.", "Qty")}</th><th className="text-right">{tr("Valoare", "Value")}</th>
      </tr></thead><tbody>
        {n.lines.map((l) => (
          <tr key={l.id || `${l.code}-${l.name}-${l.unit || ""}`} className="h-8 border-b border-border/50"><td className="font-mono">{l.code}</td><td>{l.name}</td>
            <td className="text-right font-mono">{num(l.qty)}{l.returned_qty ? <span className="text-rose-500"> (−{num(l.returned_qty)})</span> : ""}</td><td className="text-right font-mono">{money(l.value)}</td></tr>
        ))}
      </tbody></table>
      <div className="mt-2 text-right font-mono text-sm">{money(n.total)} + TVA {money(n.total_vat)}</div>
    </div>
  );
}

export default function NirEfacturaView({ nir, onClose }) {
  const { tr } = useLang();
  return (
    <Dialog open={!!nir} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-6xl" data-testid="nir-efactura-dialog">
        <DialogHeader><DialogTitle className="font-heading text-2xl uppercase">{tr("NIR și factura e-Factura", "GRN and e-Invoice")}</DialogTitle></DialogHeader>
        {nir && (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <NirSummary id={nir.id} />
            <PdfFrame path={`/efactura/inbox/${nir.efactura_message_id}/pdf`} filename={`efactura_${nir.invoice_no}.pdf`} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
