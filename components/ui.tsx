import { ArrowRight, ArrowUpRight, ArrowDownRight, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

export function cx(...parts: Array<string | false | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("rounded-[18px] border border-line bg-white shadow-[var(--shadow-card)]", className)}>
      {children}
    </div>
  );
}

export function CardTitle({
  icon: Icon,
  title,
  tint = "bg-brand-50 text-brand-500",
  right,
}: {
  icon: LucideIcon;
  title: string;
  tint?: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2.5">
        <span className={cx("flex h-8 w-8 items-center justify-center rounded-[10px]", tint)}>
          <Icon size={16} strokeWidth={2.2} />
        </span>
        <h2 className="text-[15px] font-semibold text-ink-900">{title}</h2>
      </div>
      {right}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-7 flex items-end justify-between animate-rise">
      <div>
        <h1 className="text-[28px] font-bold tracking-[-0.02em] text-ink-900">{title}</h1>
        <p className="mt-1 text-[14px] text-ink-500">{subtitle}</p>
      </div>
      {actions}
    </div>
  );
}

export function PrimaryButton({
  children,
  className,
  type = "button",
  onClick,
  disabled,
}: {
  children: ReactNode;
  className?: string;
  type?: "button" | "submit" | "reset";
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "inline-flex items-center gap-2 rounded-[10px] bg-brand-500 px-4 py-2.5 text-[13.5px] font-semibold text-white",
        "shadow-[0_4px_14px_-4px_rgba(91,92,235,0.5)] transition hover:bg-brand-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
    >
      {children}
    </button>
  );
}

export function GhostButton({
  children,
  className,
  type = "button",
  onClick,
  disabled,
}: {
  children: ReactNode;
  className?: string;
  type?: "button" | "submit" | "reset";
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "inline-flex items-center gap-2 rounded-[10px] border border-line bg-white px-4 py-2.5 text-[13.5px] font-semibold text-ink-700",
        "transition hover:border-brand-200 hover:text-brand-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
    >
      {children}
    </button>
  );
}

export function CardLink({ href = "#", children }: { href?: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="group inline-flex items-center gap-1.5 text-[13px] font-semibold text-brand-500 hover:text-brand-600"
    >
      {children}
      <ArrowRight size={14} strokeWidth={2.4} className="transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}

export function Delta({ value, up = true }: { value: string; up?: boolean }) {
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-0.5 text-[12.5px] font-semibold",
        up ? "text-emerald-500" : "text-rose-500"
      )}
    >
      <Icon size={13} strokeWidth={2.6} />
      {value}
    </span>
  );
}

export function Badge({
  children,
  tone = "brand",
}: {
  children: ReactNode;
  tone?: "brand" | "green" | "amber" | "red" | "gray" | "blue";
}) {
  const tones = {
    brand: "bg-brand-50 text-brand-600 border-brand-100",
    green: "bg-emerald-50 text-emerald-600 border-emerald-100",
    amber: "bg-amber-50 text-amber-600 border-amber-100",
    red: "bg-rose-50 text-rose-600 border-rose-100",
    gray: "bg-slate-50 text-slate-500 border-slate-100",
    blue: "bg-sky-50 text-sky-600 border-sky-100",
  } as const;
  return (
    <span className={cx("inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11.5px] font-semibold", tones[tone])}>
      {children}
    </span>
  );
}

export function Toggle({
  on = true,
  label,
  onChange,
  disabled,
}: {
  on?: boolean;
  label?: string;
  onChange?: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      {...(onChange ? { onClick: () => onChange(!on) } : {})}
      className={cx(
        "relative h-6 w-11 shrink-0 rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-not-allowed disabled:opacity-60",
        on ? "bg-brand-500" : "bg-ink-300/50"
      )}
    >
      <span
        className={cx(
          "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all",
          on ? "left-[22px]" : "left-0.5"
        )}
      />
    </button>
  );
}

export function ProgressBar({ value, color = "bg-emerald-500", track = "bg-line" }: { value: number; color?: string; track?: string }) {
  return (
    <div className={cx("h-2 w-full overflow-hidden rounded-full", track)}>
      <div className={cx("h-full rounded-full", color)} style={{ width: `${value}%` }} />
    </div>
  );
}

/* ---------- charts (inline SVG, decorative) ---------- */

export function Sparkline({
  points,
  stroke = "#5b5ceb",
  id,
  height = 56,
}: {
  points: number[];
  stroke?: string;
  id: string;
  height?: number;
}) {
  const w = 220;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const norm = (v: number) => height - 6 - ((v - min) / (max - min || 1)) * (height - 14);
  const step = w / (points.length - 1);
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${norm(p).toFixed(1)}`).join(" ");
  const area = `${d} L${w},${height} L0,${height} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${height}`} className="h-14 w-full" preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id={`sp-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#sp-${id})`} />
      <path d={d} fill="none" stroke={stroke} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function Donut({
  data,
  size = 132,
  thickness = 30,
}: {
  data: Array<{ value: number; color: string }>;
  size?: number;
  thickness?: number;
}) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const segments = data.reduce<{
    offset: number;
    items: Array<{ value: number; color: string; offset: number; index: number }>;
  }>(
    (acc, item, index) => {
      const frac = item.value / total;
      return {
        offset: acc.offset + frac,
        items: [...acc.items, { ...item, offset: acc.offset, index }],
      };
    },
    { offset: 0, items: [] }
  ).items;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
      {segments.map((d) => {
        const frac = d.value / total;
        return (
          <circle
            key={d.index}
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={d.color}
            strokeWidth={thickness}
            strokeDasharray={`${frac * c - 2} ${c - frac * c + 2}`}
            strokeDashoffset={-d.offset * c + c / 4}
          />
        );
      })}
    </svg>
  );
}

export function Bars({
  values,
  color = "#5b5ceb",
  height = 120,
}: {
  values: number[];
  color?: string;
  height?: number;
}) {
  const max = Math.max(...values);
  return (
    <div className="flex items-end gap-2" style={{ height }}>
      {values.map((v, i) => (
        <div
          key={i}
          className="flex-1 rounded-t-[5px]"
          style={{ height: `${(v / max) * 100}%`, background: i === values.length - 2 ? color : `${color}30` }}
        />
      ))}
    </div>
  );
}
