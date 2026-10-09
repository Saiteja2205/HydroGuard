package com.aistudio.hydroguard.wxqpzx.data.database;

import androidx.annotation.NonNull;
import androidx.room.Entity;
import androidx.room.Ignore;
import androidx.room.PrimaryKey;

@Entity(tableName = "users")
public class User {
    @PrimaryKey @NonNull public String email = "";
    @NonNull public String name = "";
    @NonNull public String role = "STUDENT";
    @NonNull public String hostelBlock = "";
    @NonNull public String roomNumber = "";
    public long createdAt = System.currentTimeMillis();

    public User() { }

    @Ignore public User(@NonNull String email, @NonNull String name, @NonNull String role,
                @NonNull String hostelBlock, @NonNull String roomNumber) {
        this.email = email;
        this.name = name;
        this.role = role;
        this.hostelBlock = hostelBlock;
        this.roomNumber = roomNumber;
    }
}
