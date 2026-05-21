import { CheckCircle2, CircleAlert, CircleDot, Loader2 } from "lucide-react";

export function StatusBadge({
  status,
  label,
}: {
  status: "idle" | "running" | "ok" | "error";
  label: string;
}) {
  const Icon =
    status === "ok"
      ? CheckCircle2
      : status === "running"
        ? Loader2
        : status === "error"
          ? CircleAlert
          : CircleDot;
  const color =
    status === "ok"
      ? "text-emerald-400"
      : status === "running"
        ? "text-amber-300"
        : status === "error"
          ? "text-rose-400"
          : "text-slate-400";
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm ${color}`}>
      <Icon size={14} className={status === "running" ? "animate-spin" : ""} />
      {label}
    </span>
  );
}
