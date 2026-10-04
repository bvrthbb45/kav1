plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.devtools.ksp")
}

android {
    namespace = "com.kav1.warehouse"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.kav1.warehouse"
        // API 19 = Galaxy Tab 3. This pins several libraries below to their last
        // API-19-compatible versions; bumping minSdk to 21 lifts all of those caps.
        minSdk = 19
        targetSdk = 34
        versionCode = 10
        versionName = "1.9"

        multiDexEnabled = true
        // Vector drawables are rasterised to PNG at build time for API < 21.

        buildConfigField("String", "SERVER_BASE_URL", "\"http://192.168.42.100:8000/\"")

        ksp {
            arg("room.schemaLocation", "$projectDir/schemas")
        }
    }

    buildTypes {
        release {
            // Kept off: Gson/Retrofit reflection would need keep rules and the
            // app is side-loaded on a closed network anyway.
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
    kotlinOptions {
        jvmTarget = "1.8"
    }
    buildFeatures {
        buildConfig = true
        viewBinding = true
    }
}

dependencies {
    // AndroidX — last releases that still support minSdk 19.
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.activity:activity-ktx:1.8.2")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.6.2")
    implementation("androidx.multidex:multidex:2.0.1")

    // Room
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")

    // WorkManager (2.10+ requires API 21)
    implementation("androidx.work:work-runtime-ktx:2.9.1")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

    // Retrofit 2.6.x + OkHttp 3.12.x are the last versions supporting API < 21.
    implementation("com.squareup.retrofit2:retrofit:2.6.4")
    implementation("com.squareup.retrofit2:converter-gson:2.6.4")
    implementation("com.squareup.okhttp3:okhttp") {
        version { strictly("3.12.13") }
    }

    // ZXing Embedded: zxing core 3.4+ needs API 24, so pin core to 3.3.0.
    implementation("com.journeyapps:zxing-android-embedded:4.3.0") { isTransitive = false }
    implementation("com.google.zxing:core:3.3.0")
}
