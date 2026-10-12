import type { ReactNode } from "react";

type Props = { tone?: "info" | "error" | "quiet"; children: ReactNode; role?: string };

export function Notice({ tone = "info", children, role }: Props) {
  const className = ["notice", tone === "error" ? "notice--error" : "", tone === "quiet" ? "notice--quiet" : ""]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={className} role={role ?? (tone === "error" ? "alert" : undefined)}>
      {children}
    </div>
  );
}
