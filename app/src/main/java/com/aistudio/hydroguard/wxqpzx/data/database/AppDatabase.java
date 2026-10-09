package com.aistudio.hydroguard.wxqpzx.data.database;

import android.content.Context;

import androidx.room.Database;
import androidx.room.Room;
import androidx.room.RoomDatabase;
import androidx.room.migration.Migration;
import androidx.sqlite.db.SupportSQLiteDatabase;

@Database(entities = {
        User.class, SensorNode.class, SensorReading.class, Prediction.class, Alert.class,
        NotificationLog.class, WaterFeedback.class, HostelFeedback.class,
        WaterQualityReport.class, AuditLog.class
}, version = 2, exportSchema = false)
public abstract class AppDatabase extends RoomDatabase {
    public abstract HydroDao hydroDao();

    private static volatile AppDatabase instance;

    private static final Migration MIGRATION_1_2 = new Migration(1, 2) {
        @Override public void migrate(SupportSQLiteDatabase db) {
            db.execSQL("ALTER TABLE sensor_readings ADD COLUMN red INTEGER");
            db.execSQL("ALTER TABLE sensor_readings ADD COLUMN green INTEGER");
            db.execSQL("ALTER TABLE sensor_readings ADD COLUMN blue INTEGER");
            db.execSQL("ALTER TABLE sensor_readings ADD COLUMN clear INTEGER");
            db.execSQL("ALTER TABLE sensor_readings ADD COLUMN opticalColourIndex REAL");
            db.execSQL("ALTER TABLE sensor_readings ADD COLUMN calibrationId INTEGER");
            db.execSQL("ALTER TABLE sensor_readings ADD COLUMN source TEXT NOT NULL DEFAULT 'DEMO'");
        }
    };

    public static AppDatabase getDatabase(Context context) {
        if (instance == null) {
            synchronized (AppDatabase.class) {
                if (instance == null) {
                    instance = Room.databaseBuilder(context.getApplicationContext(), AppDatabase.class,
                                    "hydroguard_database")
                            .addMigrations(MIGRATION_1_2)
                            .fallbackToDestructiveMigration()
                            .build();
                }
            }
        }
        return instance;
    }
}
