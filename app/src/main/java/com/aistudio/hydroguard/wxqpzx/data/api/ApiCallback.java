package com.aistudio.hydroguard.wxqpzx.data.api;

public interface ApiCallback {
    void onSuccess(String json);
    void onFailure(ApiFailure failure);
}
