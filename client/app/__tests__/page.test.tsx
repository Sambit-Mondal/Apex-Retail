import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import Dashboard from '../page';

// Mock SWR
jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn((url, fetcher, options) => {
    // Mock successful response
    return {
      data: {
        store_id: 'STORE_TEST_001',
        unique_visitors: 245,
        avg_dwell_ms: 3500,
        queue_depth: 12,
        query_timestamp: new Date().toISOString(),
      },
      error: null,
      isLoading: false,
    };
  }),
}));

// Mock Recharts
jest.mock('recharts', () => ({
  LineChart: () => <div data-testid="line-chart">LineChart</div>,
  Line: () => <div>Line</div>,
  XAxis: () => <div>XAxis</div>,
  YAxis: () => <div>YAxis</div>,
  CartesianGrid: () => <div>CartesianGrid</div>,
  Tooltip: () => <div>Tooltip</div>,
  Legend: () => <div>Legend</div>,
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}));

// Mock Lucide React icons
jest.mock('lucide-react', () => ({
  Users: () => <div data-testid="users-icon">Users</div>,
  Clock: () => <div data-testid="clock-icon">Clock</div>,
  ShoppingCart: () => <div data-testid="cart-icon">Cart</div>,
  AlertCircle: () => <div data-testid="alert-icon">Alert</div>,
  TrendingUp: () => <div data-testid="trending-icon">Trending</div>,
  AlertTriangle: () => <div>AlertTriangle</div>,
  Info: () => <div>Info</div>,
}));

describe('Dashboard Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders dashboard header', async () => {
    render(<Dashboard />);
    expect(screen.getByText('Apex Retail Analytics')).toBeInTheDocument();
  });

  test('renders three metric cards', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('Total Visitors')).toBeInTheDocument();
      expect(screen.getByText('Avg Dwell Time')).toBeInTheDocument();
      expect(screen.getByText('Queue Depth')).toBeInTheDocument();
    });
  });

  test('displays metric values correctly', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('245')).toBeInTheDocument();
      expect(screen.getByText('12')).toBeInTheDocument();
    });
  });

  test('renders metric card icons', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('users-icon')).toBeInTheDocument();
      expect(screen.getByTestId('clock-icon')).toBeInTheDocument();
      expect(screen.getByTestId('cart-icon')).toBeInTheDocument();
    });
  });

  test('renders footfall chart', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
    });
  });

  test('renders anomalies section', async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText('Active Anomalies')).toBeInTheDocument();
    });
  });
});
