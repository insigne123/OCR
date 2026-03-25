export function formatDate(value: string | null) {
  if (!value) return "-";

  return new Intl.DateTimeFormat("es-CL", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

export function formatConfidence(value: number | null) {
  if (value === null || Number.isNaN(value)) {
    return "-";
  }

  return value.toFixed(2);
}
