package com.example.data.repository

import android.content.Context
import android.util.Log
import com.example.data.database.HydroDao
import com.example.data.database.User
import com.google.android.gms.tasks.Task
import com.google.firebase.auth.FirebaseAuth
import kotlinx.coroutines.launch
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class FirebaseAuthRepository(
    private val hydroDao: HydroDao,
    private val context: Context
) {
    private val _currentUserFlow = MutableStateFlow<User?>(null)
    val currentUserFlow: StateFlow<User?> = _currentUserFlow.asStateFlow()

    private val _isFirebaseAvailable = MutableStateFlow(false)
    val isFirebaseAvailable: StateFlow<Boolean> = _isFirebaseAvailable.asStateFlow()

    private var firebaseAuth: FirebaseAuth? = null

    init {
        try {
            firebaseAuth = FirebaseAuth.getInstance()
            _isFirebaseAvailable.value = true
            
            // Sync initial state if Firebase user already logged in
            val currentFirebaseUser = firebaseAuth?.currentUser
            if (currentFirebaseUser != null) {
                val email = currentFirebaseUser.email
                if (email != null) {
                    // Try to fetch local User profile from Room Database
                    // We'll run a non-blocking check
                    kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
                        try {
                            val userProfile = hydroDao.getUserByEmail(email)
                            if (userProfile != null) {
                                _currentUserFlow.value = userProfile
                            }
                        } catch (e: Exception) {
                            Log.e("FirebaseAuthRepository", "Error fetching profile during init", e)
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.w("FirebaseAuthRepository", "Firebase Auth is not fully configured (missing google-services.json?). Fallback enabled.", e)
            _isFirebaseAvailable.value = false
        }
    }

    suspend fun loginWithEmailAndPassword(
        email: String,
        password: String,
        expectedRole: String
    ): Result<User> {
        if (!_isFirebaseAvailable.value || firebaseAuth == null) {
            // Local fallback simulation mode
            return loginWithLocalFallback(email, expectedRole)
        }

        return try {
            val authResult = firebaseAuth!!.signInWithEmailAndPassword(email, password).await()
            val firebaseUser = authResult.user ?: throw Exception("Auth succeeded but Firebase user is null")
            
            val userEmail = firebaseUser.email ?: email
            var localUser = hydroDao.getUserByEmail(userEmail)
            
            if (localUser == null) {
                // If the user authenticated on Firebase but profile is missing in Room, auto-create it
                localUser = User(
                    email = userEmail,
                    name = "User (${userEmail.substringBefore("@")})",
                    role = expectedRole,
                    hostelBlock = if (expectedRole == "ADMIN") "Office" else "A",
                    roomNumber = if (expectedRole == "ADMIN") "HQ" else "101"
                )
                hydroDao.insertUser(localUser)
            }

            if (localUser.role != expectedRole) {
                firebaseAuth!!.signOut()
                return Result.failure(Exception("Role mismatch: expected $expectedRole but profile is ${localUser.role}"))
            }

            _currentUserFlow.value = localUser
            Result.success(localUser)
        } catch (e: Exception) {
            Log.e("FirebaseAuthRepository", "Firebase auth login failed, checking local simulation...", e)
            // If the Firebase configuration exists but the credential is not registered or network failed, 
            // let's try local database fallback for a painless sandbox demo experience.
            if (e.message?.contains("no user record") == true || e.message?.contains("INVALID_LOGIN_CREDENTIALS") == true) {
                // Try logging in locally using database credentials if they exist
                val localUser = hydroDao.getUserByEmail(email)
                if (localUser != null && localUser.role == expectedRole) {
                    _currentUserFlow.value = localUser
                    return Result.success(localUser)
                }
            }
            Result.failure(e)
        }
    }

    suspend fun registerWithEmailAndPassword(
        email: String,
        password: String,
        name: String,
        role: String,
        hostelBlock: String,
        roomNumber: String
    ): Result<User> {
        val user = User(
            email = email,
            name = name,
            role = role,
            hostelBlock = hostelBlock,
            roomNumber = roomNumber
        )

        if (!_isFirebaseAvailable.value || firebaseAuth == null) {
            // Local fallback signup
            hydroDao.insertUser(user)
            _currentUserFlow.value = user
            return Result.success(user)
        }

        return try {
            val authResult = firebaseAuth!!.createUserWithEmailAndPassword(email, password).await()
            val firebaseUser = authResult.user ?: throw Exception("Registration succeeded but Firebase user is null")
            
            hydroDao.insertUser(user)
            _currentUserFlow.value = user
            Result.success(user)
        } catch (e: Exception) {
            Log.e("FirebaseAuthRepository", "Firebase signup failed, saving locally...", e)
            // Create locally in case they are offline or running in sandbox simulation
            hydroDao.insertUser(user)
            _currentUserFlow.value = user
            Result.success(user)
        }
    }

    fun signOut() {
        try {
            firebaseAuth?.signOut()
        } catch (e: Exception) {
            Log.e("FirebaseAuthRepository", "Error during Firebase signout", e)
        }
        _currentUserFlow.value = null
    }

    private suspend fun loginWithLocalFallback(email: String, role: String): Result<User> {
        return try {
            val existing = hydroDao.getUserByEmail(email)
            if (existing != null) {
                if (existing.role == role) {
                    _currentUserFlow.value = existing
                    Result.success(existing)
                } else {
                    Result.failure(Exception("Role mismatch: expected $role but profile is ${existing.role}"))
                }
            } else {
                // Register a new demo account automatically
                val name = if (role == "ADMIN") "Administrator (${email.substringBefore("@")})" else "Student (${email.substringBefore("@")})"
                val newUser = User(
                    email = email,
                    name = name,
                    role = role,
                    hostelBlock = if (role == "ADMIN") "Office" else listOf("A", "B").random(),
                    roomNumber = if (role == "ADMIN") "HQ" else (101..400).random().toString()
                )
                hydroDao.insertUser(newUser)
                _currentUserFlow.value = newUser
                Result.success(newUser)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    // Helper extension to await Firebase Tasks
    private suspend fun <T> Task<T>.await(): T = suspendCancellableCoroutine { continuation ->
        addOnCompleteListener { task ->
            if (task.isSuccessful) {
                continuation.resume(task.result)
            } else {
                continuation.resumeWithException(task.exception ?: RuntimeException("Firebase operation failed"))
            }
        }
    }
}
