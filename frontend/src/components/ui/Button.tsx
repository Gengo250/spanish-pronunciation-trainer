import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "default" | "quiet" | "danger";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "md" | "lg";
  block?: boolean;
  /** Keyboard shortcut shown on the button, so the hint lives where it is used. */
  shortcut?: string;
  children: ReactNode;
};

export function Button({
  variant = "default",
  size = "md",
  block,
  shortcut,
  children,
  className = "",
  ...rest
}: Props) {
  const classes = [
    "btn",
    variant !== "default" ? `btn--${variant}` : "",
    size === "lg" ? "btn--lg" : "",
    block ? "btn--block" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={classes} {...rest}>
      {children}
      {shortcut && (
        <kbd className="btn__key" aria-hidden="true">
          {shortcut}
        </kbd>
      )}
    </button>
  );
}
