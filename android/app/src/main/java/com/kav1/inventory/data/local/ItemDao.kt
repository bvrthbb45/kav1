package com.kav1.inventory.data.local

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface ItemDao {
    @Query("SELECT * FROM items WHERE qrId = :qrId")
    fun observe(qrId: String): Flow<Item?>

    @Query("SELECT * FROM items WHERE qrId = :qrId")
    suspend fun get(qrId: String): Item?

    @Upsert
    suspend fun upsert(item: Item)

    @Upsert
    suspend fun upsertAll(items: List<Item>)

    @Query("DELETE FROM items WHERE qrId IN (:qrIds)")
    suspend fun deleteByIds(qrIds: List<String>)
}
