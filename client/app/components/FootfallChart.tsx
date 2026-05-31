'use client';

import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface FootfallChartProps {
  loading?: boolean;
}

// Generate dummy historical data
const generateHistoricalData = () => {
  const data = [];
  const now = new Date();
  for (let i = 23; i >= 0; i--) {
    const hour = new Date(now.getTime() - i * 60 * 60 * 1000);
    data.push({
      time: hour.getHours() + ':00',
      footfall: Math.floor(Math.random() * 150 + 50),
      averageDwell: Math.floor(Math.random() * 2000 + 1000),
    });
  }
  return data;
};

export default function FootfallChart({ loading = false }: FootfallChartProps) {
  const data = generateHistoricalData();

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-6 backdrop-blur">
      <h2 className="text-lg font-semibold mb-4 text-white">Historical Footfall (24h)</h2>

      {loading ? (
        <div className="h-80 bg-slate-700/20 rounded animate-pulse flex items-center justify-center">
          <span className="text-slate-400">Loading chart...</span>
        </div>
      ) : (
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#475569" />
              <XAxis dataKey="time" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                }}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Legend
                wrapperStyle={{ paddingTop: '20px' }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Line
                type="monotone"
                dataKey="footfall"
                stroke="#3b82f6"
                dot={false}
                strokeWidth={2}
                name="Footfall (visitors)"
              />
              <Line
                type="monotone"
                dataKey="averageDwell"
                stroke="#a855f7"
                dot={false}
                strokeWidth={2}
                name="Avg Dwell (ms)"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
