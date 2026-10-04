package com.example.data.repository

import android.content.Context
import android.util.Log
import com.example.BuildConfig
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
            return Result.failure(Exception("Authentication is unavailable. Configure Firebase before signing in."))
        }

        return try {
            val authResult = firebaseAuth!!.signInWithEmailAndPassword(email, password).await()
            val firebaseUser = authResult.user ?: throw Exception("Auth succeeded but Firebase user is null")
            val userEmail = firebaseUser.email ?: email
            val claims = firebaseUser.getIdToken(false).await().claims
            val claimedRole = (claims["role"] as? String)?.uppercase() ?: "STUDENT"
            if (claimedRole !in setOf("STUDENT", "ADMIN") || claimedRole != expectedRole.uppercase()) {
                firebaseAuth!!.signOut()
                return Result.failure(Exception("This account does not have the selected role."))
            }
            var localUser = hydroDao.getUserByEmail(userEmail)
            if (localUser == null) {
                localUser = User(
                    email = userEmail,
                    name = "User (${userEmail.substringBefore("@")})",
                    role = claimedRole,
                    hostelBlock = "",
                    roomNumber = ""
                )
                hydroDao.insertUser(localUser)
            } else if (localUser.role != claimedRole) {
                localUser = localUser.copy(role = claimedRole)
                hydroDao.insertUser(localUser)
            }

            _currentUserFlow.value = localUser
            Result.success(localUser)
        } catch (e: Exception) {
            Log.e("FirebaseAuthRepository", "Firebase auth login failed", e)
            Result.failure(e)
        }
    }

    /** Local-only identity for debug demos. The release variant compiles with this disabled. */
    suspend fun loginAsDevelopment(role: String): Result<User> {
        if (!DevelopmentAuthPolicy.allows(BuildConfig.DEBUG, BuildConfig.ALLOW_DEVELOPMENT_LOGIN)) {
            return Result.failure(SecurityException("Development Login is disabled in this build."))
        }
        val user = when (role.uppercase()) {
            "STUDENT" -> User("demo.student@hydroguard.local", "Demo Student", "STUDENT", "A", "DEMO")
            "ADMIN" -> User("demo.admin@hydroguard.local", "Demo Administrator", "ADMIN", "", "")
            else -> return Result.failure(IllegalArgumentException("Unsupported development role."))
        }
        return try {
            hydroDao.insertUser(user)
            _currentUserFlow.value = user
            Result.success(user)
        } catch (e: Exception) {
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
        if (role.uppercase() != "STUDENT") {
            return Result.failure(Exception("Administrator accounts must be provisioned by an authorized administrator."))
        }
        val user = User(
            email = email,
            name = name,
            role = "STUDENT",
            hostelBlock = hostelBlock,
            roomNumber = roomNumber
        )

        if (!_isFirebaseAvailable.value || firebaseAuth == null) {
            return Result.failure(Exception("Authentication is unavailable. Configure Firebase before creating an account."))
        }

        return try {
            val authResult = firebaseAuth!!.createUserWithEmailAndPassword(email, password).await()
            val firebaseUser = authResult.user ?: throw Exception("Registration succeeded but Firebase user is null")
            
            hydroDao.insertUser(user)
            _currentUserFlow.value = user
            Result.success(user)
        } catch (e: Exception) {
            Log.e("FirebaseAuthRepository", "Firebase signup failed", e)
            Result.failure(e)
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
