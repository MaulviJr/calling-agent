import { formatLabel } from "@/lib/formatting";

export default function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${status}`}>{formatLabel(status)}</span>;
}
