package com.example.data.repository

import android.content.Context
import android.util.Log
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.CredentialManager
import com.example.BuildConfig
import com.example.data.database.HydroDao
import com.example.data.database.User
import com.google.android.gms.tasks.Task
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseUser
import com.google.firebase.auth.GoogleAuthProvider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class FirebaseAuthRepository(
    private val hydroDao: HydroDao,
    private val context: Context,
    private val developmentApiToken: String = BuildConfig.DEVELOPMENT_API_TOKEN
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
            firebaseAuth?.currentUser?.let(::restoreFirebaseSession)
        } catch (exception: Exception) {
            // Firebase can be unavailable until the app's Firebase configuration is supplied.
            Log.w("FirebaseAuthRepository", "Firebase initialization unavailable (${exception.javaClass.simpleName}).")
            _isFirebaseAvailable.value = false
        }
    }

    private fun restoreFirebaseSession(firebaseUser: FirebaseUser) {
        CoroutineScope(Dispatchers.IO).launch {
            runCatching { userFromFirebase(firebaseUser) }
                .onSuccess { _currentUserFlow.value = it }
                .onFailure { error ->
                    if (error is SecurityException) firebaseAuth?.signOut()
                    Log.w("FirebaseAuthRepository", "Session restoration unavailable (${error.javaClass.simpleName}).")
                }
        }
    }

    suspend fun signInWithGoogleIdToken(idToken: String): Result<User> {
        if (!_isFirebaseAvailable.value || firebaseAuth == null) {
            return Result.failure(IllegalStateException("Firebase authentication is not configured."))
        }
        if (idToken.isBlank()) return Result.failure(SecurityException("Google did not return an authentication token."))

        return try {
            val credential = GoogleAuthProvider.getCredential(idToken, null)
            val result = firebaseAuth!!.signInWithCredential(credential).await()
            DevelopmentApiSession.clear()
            val firebaseUser = result.user ?: throw SecurityException("Firebase did not return an authenticated user.")
            val user = userFromFirebase(firebaseUser)
            _currentUserFlow.value = user
            Result.success(user)
        } catch (exception: Exception) {
            if (exception is SecurityException) firebaseAuth?.signOut()
            // Never include account tokens or provider response bodies in application logs.
            Log.w("FirebaseAuthRepository", "Google authentication failed (${exception.javaClass.simpleName}).")
            Result.failure(exception)
        }
    }

    private suspend fun userFromFirebase(firebaseUser: FirebaseUser): User {
        val email = firebaseUser.email ?: throw SecurityException("The Google account does not provide an email address.")
        val tokenClaims = firebaseUser.getIdToken(true).await().claims
        val role = authorizedRole(tokenClaims["role"])
            ?: throw SecurityException("This Google account has not been assigned a HydroGuard role.")

        val existing = hydroDao.getUserByEmail(email)
        val user = User(
            email = email,
            name = firebaseUser.displayName?.takeIf(String::isNotBlank)
                ?: existing?.name?.takeIf(String::isNotBlank)
                ?: email.substringBefore('@'),
            role = role,
            hostelBlock = existing?.hostelBlock.orEmpty(),
            roomNumber = existing?.roomNumber.orEmpty()
        )
        hydroDao.insertUser(user)
        return user
    }

    private fun authorizedRole(value: Any?): String? = when ((value as? String)?.trim()?.uppercase()) {
        "STUDENT" -> "STUDENT"
        "ADMIN" -> "ADMIN"
        else -> null
    }

    /** Local-only identity for debug demos. The release variant compiles with this disabled. */
    suspend fun loginAsDevelopment(role: String): Result<User> {
        if (!DevelopmentAuthPolicy.apiBridgeConfigured(
                BuildConfig.DEBUG,
                BuildConfig.ALLOW_DEVELOPMENT_LOGIN,
                developmentApiToken
            )
        ) {
            val message = if (!BuildConfig.DEBUG || !BuildConfig.ALLOW_DEVELOPMENT_LOGIN) {
                "Development Login is disabled in this build."
            } else {
                "Development login is not configured."
            }
            return Result.failure(SecurityException(message))
        }
        if (!DevelopmentAuthPolicy.allows(BuildConfig.DEBUG, BuildConfig.ALLOW_DEVELOPMENT_LOGIN)) {
            return Result.failure(SecurityException("Development Login is disabled in this build."))
        }
        val user = when (role.uppercase()) {
            "STUDENT" -> User("demo.student@hydroguard.local", "Demo Student", "STUDENT", "", "")
            "ADMIN" -> User("demo.admin@hydroguard.local", "Demo Administrator", "ADMIN", "", "")
            else -> return Result.failure(IllegalArgumentException("Unsupported development role."))
        }
        return try {
            hydroDao.insertUser(user)
            DevelopmentApiSession.set(user.email, user.role)
            _currentUserFlow.value = user
            Result.success(user)
        } catch (exception: Exception) {
            Result.failure(exception)
        }
    }

    fun signOut() {
        DevelopmentApiSession.clear()
        _currentUserFlow.value = null
        try {
            firebaseAuth?.signOut()
        } catch (exception: Exception) {
            Log.w("FirebaseAuthRepository", "Sign-out unavailable (${exception.javaClass.simpleName}).")
        }
        CoroutineScope(Dispatchers.IO).launch {
            runCatching {
                CredentialManager.create(context.applicationContext)
                    .clearCredentialState(ClearCredentialStateRequest())
            }.onFailure { exception ->
                Log.w("FirebaseAuthRepository", "Credential-provider sign-out unavailable (${exception.javaClass.simpleName}).")
            }
        }
    }

    private suspend fun <T> Task<T>.await(): T = suspendCancellableCoroutine { continuation ->
        addOnCompleteListener { task ->
            if (task.isSuccessful) continuation.resume(task.result)
            else continuation.resumeWithException(task.exception ?: RuntimeException("Firebase operation failed"))
        }
    }
}
