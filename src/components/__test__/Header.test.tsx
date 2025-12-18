import { render, screen } from '@testing-library/react';
import Header from '../Header';
import '@testing-library/jest-dom';
import React from 'react';

jest.mock('next/image', () => ({
  __esModule: true,
  // Utilise une fonction qui retourne un élément JSX natif sans utiliser <img /> directement
  default: (props: Record<string, unknown>) => {
    return React.createElement('img', { ...props });
  },
}));

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>, // Mock Link
}));

describe('Header', () => {
  test('renders navigation links', () => {
    render(<Header />);

    expect(screen.getByText(/Try our calculations/i)).toBeInTheDocument();
    expect(screen.getByText(/Why It Matters/i)).toBeInTheDocument();
    expect(screen.getByText(/About Us/i)).toBeInTheDocument();
    expect(screen.getByText(/Sign In/i)).toBeInTheDocument();
  });
});
