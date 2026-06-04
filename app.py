from flask import Flask, render_template, jsonify, request
import sqlite3
import pandas as pd
from pathlib import Path

app = Flask(__name__)

# =========================
# CONFIG
# =========================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "datawarehouse.db"

def get_conn():
    return sqlite3.connect(str(DB_PATH))

# =========================
# HOME
# =========================
@app.route("/")
def index():
    return render_template("dashboard.html")

# =========================
# API KOS (DIAGNOSTIK 🔥)
# =========================
@app.route("/api/kos")
def api_kos():
    try:
        conn = get_conn()
        bulan = request.args.get("bulan")

        query = """
        SELECT 
            d.tanggal,
            d.bulan,
            d.tahun,
            f.total_kamar,
            f.kamar_terisi,
            f.kamar_kosong,
            f.occupancy_rate,
            f.rata_hari_kosong,
            f.pemasukan_kos_bulanan,
            f.jumlah_masuk,
            f.jumlah_keluar,
            f.biaya_operasional,
            f.biaya_tak_terduga,
            f.profit_kos,
            f.net_penghuni
        FROM fact_kos_diagnostik f
        JOIN dim_waktu d ON f.id_waktu = d.id_waktu
        """

        if bulan and bulan != "all":
            query += " WHERE d.bulan = ?"
            df = pd.read_sql_query(query, conn, params=[bulan])
        else:
            df = pd.read_sql_query(query, conn)

        query += " ORDER BY d.tanggal"

        df = df.fillna(0)

        print("\nDATA KOS API:")
        print(df.head())

        conn.close()

        return df.to_json(orient="records")

    except Exception as e:
        return jsonify({"error": str(e)})

# =========================
# API LAUNDRY
# =========================
@app.route("/api/laundry")
def api_laundry():
    try:
        conn = get_conn()

        bulan = request.args.get("bulan")

        query = """
        SELECT 
            d.tanggal,
            d.hari,
            d.bulan,
            f.jumlah_transaksi,
            f.berat_total_kg,
            f.pendapatan_harian,
            f.laba_harian,
            f.indikator_antrian
        FROM fact_laundry_harian f
        JOIN dim_waktu d ON f.id_waktu = d.id_waktu
        """

        if bulan and bulan != "all":
            query += f" WHERE d.bulan = {bulan}"

        query += " ORDER BY d.tanggal"

        df = pd.read_sql_query(query, conn)
        conn.close()

        return df.to_json(orient="records")

    except Exception as e:
        return jsonify({"error": str(e)})

# =========================
# API PENGELUARAN LAUNDRY
# =========================
@app.route("/api/pengeluaran_laundry")
def api_pengeluaran_laundry():
    try:
        conn = get_conn()
        bulan = request.args.get("bulan")

        query = """
        SELECT 
            tanggal,
            nominal
        FROM fact_pengeluaran_laundry
        """

        df = pd.read_sql_query(query, conn)

        # filter manual (karena tanpa join)
        if bulan and bulan != "all":
            df["tanggal"] = pd.to_datetime(df["tanggal"])
            df = df[df["tanggal"].dt.month == int(bulan)]

        df = df.fillna(0)

        conn.close()
        return df.to_json(orient="records")

    except Exception as e:
        return jsonify({"error": str(e)})

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)