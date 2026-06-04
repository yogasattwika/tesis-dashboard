import pandas as pd
import sqlite3
from pathlib import Path

# =========================
# CONFIG
# =========================
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "1 data"
DB_PATH = BASE_DIR / "datawarehouse.db"

print("DB PATH:", DB_PATH)
conn = sqlite3.connect(DB_PATH)

# =========================
# 1. DIM_WAKTU
# =========================
dates = pd.date_range(start="2022-01-01", end="2025-12-31")

dim_waktu = pd.DataFrame({"tanggal": dates})

dim_waktu["id_waktu"] = dim_waktu.index + 1
dim_waktu["hari"] = dim_waktu["tanggal"].dt.day_name()
dim_waktu["bulan"] = dim_waktu["tanggal"].dt.month
dim_waktu["tahun"] = dim_waktu["tanggal"].dt.year
dim_waktu["is_weekend"] = dim_waktu["hari"].isin(["Saturday", "Sunday"]).astype(int)

# 🔥 NORMALISASI
dim_waktu["tanggal"] = dim_waktu["tanggal"].dt.normalize()

dim_waktu.to_sql("dim_waktu", conn, if_exists="replace", index=False)

# =========================
# 2. FACT KOS DIAGNOSTIK
# =========================
df_hunian = pd.read_csv(DATA_DIR / "final_kos_hunian_36months_full_payment.csv")
df_inout = pd.read_csv(DATA_DIR / "final_kos_inout_36months.csv")
df_operasional = pd.read_csv(DATA_DIR / "final_kos_operational_36months.csv")

# =========================
# PARSE TANGGAL (AMAN)
# =========================
def parse_tanggal(df, kolom="bulan"):
    df[kolom] = pd.to_datetime(df[kolom], errors="coerce")

    if df[kolom].isnull().all():
        print("Fallback parsing tanggal...")
        start_year = 2021
        df["tahun"] = (df.index // 12) + start_year
        df["bulan_num"] = (df.index % 12) + 1

        df[kolom] = pd.to_datetime(
            df["tahun"].astype(str) + "-" +
            df["bulan_num"].astype(str) + "-01"
        )
    return df

df_hunian = parse_tanggal(df_hunian)
df_inout = parse_tanggal(df_inout)
df_operasional = parse_tanggal(df_operasional)

# =========================
# NORMALISASI TANGGAL
# =========================
df_hunian["bulan"] = df_hunian["bulan"].dt.normalize()
df_inout["bulan"] = df_inout["bulan"].dt.normalize()
df_operasional["bulan"] = df_operasional["bulan"].dt.normalize()

# =========================
# MERGE (INTI ETL)
# =========================
df_kos = df_hunian.merge(df_inout, on="bulan", how="left")
df_kos = df_kos.merge(df_operasional, on="bulan", how="left")

# =========================
# HANDLE KOLOM (ANTI ERROR 🔥)
# =========================

print("\nKOLOM SETELAH MERGE:")
print(df_kos.columns)

# cari kolom masuk
col_masuk = None
for col in df_kos.columns:
    if "masuk" in col.lower():
        col_masuk = col
        break

# cari kolom keluar
col_keluar = None
for col in df_kos.columns:
    if "keluar" in col.lower():
        col_keluar = col
        break

# assign aman
if col_masuk:
    df_kos["jumlah_masuk"] = df_kos[col_masuk]
else:
    print("⚠️ jumlah_masuk tidak ditemukan → isi 0")
    df_kos["jumlah_masuk"] = 0

if col_keluar:
    df_kos["jumlah_keluar"] = df_kos[col_keluar]
else:
    print("⚠️ jumlah_keluar tidak ditemukan → isi 0")
    df_kos["jumlah_keluar"] = 0

# biaya
if "biaya_operasional" not in df_kos.columns:
    df_kos["biaya_operasional"] = 0

if "biaya_tak_terduga" not in df_kos.columns:
    df_kos["biaya_tak_terduga"] = 0

# isi null
df_kos["jumlah_masuk"] = df_kos["jumlah_masuk"].fillna(0)
df_kos["jumlah_keluar"] = df_kos["jumlah_keluar"].fillna(0)
df_kos["biaya_operasional"] = df_kos["biaya_operasional"].fillna(0)
df_kos["biaya_tak_terduga"] = df_kos["biaya_tak_terduga"].fillna(0)

# =========================
# HITUNG KAMAR (NO DESIMAL)
# =========================
df_kos["kamar_terisi"] = (
    df_kos["total_kamar"] * df_kos["occupancy_rate"]
).round().astype(int)

df_kos["kamar_kosong"] = df_kos["total_kamar"] - df_kos["kamar_terisi"]

# =========================
# HITUNG PROFIT
# =========================
df_kos["profit_kos"] = (
    df_kos["pemasukan_kos_bulanan"]
    - df_kos["biaya_operasional"]
    - df_kos["biaya_tak_terduga"]
)

# =========================
# METRIK TAMBAHAN (OPSIONAL 🔥)
# =========================
df_kos["net_penghuni"] = df_kos["jumlah_masuk"] - df_kos["jumlah_keluar"]

# =========================
# JOIN DIM_WAKTU
# =========================
df_kos = df_kos.merge(dim_waktu, left_on="bulan", right_on="tanggal", how="left")

# =========================
# VALIDASI
# =========================
print("\nCEK ID_WAKTU NULL:", df_kos["id_waktu"].isnull().sum())

# =========================
# FINAL FACT TABLE
# =========================
fact_kos = df_kos[[
    "id_waktu",
    "total_kamar",
    "kamar_terisi",
    "kamar_kosong",
    "occupancy_rate",
    "rata_hari_kosong",
    "pemasukan_kos_bulanan",
    "jumlah_masuk",
    "jumlah_keluar",
    "biaya_operasional",
    "biaya_tak_terduga",
    "profit_kos",
    "net_penghuni"
]]

fact_kos.to_sql("fact_kos_diagnostik", conn, if_exists="replace", index=False)

# =========================
# 3. FACT LAUNDRY
# =========================
df_laundry = pd.read_csv(DATA_DIR / "final_laundry_daily_90days.csv")

df_laundry["tanggal"] = pd.to_datetime(df_laundry["tanggal"])
df_laundry["tanggal"] = df_laundry["tanggal"].dt.normalize()

df_laundry = df_laundry.merge(dim_waktu, on="tanggal", how="left")

# =========================
# HITUNG LABA HARIAN 🔥
# =========================
df_laundry["pendapatan_harian"] = pd.to_numeric(
    df_laundry["pendapatan_harian"],
    errors="coerce"
).fillna(0)

df_laundry["biaya_tak_terduga"] = pd.to_numeric(
    df_laundry["biaya_tak_terduga"],
    errors="coerce"
).fillna(0)

df_laundry["laba_harian"] = (
    df_laundry["pendapatan_harian"]
    - df_laundry["biaya_tak_terduga"]
)

# =========================
# FACT TABLE
# =========================
fact_laundry = df_laundry[[
    "id_waktu",
    "jumlah_transaksi",
    "berat_total_kg",
    "pendapatan_harian",
    "biaya_tak_terduga",
    "laba_harian",
    "indikator_antrian"
]]

fact_laundry.to_sql("fact_laundry_harian", conn, if_exists="replace", index=False)

# =========================
# DONE
# =========================
conn.close()

print("\n💀 DATA MART SIAP DIGUNAKAN")