import type { Action } from "./domain";
import { actionNames } from "./constants";

export const duration = (ms: number | undefined) =>
  (ms ?? 0) >= 1000
    ? `${((ms ?? 0) / 1000).toFixed(1)} s`
    : `${Number(ms || 0).toFixed(1)} ms`;
export const number = (value: number | null | undefined) =>
  new Intl.NumberFormat().format(Number(value || 0));
export const dateTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "Saved record"
    : new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
};
export const actionLabel = (actions?: Action[] | null) =>
  actions?.length
    ? actions
        .map((action) => actionNames[action] || action.replaceAll("_", " "))
        .join(" + ")
    : "No changes · control";
