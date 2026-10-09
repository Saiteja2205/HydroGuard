package com.aistudio.hydroguard.wxqpzx.data.repository;

import com.aistudio.hydroguard.wxqpzx.data.database.User;

public interface AuthCallback {
    void onSuccess(User user);
    void onFailure(String message);
}
