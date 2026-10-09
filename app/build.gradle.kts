import com.google.gms.googleservices.GoogleServicesPlugin.MissingGoogleServicesStrategy
import java.net.URI
import java.util.Properties

plugins {
  alias(libs.plugins.android.application)
  alias(libs.plugins.google.services)
}

val debugApiBaseUrl = providers.gradleProperty("HYDROGUARD_API_BASE_URL")
  .orElse(providers.environmentVariable("HYDROGUARD_API_BASE_URL"))
  .getOrElse("http://10.0.96.236:8000/")
val releaseApiBaseUrl = providers.gradleProperty("HYDROGUARD_RELEASE_API_BASE_URL")
  .orElse(providers.environmentVariable("HYDROGUARD_RELEASE_API_BASE_URL"))
  .getOrElse("")
val developmentApiTokenFromFile = providers.provider {
  val authFile = rootProject.file(".dev-auth.env")
  if (!authFile.isFile) "" else Properties().apply {
    authFile.inputStream().use(::load)
  }.getProperty("HYDROGUARD_DEV_API_TOKEN", "").trim()
}
val developmentApiToken = providers.gradleProperty("HYDROGUARD_DEV_API_TOKEN")
  .orElse(providers.environmentVariable("HYDROGUARD_DEV_API_TOKEN"))
  .orElse(developmentApiTokenFromFile)
  .getOrElse("")
val escapedDevelopmentApiToken = developmentApiToken
  .replace("\\", "\\\\")
  .replace("\"", "\\\"")

android {
  enableKotlin = false
  namespace = "com.aistudio.hydroguard.wxqpzx"
  compileSdk { version = release(36) { minorApiLevel = 1 } }

  defaultConfig {
    applicationId = "com.aistudio.hydroguard.wxqpzx"
    minSdk = 24
    targetSdk = 36
    versionCode = 1
    versionName = "1.0"
    buildConfigField("String", "API_BASE_URL", "\"$debugApiBaseUrl\"")
    testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
  }

  signingConfigs {
    val keystorePath = System.getenv("KEYSTORE_PATH")
    val storePasswordValue = System.getenv("STORE_PASSWORD")
    val keyAliasValue = System.getenv("KEY_ALIAS")
    val keyPasswordValue = System.getenv("KEY_PASSWORD")
    if (listOf(keystorePath, storePasswordValue, keyAliasValue, keyPasswordValue).all { !it.isNullOrBlank() }) {
      create("release") {
        storeFile = file(keystorePath!!)
        storePassword = storePasswordValue
        keyAlias = keyAliasValue
        keyPassword = keyPasswordValue
      }
    }
  }

  buildTypes {
    release {
      isCrunchPngs = false
      isMinifyEnabled = false
      buildConfigField("String", "API_BASE_URL", "\"$releaseApiBaseUrl\"")
      buildConfigField("boolean", "ALLOW_DEVELOPMENT_LOGIN", "false")
      buildConfigField("String", "DEVELOPMENT_API_TOKEN", "\"\"")
      proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
      signingConfigs.findByName("release")?.let { signingConfig = it }
    }
    debug {
      buildConfigField("boolean", "ALLOW_DEVELOPMENT_LOGIN", "true")
      buildConfigField("String", "DEVELOPMENT_API_TOKEN", "\"$escapedDevelopmentApiToken\"")
      signingConfig = android.signingConfigs.findByName("debug")
    }
  }

  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
  }
  buildFeatures { buildConfig = true }
  testOptions { unitTests { isIncludeAndroidResources = true } }
}

val validateReleaseConfiguration by tasks.registering {
  doLast {
    if (!releaseApiBaseUrl.startsWith("https://")) {
      throw GradleException("Set HYDROGUARD_RELEASE_API_BASE_URL to the production HTTPS API URL before building a release.")
    }
    val releaseApiHost = runCatching { URI(releaseApiBaseUrl).host?.lowercase() }.getOrNull()
    val privateIpv4 = releaseApiHost?.split(".")?.mapNotNull { it.toIntOrNull() }
    val isLocalOrPrivate = releaseApiHost == null || releaseApiHost == "localhost" || releaseApiHost.endsWith(".local")
        || releaseApiHost.startsWith("127.") || releaseApiHost.startsWith("10.")
        || releaseApiHost.startsWith("192.168.")
        || (releaseApiHost.startsWith("172.") && privateIpv4?.getOrNull(1) in 16..31)
    if (releaseApiHost.isNullOrBlank() || isLocalOrPrivate) {
      throw GradleException("The release API URL must use a production host, not a local development address.")
    }
    val requiredSigning = listOf("KEYSTORE_PATH", "STORE_PASSWORD", "KEY_ALIAS", "KEY_PASSWORD")
    val missing = requiredSigning.filter { System.getenv(it).isNullOrBlank() }
    val keyStore = System.getenv("KEYSTORE_PATH")?.let(::file)
    if (missing.isNotEmpty() || keyStore?.isFile != true) {
      throw GradleException("Release signing is not configured. Supply a private keystore and all signing values through environment variables.")
    }
  }
}

tasks.configureEach {
  if (name == "assembleRelease" || name == "bundleRelease") dependsOn(validateReleaseConfiguration)
}

googleServices {
  missingGoogleServicesStrategy = MissingGoogleServicesStrategy.ERROR
}

dependencies {
  implementation(platform(libs.firebase.bom))
  implementation("com.google.android.material:material:1.12.0")
  implementation(libs.androidx.lifecycle.livedata) {
    exclude(group = "androidx.lifecycle", module = "lifecycle-viewmodel")
  }
  implementation(libs.androidx.lifecycle.process)
  implementation(libs.androidx.lifecycle.runtime.android)
  implementation(libs.androidx.lifecycle.viewmodel.android)
  implementation(libs.androidx.lifecycle.common.java8)
  implementation(libs.androidx.room.runtime)
  annotationProcessor(libs.androidx.room.compiler)
  implementation(libs.firebase.auth)
  implementation(libs.okhttp)
  implementation(libs.androidx.credentials)
  implementation(libs.androidx.credentials.play.services.auth)
  implementation(libs.google.id)
  implementation(libs.retrofit)
  testImplementation(libs.junit)
}

configurations.configureEach {
  exclude(group = "androidx.lifecycle", module = "lifecycle-viewmodel")
  exclude(group = "androidx.lifecycle", module = "lifecycle-runtime")
}
