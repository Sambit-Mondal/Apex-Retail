import React from 'react';

interface MetricCardProps {
  title: string;
  value: number;
  icon: React.ReactNode;
  unit: string;
  color: string;
  loading?: boolean;
  formatter?: (val: number) => string;
}

export default function MetricCard({
  title,
  value,
  icon,
  unit,
  color,
  loading = false,
  formatter,
}: MetricCardProps) {
  const displayValue = formatter ? formatter(value) : value;

  return (
    <div
      className={`bg-gradient-to-br ${color} rounded-lg p-6 text-white shadow-lg overflow-hidden relative`}
    >
      {/* Background blur effect */}
      <div className="absolute inset-0 opacity-20 bg-white mix-blend-overlay" />

      {/* Content */}
      <div className="relative z-10">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-white/80">{title}</h3>
          <div className="w-10 h-10 bg-white/20 rounded-lg flex items-center justify-center">
            {icon}
          </div>
        </div>

        {/* Loading skeleton */}
        {loading ? (
          <div className="space-y-2">
            <div className="h-8 bg-white/20 rounded animate-pulse w-20" />
            <div className="h-4 bg-white/10 rounded animate-pulse w-16" />
          </div>
        ) : (
          <>
            <div className="text-3xl font-bold text-white mb-1">{displayValue}</div>
            <div className="text-xs text-white/70">{unit}</div>
          </>
        )}
      </div>
    </div>
  );
}
