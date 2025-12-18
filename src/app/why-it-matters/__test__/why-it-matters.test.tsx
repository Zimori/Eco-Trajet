import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import WhyItMattersPage from '../page';

describe('WhyItMattersPage', () => {
  test('renders the page with all sections and content', () => {
    render(<WhyItMattersPage />);

    // Check for the main title
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Why It Matters');

    // Check for the "Climate Change and Transportation" section
    expect(screen.getByRole('heading', { level: 2, name: 'Climate Change and Transportation' })).toBeInTheDocument();
    expect(screen.getAllByText(/carbon footprint/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('24%')).toBeInTheDocument();
    expect(screen.getByText('of global CO₂ emissions come from transportation')).toBeInTheDocument();

    // Check for the "Our Mission" section
    expect(screen.getByRole('heading', { level: 2, name: 'Our Mission' })).toBeInTheDocument();
    expect(screen.getByText(/help you understand the impact of your travel choices/i)).toBeInTheDocument();
    expect(screen.getByText(/eco-friendly decisions/i)).toBeInTheDocument();

    expect(screen.getByRole('heading', { level: 2, name: 'They Talk About It' })).toBeInTheDocument();
    expect(screen.getByText('Mobilité et climat : vous avez dit urgence ?')).toBeInTheDocument();
    expect(screen.getByText('Cerema')).toBeInTheDocument();
  });
});