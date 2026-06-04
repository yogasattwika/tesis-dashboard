# etl/load_to_db.py
import pandas as pd
import sqlite3
from pathlib import Path

# =========================
# CONFIG
# =========================
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "datawarehouse.db"
DATA_DIR = BASE_DIR / "1 data"

conn = sqlite3.connect(DB_PATH)

# =========================
# 1. LOAD DATA LAUNDRY 
# =========================
df_laundry = pd.read_csv(DATA_DIR / "final_laundry_daily_90days.csv")

df_laundry["tanggal"] = pd.to_datetime(df_laundry["tanggal"])

df_laundry["pendapatan_harian"] = pd.to_numeric(df_laundry["pendapatan_harian"], errors="coerce").fillna(0)
df_laundry["biaya_tak_terduga"] = pd.to_numeric(df_laundry["biaya_tak_terduga"], errors="coerce").fillna(0)
# 🔥 laba
df_laundry["laba_harian"] = df_laundry["pendapatan_harian"] - df_laundry["biaya_tak_terduga"]
df_laundry["laba_harian"] = df_laundry["laba_harian"].fillna(0)

print(df_laundry[[
    "pendapatan_harian",
    "biaya_tak_terduga",
    "laba_harian"
]].head())

# 🔥 id_waktu
df_laundry["id_waktu"] = df_laundry["tanggal"].dt.strftime("%Y%m%d").astype(int)

# =========================
# 2. LOAD & MERGE DATA KOS (DATA MART)
# =========================
df_hunian = pd.read_csv(DATA_DIR / "final_kos_hunian_36months_full_payment.csv")
df_inout = pd.read_csv(DATA_DIR / "final_kos_inout_36months.csv")
df_operasional = pd.read_csv(DATA_DIR / "final_kos_operational_36months.csv")

print("\nKOLOM HUNIAN:", df_hunian.columns)
print("KOLOM INOUT:", df_inout.columns)
print("KOLOM OPERASIONAL:", df_operasional.columns)

# =========================
# NORMALISASI NAMA KOLOM (WAJIB 🔥)
# =========================
df_inout.columns = df_inout.columns.str.lower().str.strip()
df_operasional.columns = df_operasional.columns.str.lower().str.strip()

# mapping fleksibel (biar gak error)
if "masuk" in df_inout.columns:
    df_inout.rename(columns={"masuk": "jumlah_masuk"}, inplace=True)

if "keluar" in df_inout.columns:
    df_inout.rename(columns={"keluar": "jumlah_keluar"}, inplace=True)

# =========================
# sesuaikan CSV
# =========================

# INOUT
df_inout.rename(columns={
    "penghuni_masuk": "jumlah_masuk",
    "penghuni_keluar": "jumlah_keluar"
}, inplace=True)

# OPERASIONAL
df_operasional.rename(columns={
    "pengeluaran_operasional_kos": "biaya_operasional",
    "biaya_tak_terduga_kos": "biaya_tak_terduga"
}, inplace=True)

# =========================
# NORMALISASI TANGGAL
# =========================
def parse_tanggal(df, kolom="bulan"):
    df[kolom] = pd.to_datetime(df[kolom], errors="coerce")

    if df[kolom].isnull().all():
        print("Format bulan tidak terbaca, pakai index fallback...")
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

# 🔥 samakan format tanggal
df_hunian["bulan"] = df_hunian["bulan"].dt.normalize()
df_inout["bulan"] = df_inout["bulan"].dt.normalize()
df_operasional["bulan"] = df_operasional["bulan"].dt.normalize()

# =========================
# MERGE DATA
# =========================
df_kos = df_hunian.merge(df_inout, on="bulan", how="left")
df_kos = df_kos.merge(df_operasional, on="bulan", how="left")

print("\nCEK DATA SETELAH FIX:")
print(df_kos[[
    "jumlah_masuk",
    "jumlah_keluar",
    "biaya_operasional",
    "biaya_tak_terduga"
]].head())

# =========================
# HANDLE KOLOM (ANTI ERROR 🔥)
# =========================
if "jumlah_masuk" not in df_kos.columns:
    df_kos["jumlah_masuk"] = 0

if "jumlah_keluar" not in df_kos.columns:
    df_kos["jumlah_keluar"] = 0

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
# FIX KAMAR (BIAR GAK DESIMAL)
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
# TAMBAHAN DIAGNOSTIK 🔥
# =========================
df_kos["net_penghuni"] = df_kos["jumlah_masuk"] - df_kos["jumlah_keluar"]

# =========================
# TAMBAH ID WAKTU
# =========================
df_kos["id_waktu"] = df_kos["bulan"].dt.strftime("%Y%m%d").astype(int)

# =========================
# RENAME KOLOM (AMAN)
# =========================
df_kos["kamar_terisi"] = (
    df_kos["total_kamar"] * df_kos["occupancy_rate"]
).round().astype(int)

df_kos["kamar_kosong"] = df_kos["total_kamar"] - df_kos["kamar_terisi"]
df_kos = df_kos.loc[:, ~df_kos.columns.duplicated()]
# =========================
# DATA MART FINAL
# =========================
fact_kos = df_kos[[
    "id_waktu",
    "bulan",
    "occupancy_rate",
    "total_kamar",
    "kamar_terisi",
    "kamar_kosong",
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
print("✅ fact_kos_diagnostik berhasil disimpan")

# =========================
# 3. DIMENSI WAKTU
# =========================
all_tanggal = pd.concat([
    df_laundry["tanggal"],
    df_kos["bulan"]
], ignore_index=True)

all_tanggal = all_tanggal.dropna().drop_duplicates()

dim_waktu = pd.DataFrame({"tanggal": all_tanggal})

dim_waktu["id_waktu"] = dim_waktu["tanggal"].dt.strftime("%Y%m%d").astype(int)
dim_waktu["bulan"] = dim_waktu["tanggal"].dt.month
dim_waktu["tahun"] = dim_waktu["tanggal"].dt.year
dim_waktu["hari"] = dim_waktu["tanggal"].dt.day_name()

dim_waktu.to_sql("dim_waktu", conn, if_exists="replace", index=False)

# =========================
# 4. LOAD FACT TABLES
# =========================
df_laundry.to_sql("fact_laundry_harian", conn, if_exists="replace", index=False)
fact_kos.to_sql("fact_kos_diagnostik", conn, if_exists="replace", index=False)

# =========================
# 5. EVENT PENGELUARAN LAUNDRY
# =========================
df_event = df_laundry[df_laundry["biaya_tak_terduga"] > 0].copy()

df_event["jenis_pengeluaran"] = "biaya_tak_terduga"
df_event["nominal"] = df_event["biaya_tak_terduga"]
df_event["keterangan"] = "biaya operasional tak terduga"

fact_pengeluaran = df_event[[
    "tanggal",
    "id_waktu",
    "jenis_pengeluaran",
    "nominal",
    "keterangan"
]]
print("\nCEK BIAYA TAK TERDUGA:")
print(df_laundry["biaya_tak_terduga"].describe())
fact_pengeluaran.to_sql("fact_pengeluaran_laundry", conn, if_exists="replace", index=False)

# =========================
# DEBUG
# =========================
print("\n=== CEK TABEL ===")
print(pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn))

print("\n=== SAMPLE KOS DIAGNOSTIK ===")
print(fact_kos.head())

# =========================
# CLOSE
# =========================
conn.close()

print("\n💀 ETL SELESAI - DATA MART SIAP DIPAKAI")