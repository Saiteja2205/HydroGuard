package com.example.data.database

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [
        User::class,
        SensorNode::class,
        SensorReading::class,
        Prediction::class,
        Alert::class,
        NotificationLog::class,
        WaterFeedback::class,
        HostelFeedback::class,
        WaterQualityReport::class,
        AuditLog::class
    ],
    version = 2,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun hydroDao(): HydroDao

    companion object {
        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE sensor_readings ADD COLUMN red INTEGER")
                db.execSQL("ALTER TABLE sensor_readings ADD COLUMN green INTEGER")
                db.execSQL("ALTER TABLE sensor_readings ADD COLUMN blue INTEGER")
                db.execSQL("ALTER TABLE sensor_readings ADD COLUMN clear INTEGER")
                db.execSQL("ALTER TABLE sensor_readings ADD COLUMN opticalColourIndex REAL")
                db.execSQL("ALTER TABLE sensor_readings ADD COLUMN calibrationId INTEGER")
                db.execSQL("ALTER TABLE sensor_readings ADD COLUMN source TEXT NOT NULL DEFAULT 'DEMO'")
            }
        }

        @Volatile
        private var INSTANCE: AppDatabase? = null

        fun getDatabase(context: Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "hydroguard_database"
                )
                .fallbackToDestructiveMigration(true)
                .addMigrations(MIGRATION_1_2)
                .build()
                INSTANCE = instance
                instance
            }
        }
    }
}
