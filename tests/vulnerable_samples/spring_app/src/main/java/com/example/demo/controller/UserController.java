package com.example.demo.controller;

import com.example.demo.service.UserService;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/users/search")
    public List<Map<String, Object>> search(@RequestParam String name) {
        return userService.searchUsers(name);
    }
}
