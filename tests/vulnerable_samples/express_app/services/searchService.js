const { findUsersByName } = require("../db/userRepository");

async function searchUsers(term) {
  return findUsersByName(term.trim());
}

module.exports = { searchUsers };
