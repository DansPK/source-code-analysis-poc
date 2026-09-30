package com.example.demo.service;

import com.example.demo.repository.UserRepository;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public List<Map<String, Object>> searchUsers(String name) {
        return userRepository.findByName(name.trim());
    }
}
