import sqlite3

conn = sqlite3.connect("../datawarehouse.db")
conn.close()

print("Database berhasil dibuat!")
