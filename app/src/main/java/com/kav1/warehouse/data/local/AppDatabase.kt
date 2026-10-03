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
        HoldingEntity::class,
    ],
    version = 5,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun itemDao(): ItemDao
    abstract fun userDao(): UserDao
    abstract fun pendingTransactionDao(): PendingTransactionDao
    abstract fun categoryDao(): CategoryDao
    abstract fun historyDao(): HistoryDao
    abstract fun holdingDao(): HoldingDao

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

        /** v4: stock quantity per item, quantities on actions, and per-soldier holdings. */
        val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE items ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")
                db.execSQL("ALTER TABLE items ADD COLUMN available_qty INTEGER NOT NULL DEFAULT 1")
                db.execSQL("ALTER TABLE items ADD COLUMN borrowed_qty INTEGER NOT NULL DEFAULT 0")
                db.execSQL("ALTER TABLE items ADD COLUMN issued_qty INTEGER NOT NULL DEFAULT 0")
                // Existing items: one unit, held by its holder if it is out.
                db.execSQL(
                    "UPDATE items SET available_qty = 0, " +
                        "borrowed_qty = CASE current_status WHEN 'BORROWED' THEN 1 ELSE 0 END, " +
                        "issued_qty = CASE current_status WHEN 'ISSUED' THEN 1 ELSE 0 END " +
                        "WHERE current_status != 'AVAILABLE'",
                )
                db.execSQL("ALTER TABLE pending_transactions ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")
                db.execSQL("ALTER TABLE history ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS holdings (qr_id TEXT NOT NULL, user_id TEXT NOT NULL, " +
                        "borrowed INTEGER NOT NULL, issued INTEGER NOT NULL, since INTEGER, " +
                        "PRIMARY KEY(qr_id, user_id))",
                )
                db.execSQL("CREATE INDEX IF NOT EXISTS index_holdings_user_id ON holdings (user_id)")
                db.execSQL(
                    "INSERT OR REPLACE INTO holdings (qr_id, user_id, borrowed, issued, since) " +
                        "SELECT qr_id, holder_user_id, borrowed_qty, issued_qty, last_action_at FROM items " +
                        "WHERE holder_user_id IS NOT NULL AND current_status != 'AVAILABLE'",
                )
            }
        }

        /** v5: item kind (loan / consumable). */
        val MIGRATION_4_5 = object : Migration(4, 5) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE items ADD COLUMN kind TEXT NOT NULL DEFAULT 'LOAN'")
            }
        }

        fun get(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "warehouse.db",
                ).addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5).build().also { instance = it }
            }
    }
}
