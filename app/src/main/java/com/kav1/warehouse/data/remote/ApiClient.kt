package com.kav1.warehouse.data.remote

import com.google.gson.Gson
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {
    val gson: Gson = Gson()

    /**
     * Returns [input] as a valid base URL ending with "/" (adding "http://"
     * and the trailing slash if missing), or null if it is not a valid URL.
     */
    fun normalizeBaseUrl(input: String): String? {
        var url = input.trim()
        if (url.isEmpty()) return null
        if (!url.startsWith("http://") && !url.startsWith("https://")) url = "http://$url"
        if (!url.endsWith("/")) url += "/"
        return if (HttpUrl.parse(url) != null) url else null
    }

    fun create(baseUrl: String): WarehouseApi {
        // Short connect timeout: devices are usually off the tether, and we
        // want to fail fast rather than hang the UI or a worker.
        val http = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(http)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(WarehouseApi::class.java)
    }
}
