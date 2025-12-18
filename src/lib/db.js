import { Pool } from 'pg';


// Create a new PostgreSQL connection pool using environment variables 
// For demonstration purposes, we only got placeholders here
// Make sure to set the appropriate environment variables in your deployment environment
const pool = new Pool({
  user: process.env.DB_USER,
  host: process.env.DB_HOST,
  database: process.env.DB_NAME,
  password: process.env.DB_PASSWORD,
  port: process.env.DB_PORT || 5432,
  ssl: process.env.DB_SSL === 'true' ? {
    rejectUnauthorized: process.env.DB_REJECT_UNAUTHORIZED !== 'false',
  } : false,
});

export default pool;

