import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import FootfallChart from '../components/FootfallChart';

jest.mock('recharts', () => ({
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line">Line</div>,
  XAxis: () => <div data-testid="xaxis">XAxis</div>,
  YAxis: () => <div data-testid="yaxis">YAxis</div>,
  CartesianGrid: () => <div data-testid="grid">CartesianGrid</div>,
  Tooltip: () => <div data-testid="tooltip">Tooltip</div>,
  Legend: () => <div data-testid="legend">Legend</div>,
  ResponsiveContainer: ({ children }: any) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

describe('FootfallChart Component', () => {
  test('renders chart container', () => {
    render(<FootfallChart />);
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
  });

  test('renders LineChart component', () => {
    render(<FootfallChart />);
    expect(screen.getByTestId('line-chart')).toBeInTheDocument();
  });

  test('renders chart axes', () => {
    render(<FootfallChart />);
    expect(screen.getByTestId('xaxis')).toBeInTheDocument();
    expect(screen.getByTestId('yaxis')).toBeInTheDocument();
  });

  test('renders grid and legend', () => {
    render(<FootfallChart />);
    expect(screen.getByTestId('grid')).toBeInTheDocument();
    expect(screen.getByTestId('legend')).toBeInTheDocument();
  });

  test('renders title', () => {
    render(<FootfallChart />);
    expect(screen.getByText('Historical Footfall (24h)')).toBeInTheDocument();
  });

  test('renders with dark theme styling', () => {
    const { container } = render(<FootfallChart />);
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('bg-slate-800');
    expect(wrapper.className).toContain('border-slate-700');
  });

  test('renders two Line components for footfall and dwell time', () => {
    const { container } = render(<FootfallChart />);
    const lines = container.querySelectorAll('[data-testid="line"]');
    expect(lines.length).toBe(2);
  });
});
