package com.aistudio.hydroguard.wxqpzx.ui.viewmodel;

import android.app.Application;

import androidx.annotation.NonNull;
import androidx.lifecycle.AndroidViewModel;
import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.aistudio.hydroguard.wxqpzx.data.api.ApiRepository;
import com.aistudio.hydroguard.wxqpzx.data.database.AppDatabase;
import com.aistudio.hydroguard.wxqpzx.data.database.User;
import com.aistudio.hydroguard.wxqpzx.data.repository.AuthCallback;
import com.aistudio.hydroguard.wxqpzx.data.repository.FirebaseAuthRepository;
import com.aistudio.hydroguard.wxqpzx.data.repository.HydroRepository;

public class HydroViewModel extends AndroidViewModel {
    private final ApiRepository apiRepository;
    private final FirebaseAuthRepository authRepository;
    private final HydroRepository hydroRepository;
    private final MutableLiveData<User> currentUser = new MutableLiveData<>();
    private final MutableLiveData<String> loginError = new MutableLiveData<>();

    public HydroViewModel(@NonNull Application application) {
        super(application);
        apiRepository = new ApiRepository();
        AppDatabase database = AppDatabase.getDatabase(application);
        authRepository = new FirebaseAuthRepository(application, database, apiRepository);
        hydroRepository = new HydroRepository(database.hydroDao(), apiRepository);
    }

    public LiveData<User> currentUser() { return currentUser; }
    public LiveData<String> loginError() { return loginError; }
    public boolean isFirebaseAvailable() { return authRepository.isFirebaseAvailable(); }
    public ApiRepository api() { return apiRepository; }
    public HydroRepository hydro() { return hydroRepository; }

    public void restoreSession(AuthCallback callback) {
        authRepository.restoreSession(new AuthCallback() {
            @Override public void onSuccess(User user) {
                currentUser.postValue(user);
                loginError.postValue(null);
                callback.onSuccess(user);
            }
            @Override public void onFailure(String message) {
                currentUser.postValue(null);
                callback.onFailure(message);
            }
        });
    }

    public void signInWithGoogleIdToken(String idToken, AuthCallback callback) {
        loginError.setValue(null);
        authRepository.signInWithGoogleIdToken(idToken, resultCallback(callback));
    }

    public void developmentLogin(String role, AuthCallback callback) {
        loginError.setValue(null);
        authRepository.loginAsDevelopment(role, resultCallback(callback));
    }

    public void logout() {
        authRepository.signOut();
        currentUser.setValue(null);
        loginError.setValue(null);
    }

    private AuthCallback resultCallback(AuthCallback target) {
        return new AuthCallback() {
            @Override public void onSuccess(User user) {
                currentUser.postValue(user);
                loginError.postValue(null);
                target.onSuccess(user);
            }
            @Override public void onFailure(String message) {
                loginError.postValue(message);
                target.onFailure(message);
            }
        };
    }
}
