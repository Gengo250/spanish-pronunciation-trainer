import type { ReactNode } from "react";

type Props = { title: string; body: string; action?: ReactNode };

export function EmptyState({ title, body, action }: Props) {
  return (
    <div className="empty">
      <p className="empty__title">{title}</p>
      <p className="empty__body">{body}</p>
      {action}
    </div>
  );
}
