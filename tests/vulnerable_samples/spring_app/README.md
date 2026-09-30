# spring_app — intentionally vulnerable

Ground truth for the Java code map and `java-sqli-concat`. **Do not deploy.**

`GET /users/search?name=...` → `UserController.search` → `UserService.searchUsers` →
`UserRepository.findByName`, which concatenates `name` into SQL (line 18) and runs it (line 19): SQL injection.
