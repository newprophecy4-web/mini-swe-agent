import React from 'react';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
  id?: string;
  compact?: boolean;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  id,
  compact = false,
}) => {
  return (
    <div
      id={id}
      className={`flex flex-col items-center justify-center text-center select-none ${
        compact ? 'py-8 px-4' : 'py-16 px-6'
      }`}
    >
      {icon && (
        <div className="w-12 h-12 rounded-xl bg-zinc-800/80 border border-zinc-700/60 flex items-center justify-center text-zinc-400 mb-3 shadow-inner">
          {icon}
        </div>
      )}
      <h4 className="text-sm font-semibold text-zinc-200 mb-1">{title}</h4>
      <p className="text-xs text-zinc-400 max-w-sm leading-relaxed mb-4">{description}</p>
      {action && <div>{action}</div>}
    </div>
  );
};
