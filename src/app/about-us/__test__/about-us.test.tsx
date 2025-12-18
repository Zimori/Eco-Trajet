import { render, screen } from '@testing-library/react';
import AboutUsPage from '../page';
import '@testing-library/jest-dom';

describe('AboutUsPage', () => {
  test('renders the About Us page with all sections', () => {
    render(<AboutUsPage />);

    // Vérifie que le titre principal est rendu
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('About Us');

    // Vérifie que les sections sont rendues (adapter aux vrais titres)
    expect(screen.getByRole('heading', { level: 2, name: 'Project' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Our Team' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Our Professors' })).toBeInTheDocument();

    // Vérifie que les membres de l'équipe sont rendus
    const redactedElements = screen.getAllByText('[REDACTED]');
    expect(redactedElements.length).toBeGreaterThan(0);

    // Vérifie que les rôles sont toujours affichés
    expect(screen.getByText('Frontend and Backend Developer')).toBeInTheDocument();
    expect(screen.getByText('VM Specialist')).toBeInTheDocument();
    expect(screen.getByText('UI/UX Designer')).toBeInTheDocument();
    expect(screen.getByText('VM and Frontend Developer')).toBeInTheDocument();
    expect(screen.getByText('Backend Developer')).toBeInTheDocument();
    expect(screen.getByText('Database Specialist')).toBeInTheDocument();

    // Vérifie que les professeurs sont redactés
    expect(screen.getByText('Responsable de l\'UE, Orga, Support')).toBeInTheDocument();
    expect(screen.getByText('Support BD')).toBeInTheDocument();
    expect(screen.getByText('Support Prog Web')).toBeInTheDocument();
  });
});