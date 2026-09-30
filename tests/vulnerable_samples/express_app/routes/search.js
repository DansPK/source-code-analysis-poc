const express = require("express");
const { searchUsers } = require("../services/searchService");

const router = express.Router();

router.get("/", async (req, res) => {
  const users = await searchUsers(req.query.q);
  res.json(users);
});

module.exports = router;
