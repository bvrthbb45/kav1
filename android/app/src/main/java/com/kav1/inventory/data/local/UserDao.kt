package com.kav1.inventory.data.local

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface UserDao {
    @Query("SELECT * FROM users ORDER BY name COLLATE NOCASE")
    fun observeAll(): Flow<List<User>>

    @Upsert
    suspend fun upsertAll(users: List<User>)

    @Query("DELETE FROM users WHERE userId IN (:userIds)")
    suspend fun deleteByIds(userIds: List<String>)
}
