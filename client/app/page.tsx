'use client';

import React from 'react';
import useSWR from 'swr';
import { Users, Clock, ShoppingCart, AlertCircle, TrendingUp } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import MetricCard from './components/MetricCard';
import AnomaliesList from './components/AnomaliesList';
import FootfallChart from './components/FootfallChart';

// API fetcher
const fetcher = async (url: string) => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error('Failed to fetch metrics');
  }
  return response.json();
};

interface Metrics {
  store_id: string;
  unique_visitors: number;
  avg_dwell_ms: number;
  queue_depth: number;
  query_timestamp: string;
}

interface Anomaly {
  id: string;
  type: string;
  severity: 'high' | 'medium' | 'low';
  message: string;
  timestamp: string;
}

// Generate dummy anomalies
const generateAnomalies = (): Anomaly[] => {
  return [
    {
      id: 'anom-001',
      type: 'High Queue Depth',
      severity: 'high',
      message: 'Queue depth exceeded 20 customers',
      timestamp: new Date(Date.now() - 5 * 60000).toISOString(),
    },
    {
      id: 'anom-002',
      type: 'Unusual Dwell Time',
      severity: 'medium',
      message: 'Average dwell time increased by 45%',
      timestamp: new Date(Date.now() - 15 * 60000).toISOString(),
    },
  ];
};

export default function Dashboard() {
  const storeId = 'STORE_TEST_001'; // Default store ID
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // SWR configuration for polling every 3000ms
  const { data: metrics, error, isLoading } = useSWR<Metrics>(
    `${apiUrl}/stores/${storeId}/metrics`,
    fetcher,
    {
      refreshInterval: 3000, // Poll every 3 seconds
      dedupingInterval: 2000,
      focusThrottleInterval: 300000, // 5 min when not focused
      revalidateOnFocus: true,
      revalidateOnReconnect: true,
    }
  );

  const anomalies = generateAnomalies();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white p-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">Apex Retail Analytics</h1>
        <p className="text-slate-400">Real-time store intelligence dashboard</p>
      </div>

      {/* Error State */}
      {error && (
        <div className="mb-6 p-4 bg-red-900/20 border border-red-500/50 rounded-lg flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <span className="text-red-200">Failed to load metrics. Please check your API connection.</span>
        </div>
      )}

      {/* Loading State */}
      {isLoading && !metrics && (
        <div className="mb-6 p-4 bg-blue-900/20 border border-blue-500/50 rounded-lg flex items-center gap-3">
          <div className="animate-spin rounded-full h-5 w-5 border border-blue-400 border-t-blue-600" />
          <span className="text-blue-200">Loading metrics...</span>
        </div>
      )}

      {/* Top Row: Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <MetricCard
          title="Total Visitors"
          value={metrics?.unique_visitors ?? 0}
          icon={<Users className="w-6 h-6" />}
          unit="today"
          color="from-blue-500 to-blue-600"
          loading={isLoading}
        />
        <MetricCard
          title="Avg Dwell Time"
          value={metrics?.avg_dwell_ms ?? 0}
          icon={<Clock className="w-6 h-6" />}
          unit="milliseconds"
          color="from-purple-500 to-purple-600"
          loading={isLoading}
          formatter={(val) => (val / 1000).toFixed(1) + 's'}
        />
        <MetricCard
          title="Queue Depth"
          value={metrics?.queue_depth ?? 0}
          icon={<ShoppingCart className="w-6 h-6" />}
          unit="customers"
          color="from-green-500 to-green-600"
          loading={isLoading}
        />
      </div>

      {/* Middle Row: Charts and Anomalies */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Footfall Chart */}
        <div className="lg:col-span-2">
          <FootfallChart loading={isLoading} />
        </div>

        {/* Anomalies List */}
        <div>
          <AnomaliesList anomalies={anomalies} loading={isLoading} />
        </div>
      </div>

      {/* Bottom Section: Last Updated */}
      {metrics && (
        <div className="text-center text-slate-500 text-sm">
          Last updated: {new Date(metrics.query_timestamp).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}