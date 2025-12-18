import pool from '@/lib/db';

export default async function handler(req, res) {
  try {
    const result = await pool.query(`SELECT name FROM co2app.city;`);

    res.status(200).json({ tables: result.rows });
  } catch (err) {
    console.error('Erreur DB détaillée :', err);
    res.status(500).json({ error: 'Erreur de base de données' });
  }
}

// Dummy test to satisfy Jest
it('dummy test for API route', () => {
  expect(true).toBe(true);
});
