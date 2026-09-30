# express_app — intentionally vulnerable

Ground truth for the JavaScript code map and `javascript-sqli-concat`. **Do not deploy.**

`GET /search?q=...` → the handler in `routes/search.js` → `searchUsers` in
`services/searchService.js` → `findUsersByName` in `db/userRepository.js`, which builds the
SQL with a template string: SQL injection.
