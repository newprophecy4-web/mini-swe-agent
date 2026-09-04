import React from 'react';

interface LoadingSkeletonProps {
  lines?: number;
  className?: string;
  id?: string;
}

export const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({
  lines = 3,
  className = '',
  id,
}) => {
  return (
    <div id={id} className={`space-y-2.5 animate-pulse ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-3.5 bg-zinc-800/80 rounded-sm"
          style={{ width: `${Math.max(45, 95 - (i * 18) % 40)}%` }}
        />
      ))}
    </div>
  );
};
