import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import MetricCard from '../components/MetricCard';
import { Users } from 'lucide-react';

jest.mock('lucide-react', () => ({
  Users: () => <div data-testid="metric-icon">Icon</div>,
  Clock: () => <div>Clock</div>,
  ShoppingCart: () => <div>Cart</div>,
}));

describe('MetricCard Component', () => {
  const mockIcon = <Users className="w-8 h-8" />;

  test('renders metric card with title and value', () => {
    render(
      <MetricCard
        title="Test Metric"
        value={100}
        icon={mockIcon}
        unit="count"
        color="from-slate-600 to-slate-400"
      />
    );
    expect(screen.getByText('Test Metric')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
  });

  test('renders loading skeleton when loading is true', () => {
    const { container } = render(
      <MetricCard
        title="Test Metric"
        value={0}
        icon={mockIcon}
        unit="count"
        color="from-slate-600 to-slate-400"
        loading={true}
      />
    );
    const skeleton = container.querySelector('.animate-pulse');
    expect(skeleton).toBeInTheDocument();
  });

  test('applies custom formatter function', () => {
    const formatter = (value: number) => `$${value.toFixed(2)}`;
    render(
      <MetricCard
        title="Revenue"
        value={1000}
        icon={mockIcon}
        unit="amount"
        color="from-green-600 to-green-400"
        formatter={formatter}
      />
    );
    expect(screen.getByText('$1000.00')).toBeInTheDocument();
  });

  test('renders with gradient background', () => {
    const { container } = render(
      <MetricCard
        title="Test Metric"
        value={100}
        icon={mockIcon}
        unit="count"
        color="from-blue-600 to-blue-400"
      />
    );
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('from-blue-600');
    expect(card.className).toContain('to-blue-400');
  });

  test('handles missing formatter gracefully', () => {
    render(
      <MetricCard
        title="Test Metric"
        value={42.5}
        icon={mockIcon}
        unit="count"
        color="from-slate-600 to-slate-400"
      />
    );
    expect(screen.getByText('42.5')).toBeInTheDocument();
  });

  test('renders unit correctly', () => {
    render(
      <MetricCard
        title="Test Metric"
        value={100}
        icon={mockIcon}
        unit="people"
        color="from-purple-600 to-purple-400"
      />
    );
    expect(screen.getByText('people')).toBeInTheDocument();
  });
});
