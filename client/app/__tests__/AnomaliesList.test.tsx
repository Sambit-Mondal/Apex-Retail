import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import AnomaliesList from '../components/AnomaliesList';

jest.mock('lucide-react', () => ({
  AlertTriangle: () => <div data-testid="alert-triangle">AlertTriangle</div>,
  AlertCircle: () => <div data-testid="alert-circle">AlertCircle</div>,
  Info: () => <div data-testid="info">Info</div>,
}));

describe('AnomaliesList Component', () => {
  const mockAnomalies = [
    {
      id: '1',
      type: 'High Queue Depth',
      severity: 'high' as const,
      message: 'Queue depth exceeded 15 people',
      timestamp: new Date(Date.now() - 5 * 60000).toISOString(),
    },
    {
      id: '2',
      type: 'Unusual Dwell Time',
      severity: 'medium' as const,
      message: 'Average dwell time increased by 40%',
      timestamp: new Date(Date.now() - 30 * 60000).toISOString(),
    },
  ];

  test('renders empty state when no anomalies', () => {
    render(<AnomaliesList anomalies={[]} />);
    expect(screen.getByText('No anomalies detected')).toBeInTheDocument();
    expect(screen.getByText('All systems operating normally')).toBeInTheDocument();
  });

  test('renders anomalies list', () => {
    render(<AnomaliesList anomalies={mockAnomalies} />);
    expect(screen.getByText('High Queue Depth')).toBeInTheDocument();
    expect(screen.getByText('Unusual Dwell Time')).toBeInTheDocument();
  });

  test('renders anomaly messages', () => {
    render(<AnomaliesList anomalies={mockAnomalies} />);
    expect(screen.getByText('Queue depth exceeded 15 people')).toBeInTheDocument();
    expect(screen.getByText('Average dwell time increased by 40%')).toBeInTheDocument();
  });

  test('renders correct severity icons', () => {
    render(<AnomaliesList anomalies={mockAnomalies} />);
    expect(screen.getByTestId('alert-triangle')).toBeInTheDocument();
    expect(screen.getByTestId('alert-circle')).toBeInTheDocument();
  });

  test('displays anomaly count', () => {
    render(<AnomaliesList anomalies={mockAnomalies} />);
    expect(screen.getByText('2 anomalies detected')).toBeInTheDocument();
  });

  test('displays singular anomaly count correctly', () => {
    const singleAnomaly = [mockAnomalies[0]];
    render(<AnomaliesList anomalies={singleAnomaly} />);
    expect(screen.getByText('1 anomaly detected')).toBeInTheDocument();
  });

  test('renders loading skeleton when loading prop is true', () => {
    const { container } = render(
      <AnomaliesList anomalies={[]} loading={true} />
    );
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  test('renders header text', () => {
    render(<AnomaliesList anomalies={[]} />);
    expect(screen.getByText('Active Anomalies')).toBeInTheDocument();
  });

  test('applies correct severity styling to high severity', () => {
    const { container } = render(<AnomaliesList anomalies={mockAnomalies} />);
    const highSeverityItem = container.querySelector('.bg-red-900\\/30');
    expect(highSeverityItem).toBeInTheDocument();
  });

  test('displays relative time formatting', () => {
    render(<AnomaliesList anomalies={mockAnomalies} />);
    const timeElements = screen.getAllByText(/m ago/);
    expect(timeElements.length).toBeGreaterThan(0);
  });

  test('formats "just now" for very recent anomalies', () => {
    const recentAnomaly = {
      ...mockAnomalies[0],
      timestamp: new Date().toISOString(),
    };
    render(<AnomaliesList anomalies={[recentAnomaly]} />);
    expect(screen.getByText('Just now')).toBeInTheDocument();
  });
});
