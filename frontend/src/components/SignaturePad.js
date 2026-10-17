import { useEffect, useRef } from "react";
import { Eraser } from "lucide-react";
import { useLang } from "@/lib/prefs";

export default function SignaturePad({ value, onChange, testid, height = 160 }) {
  const ref = useRef(null);
  const drawing = useRef(false);
  const { tr } = useLang();

  useEffect(() => {
    const c = ref.current;
    const ctx = c.getContext("2d");
    c.width = c.offsetWidth;
    c.height = height;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, c.width, c.height);
    if (value) {
      const img = new Image();
      img.onload = () => ctx.drawImage(img, 0, 0, c.width, c.height);
      img.src = value;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pos = (e) => {
    const r = ref.current.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  const down = (e) => {
    drawing.current = true;
    const ctx = ref.current.getContext("2d");
    ctx.beginPath();
    ctx.moveTo(...pos(e));
  };
  const move = (e) => {
    if (!drawing.current) return;
    const ctx = ref.current.getContext("2d");
    ctx.lineWidth = 2.2;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#0f172a";
    ctx.lineTo(...pos(e));
    ctx.stroke();
  };
  const up = () => {
    if (!drawing.current) return;
    drawing.current = false;
    onChange(ref.current.toDataURL("image/png"));
  };
  const clear = () => {
    const c = ref.current;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, c.width, c.height);
    onChange("");
  };

  return (
    <div className="relative">
      <canvas
        ref={ref}
        data-testid={testid}
        className="w-full touch-none rounded-md border-2 border-dashed border-primary/40 bg-white"
        style={{ height }}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerLeave={up}
      />
      <button type="button" data-testid={`${testid}-clear`} onClick={clear}
        className="absolute right-2 top-2 inline-flex items-center gap-1 rounded bg-slate-900/80 px-2 py-1 text-xs text-white hover:bg-slate-900">
        <Eraser className="h-3 w-3" /> {tr("Șterge", "Clear")}
      </button>
    </div>
  );
}
