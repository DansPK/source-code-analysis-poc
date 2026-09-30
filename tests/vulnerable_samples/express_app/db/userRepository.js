const mysql = require("mysql2/promise");

const pool = mysql.createPool({ host: "localhost", user: "app", database: "app" });

async function findUsersByName(name) {
  // VULNERABLE: the query string is interpolated into the SQL text.
  const sql = `SELECT id, name, email FROM users WHERE name LIKE '%${name}%'`;
  const [rows] = await pool.query(sql);
  return rows;
}

module.exports = { findUsersByName };
