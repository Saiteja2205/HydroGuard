package com.aistudio.hydroguard.wxqpzx;

import android.app.Application;

import com.aistudio.hydroguard.wxqpzx.data.api.LanApiRoute;
import com.aistudio.hydroguard.wxqpzx.data.api.RetrofitClient;

public class HydroGuardApplication extends Application {
    @Override public void onCreate() {
        super.onCreate();
        RetrofitClient.attach(this);
        LanApiRoute.register(this);
    }
}
