package com.kav1.warehouse.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [ItemEntity::class, UserEntity::class, PendingTransactionEntity::class],
    version = 2,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun itemDao(): ItemDao
    abstract fun userDao(): UserDao
    abstract fun pendingTransactionDao(): PendingTransactionDao

    companion object {
        @Volatile
        private var instance: AppDatabase? = null

        /** v2: item holder / last action time, and pending-upload flags for local management edits. */
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE items ADD COLUMN holder_user_id TEXT")
                db.execSQL("ALTER TABLE items ADD COLUMN last_action_at INTEGER")
                db.execSQL("ALTER TABLE items ADD COLUMN pending_upload INTEGER NOT NULL DEFAULT 0")
                db.execSQL("ALTER TABLE users ADD COLUMN pending_upload INTEGER NOT NULL DEFAULT 0")
            }
        }

        fun get(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "warehouse.db",
                ).addMigrations(MIGRATION_1_2).build().also { instance = it }
            }
    }
}
