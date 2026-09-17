import React from 'react';

export type BadgeVariant = 'pill' | 'text-only';
export type BadgeIntent = 'success' | 'warning' | 'error' | 'neutral' | 'info';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  intent?: BadgeIntent;
  children: React.ReactNode;
}

const PILL_STYLES: Record<BadgeIntent, string> = {
  success: 'bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full px-2 py-0.5',
  warning: 'bg-amber-50 text-amber-700 border border-amber-200 rounded-full px-2 py-0.5',
  error: 'bg-rose-50 text-rose-700 border border-rose-200 rounded-full px-2 py-0.5',
  neutral: 'bg-slate-100 text-slate-600 border border-slate-200 rounded-full px-2 py-0.5',
  info: 'bg-indigo-50 text-[#5e4cff] border border-indigo-200 rounded-full px-2 py-0.5',
};

const TEXT_ONLY_STYLES: Record<BadgeIntent, string> = {
  success: 'text-emerald-600 font-semibold',
  warning: 'text-amber-600 font-semibold',
  error: 'text-rose-600 font-semibold',
  neutral: 'text-slate-400 font-medium',
  info: 'text-[#5e4cff] font-semibold',
};

export const Badge: React.FC<BadgeProps> = ({
  variant = 'pill',
  intent = 'neutral',
  className = '',
  children,
  ...props
}) => {
  const baseClass = variant === 'text-only' ? TEXT_ONLY_STYLES[intent] : PILL_STYLES[intent];
  return (
    <span
      className={`text-[11px] inline-flex items-center ${baseClass} ${className}`}
      {...props}
    >
      {children}
    </span>
  );
};
