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
import com.google.firebase.auth.AuthResult
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
    private val apiRepository: ApiRepository = ApiRepository()
) {
    @Deprecated("Demo sign-in now uses Firebase custom authentication; API tokens are not used.")
    constructor(
        hydroDao: HydroDao,
        context: Context,
        @Suppress("UNUSED_PARAMETER") legacyDevelopmentApiToken: String
    ) : this(hydroDao, context, ApiRepository())

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

    private suspend fun signInWithDevelopmentDemoStudent(): Result<User> {
        if (!_isFirebaseAvailable.value || firebaseAuth == null) {
            return Result.failure(IllegalStateException("Firebase authentication is not configured."))
        }
        return try {
            val customToken = apiRepository.createDevelopmentDemoStudentSession().getOrElse { throw it }
            if (customToken.isBlank()) throw SecurityException("The development sign-in service returned no credential.")
            val result: AuthResult = firebaseAuth!!.signInWithCustomToken(customToken).await()
            DevelopmentApiSession.clear()
            val firebaseUser = result.user
                ?: throw SecurityException("Firebase did not return an authenticated demo account.")
            val user = userFromFirebase(firebaseUser)
            if (user.role != "STUDENT" || !user.email.equals(DEMO_STUDENT_EMAIL, ignoreCase = true)) {
                firebaseAuth?.signOut()
                throw SecurityException("The development sign-in service returned an unexpected account.")
            }
            _currentUserFlow.value = user
            Result.success(user)
        } catch (exception: Exception) {
            if (exception is SecurityException) firebaseAuth?.signOut()
            Log.w("FirebaseAuthRepository", "Demo student authentication failed (${exception.javaClass.simpleName}).")
            Result.failure(exception)
        }
    }

    private suspend fun userFromFirebase(firebaseUser: FirebaseUser): User {
        val firebaseEmail = firebaseUser.email
            ?: throw SecurityException("This account is not authorized for HydroGuard.")
        firebaseUser.getIdToken(true).await()
            .token
            ?.takeIf(String::isNotBlank)
            ?: throw SecurityException("This account is not authorized for HydroGuard.")

        val serverAccount = apiRepository.bootstrapAccount().getOrElse { error ->
            if (error is ApiRequestFailure && error.statusCode in setOf(401, 403)) {
                throw SecurityException("This account is not authorized for HydroGuard.")
            }
            throw error
        }
        if (serverAccount.uid != firebaseUser.uid || !serverAccount.email.equals(firebaseEmail, ignoreCase = true)) {
            throw SecurityException("This account is not authorized for HydroGuard.")
        }
        val role = authorizedRole(serverAccount.role)
            ?: throw SecurityException("This account is not authorized for HydroGuard.")
        if (serverAccount.status != "ACTIVE") {
            throw SecurityException("This account is not authorized for HydroGuard.")
        }

        // Bootstrap writes the server-owned role claim. Force a fresh Firebase
        // ID token before the normal authenticated API session begins.
        val refreshedClaims = firebaseUser.getIdToken(true).await().claims
        if (authorizedRole(refreshedClaims["role"]) != role) {
            throw IllegalStateException("Account permissions are still updating. Please try again.")
        }

        val existing = hydroDao.getUserByEmail(firebaseEmail)
        val user = User(
            email = serverAccount.email,
            name = firebaseUser.displayName?.takeIf(String::isNotBlank)
                ?: existing?.name?.takeIf(String::isNotBlank)
                ?: serverAccount.displayName.takeIf(String::isNotBlank)
                ?: serverAccount.email.substringBefore('@'),
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

    /** Debug demo users retain their Room identity; the student session also signs in to Firebase. */
    suspend fun loginAsDevelopment(role: String): Result<User> {
        if (!DevelopmentAuthPolicy.allows(BuildConfig.DEBUG, BuildConfig.ALLOW_DEVELOPMENT_LOGIN)) {
            return Result.failure(SecurityException("Development Login is disabled in this build."))
        }
        if (role.equals("STUDENT", ignoreCase = true)) return signInWithDevelopmentDemoStudent()
        val user = when (role.uppercase()) {
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

    private companion object {
        const val DEMO_STUDENT_EMAIL = "demo.student@hydroguard.local"
    }
}
