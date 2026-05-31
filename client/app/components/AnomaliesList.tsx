'use client';

import React from 'react';
import { AlertTriangle, AlertCircle, Info } from 'lucide-react';

interface Anomaly {
  id: string;
  type: string;
  severity: 'high' | 'medium' | 'low';
  message: string;
  timestamp: string;
}

interface AnomaliesListProps {
  anomalies: Anomaly[];
  loading?: boolean;
}

const getSeverityColor = (severity: string) => {
  switch (severity) {
    case 'high':
      return 'bg-red-900/30 border-red-700/50 text-red-200';
    case 'medium':
      return 'bg-yellow-900/30 border-yellow-700/50 text-yellow-200';
    case 'low':
      return 'bg-blue-900/30 border-blue-700/50 text-blue-200';
    default:
      return 'bg-slate-900/30 border-slate-700/50 text-slate-200';
  }
};

const getSeverityIcon = (severity: string) => {
  switch (severity) {
    case 'high':
      return <AlertTriangle className="w-4 h-4 flex-shrink-0" />;
    case 'medium':
      return <AlertCircle className="w-4 h-4 flex-shrink-0" />;
    case 'low':
      return <Info className="w-4 h-4 flex-shrink-0" />;
    default:
      return <Info className="w-4 h-4 flex-shrink-0" />;
  }
};

export default function AnomaliesList({ anomalies, loading = false }: AnomaliesListProps) {
  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-6 backdrop-blur h-full">
      <h2 className="text-lg font-semibold mb-4 text-white">Active Anomalies</h2>

      <div className="space-y-3 max-h-96 overflow-y-auto">
        {loading ? (
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <div key={i} className="h-20 bg-slate-700/30 rounded animate-pulse" />
            ))}
          </div>
        ) : anomalies.length === 0 ? (
          <div className="text-center py-8 text-slate-400">
            <p className="text-sm">No anomalies detected</p>
            <p className="text-xs mt-1">All systems operating normally</p>
          </div>
        ) : (
          anomalies.map((anomaly) => (
            <div
              key={anomaly.id}
              className={`border rounded-lg p-3 transition-all hover:border-opacity-100 ${getSeverityColor(
                anomaly.severity
              )}`}
            >
              <div className="flex gap-3">
                {getSeverityIcon(anomaly.severity)}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm leading-tight">{anomaly.type}</p>
                  <p className="text-xs mt-1 opacity-80 line-clamp-2">{anomaly.message}</p>
                  <p className="text-xs mt-2 opacity-60">{formatTime(anomaly.timestamp)}</p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {anomalies.length > 0 && (
        <div className="mt-4 pt-4 border-t border-slate-700 text-xs text-slate-400">
          <p>{anomalies.length} anomal{anomalies.length === 1 ? 'y' : 'ies'} detected</p>
        </div>
      )}
    </div>
  );
}
