import { useEffect, useState } from "react";
import { ExternalLink, Download } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Loading } from "@/components/common";

export default function PdfFrame({ path, filename = "factura.pdf", className = "h-[70vh]" }) {
  const { tr } = useLang();
  const [url, setUrl] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let u = null;
    let alive = true;
    api.get(path, { responseType: "blob" })
      .then((r) => {
        u = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
        if (alive) setUrl(u);
      })
      .catch((e) => alive && setErr(errMsg(e)));
    return () => {
      alive = false;
      if (u) URL.revokeObjectURL(u);
    };
  }, [path]);
  if (err) return <div className="text-sm text-rose-500" data-testid="pdf-error">{err}</div>;
  if (!url) return <Loading />;
  return (
    <div data-testid="pdf-frame">
      <div className="mb-2 flex gap-3 text-xs">
        <a className="inline-flex items-center gap-1 text-primary" href={url} target="_blank" rel="noreferrer" data-testid="pdf-open-tab-link"><ExternalLink className="h-3 w-3" />{tr("Deschide în tab nou", "Open in new tab")}</a>
        <a className="inline-flex items-center gap-1 text-primary" href={url} download={filename} data-testid="pdf-download-link"><Download className="h-3 w-3" />{tr("Descarcă PDF", "Download PDF")}</a>
      </div>
      <iframe
        title="PDF e-Factura"
        data-testid="pdf-document-frame"
        src={url}
        className={`w-full rounded border bg-white ${className}`}
      />
    </div>
  );
}
