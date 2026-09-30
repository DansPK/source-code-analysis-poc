package com.example.demo.repository;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class UserRepository {
    private final JdbcTemplate jdbcTemplate;

    public UserRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<Map<String, Object>> findByName(String name) {
        // VULNERABLE: the request parameter is concatenated into the SQL text.
        String sql = "SELECT id, name, email FROM users WHERE name LIKE '%" + name + "%'";
        return jdbcTemplate.queryForList(sql);
    }
}
