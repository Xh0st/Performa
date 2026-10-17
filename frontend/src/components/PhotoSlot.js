import { Camera, Check } from "lucide-react";

function resize(file, max = 1024) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const k = Math.min(1, max / Math.max(img.width, img.height));
        const c = document.createElement("canvas");
        c.width = img.width * k;
        c.height = img.height * k;
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        resolve(c.toDataURL("image/jpeg", 0.72));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

export default function PhotoSlot({ label, value, onChange, testid }) {
  const pick = async (e) => {
    const f = e.target.files?.[0];
    if (f) onChange(await resize(f));
  };
  return (
    <label data-testid={testid} className="group relative flex aspect-[4/3] cursor-pointer flex-col items-center justify-center overflow-hidden rounded-md border-2 border-dashed bg-muted/40 transition-colors hover:border-primary">
      {value ? (
        <>
          <img src={value} alt={label} className="absolute inset-0 h-full w-full object-cover" />
          <span className="absolute right-2 top-2 rounded-full bg-emerald-500 p-1 text-white"><Check className="h-3 w-3" /></span>
        </>
      ) : (
        <Camera className="h-7 w-7 text-muted-foreground group-hover:text-primary" />
      )}
      <span className="absolute bottom-0 left-0 right-0 bg-slate-950/75 px-2 py-1 text-center text-xs font-semibold uppercase tracking-wider text-white">{label}</span>
      <input data-testid={`${testid}-input`} type="file" accept="image/*" capture="environment" className="hidden" onChange={pick} />
    </label>
  );
}
