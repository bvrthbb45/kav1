package com.kav1.warehouse.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        ItemEntity::class,
        UserEntity::class,
        PendingTransactionEntity::class,
        CategoryEntity::class,
        HistoryEntity::class,
    ],
    version = 3,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun itemDao(): ItemDao
    abstract fun userDao(): UserDao
    abstract fun pendingTransactionDao(): PendingTransactionDao
    abstract fun categoryDao(): CategoryDao
    abstract fun historyDao(): HistoryDao

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

        /** v3: item types (category + target quantity) and server-side action history. */
        val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE items ADD COLUMN category TEXT NOT NULL DEFAULT ''")
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS categories " +
                        "(name TEXT NOT NULL, target_qty INTEGER, PRIMARY KEY(name))",
                )
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS history (tx_id TEXT NOT NULL, qr_id TEXT NOT NULL, " +
                        "user_id TEXT NOT NULL, action_type TEXT NOT NULL, timestamp INTEGER NOT NULL, " +
                        "PRIMARY KEY(tx_id))",
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS index_history_qr_id ON history (qr_id)")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_history_user_id ON history (user_id)")
            }
        }

        fun get(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "warehouse.db",
                ).addMigrations(MIGRATION_1_2, MIGRATION_2_3).build().also { instance = it }
            }
    }
}
