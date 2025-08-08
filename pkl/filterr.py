import traceback
import json  
from datetime import datetime
from flask_mysqldb import MySQL
import tempfile
import pandas as pd
import re
import os
from flask import Flask, render_template, request, send_file, session, redirect, Response
import logging


logging.basicConfig(level=logging.DEBUG)


app = Flask(__name__)


@app.errorhandler(500)
def internal_server_error(e):
    logging.error(f"Error 500: {traceback.format_exc()}")
    return f"Terjadi error: {traceback.format_exc()}", 500


# Konfigurasi Flask dan MySQL
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', '127.0.0.1')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', 'Tangot2304!')
# app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', 'Tangot2304!')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB', 'perusahaan_data')


mysql = MySQL(app)


@app.route('/')
def index():
    # Pastikan ada index.html di folder templates
    return render_template('index.html')


# Simpan path file dalam dictionary global
file_store = {}


def filter_data_gagal(data):
    hasil_filter = []
    waktu_filter = []
    grouped_counts = {}

    for baris in data:
        try:
            # penyesuaian format waktu
            waktu_match = re.search(
                r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}(?:,\d+)?', baris)
            if waktu_match:
                waktu = waktu_match.group(0)
            else:
                logging.warning(f"Waktu tidak ditemukan di baris: {baris}")
                continue  # Lewatkan baris jika tidak ada waktu

            # hapus waktu dari string untuk pencarian Nama GI
            baris_clean = re.sub(
                r'^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}(?:,\d+)?', '', baris).strip()

            # pastikan ada kata "NE" (bukan bagian dari kata "Bojonegoro" atau "New")
            if not re.search(r'\bNE\b', baris_clean):
                logging.debug(
                    f"Baris ini tidak mengandung NE, dilewati: {baris_clean}")
                continue  # Hanya lanjut jika ada "NE" yang berdiri sendiri

            # cari nama GI sesuai format yang diinginkan
            gi_match = re.search(
                r'([A-Z][A-Z0-9\s/-]+?)\s+(CB|BI\d+|TRAFO\s?\d+|TRAF0\s?\d+|Tap Position\s?\d+)',
                baris_clean, re.IGNORECASE
            )

            if gi_match:
                nama_gi = f"{gi_match.group(1)} {gi_match.group(2)}".strip()
            else:
                logging.warning(f"Nama GI tidak dikenali: {baris_clean}")
                nama_gi = "Tidak Dikenali"

           
            hasil_filter.append(nama_gi)
            waktu_filter.append(waktu)

            # hitung jumlah kemunculan tiap GI
            if nama_gi in grouped_counts:
                grouped_counts[nama_gi] += 1
            else:
                grouped_counts[nama_gi] = 1

        except Exception as e:
            logging.error(
                f"Error saat memproses baris: {baris}. Error: {str(e)}")

    # jika hasil filter kosong, beri log
    if not hasil_filter:
        logging.error(
            "Tidak ada data yang cocok setelah filtering untuk data gagal!")

    # Buat DataFrame dengan jumlah kegagalan
    df_gagal = pd.DataFrame({
        "NAMA GI": hasil_filter,
        "WAKTU": waktu_filter
    })

    # jumlah kali gagal berdasarkan jumlah kemunculan
    df_gagal["JUMLAH KALI (GAGAL)"] = df_gagal["NAMA GI"].map(grouped_counts)

    return df_gagal["NAMA GI"].tolist(), df_gagal["WAKTU"].tolist(), df_gagal["JUMLAH KALI (GAGAL)"].tolist()


def filter_data_gagal_rekap(data):
    hasil_filter = []
    waktu_filter = []

    for baris in data:
        try:
            # waktu
            waktu_match = re.search(
                r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}', baris)
            if not waktu_match:
                logging.warning(f"Waktu tidak ditemukan di baris: {baris}")
                continue
            waktu = waktu_match.group(0)

            # Hapus waktu dari string
            baris_clean = re.sub(
                r'^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}', '', baris).strip()

            # Pastikan ada kata "NE" 
            if not re.search(r'\bNE\b', baris_clean):
                logging.debug(
                    f"Baris ini tidak mengandung NE yang berdiri sendiri, dilewati: {baris_clean}")
                continue  # Skip langsung jika tidak ada "NE" yang valid

            # Regex untuk Nama GI
            gi_match = re.search(
                r'([A-Z][A-Z0-9\s/-]+?)\s+(CB|BI\d+|TRAFO\s?\d+|TRAF0\s?\d+|Tap Position\s?\d+)',
                baris_clean, re.IGNORECASE
            )

            if gi_match:
                nama_gi = f"{gi_match.group(1)} {gi_match.group(2)}".strip()
            else:
                logging.warning(f"Nama GI tidak dikenali: {baris_clean}")
                continue  # Jika tidak ada nama GI yang valid, skip juga

            hasil_filter.append(nama_gi)
            waktu_filter.append(waktu)

        except Exception as e:
            logging.error(
                f"Error saat memproses baris: {baris}. Error: {str(e)}")

    return hasil_filter, waktu_filter


def filter_data_sukses_rekap(data):
    hasil_filter, waktu_filter, info_sukses, ket_list = [], [], [], []
    grouped_status = {}

    for baris in data:
        nama_gi_match = re.search(
            r'([A-Z][A-Z0-9\s/-]+?)\s+(CB|BI\d+|TRAFO\s?\d+|TRAF0\s?\d+)',
            baris, re.IGNORECASE
        )
        if nama_gi_match:
            nama_gi = f"{nama_gi_match.group(1)} {nama_gi_match.group(2)}".strip(
            )
        else:
            nama_gi = "Tidak Dikenali"

        # Ambil status open/close/tap position
        status_list = []
        if "open" in baris.lower():
            status_list.append("open")
        if "close" in baris.lower():
            status_list.append("close")

        #  Tap Position jika ada
        tap_position_match = re.search(
            r'Tap Position\s?(\d+)', baris, re.IGNORECASE)
        if tap_position_match:
            status_list.append(f"Tap Position {tap_position_match.group(1)}")

        # Gabungkan semua status ke KET dalam urutan waktu
        ket = "; ".join(status_list) if status_list else "Tidak Ada Status"

        # Kelompokkan data berdasarkan Nama GI
        if nama_gi in grouped_status:
            grouped_status[nama_gi].append(ket)
        else:
            grouped_status[nama_gi] = [ket]

        # Tambahkan hasil filter
        hasil_filter.append(nama_gi)

        # Ambil waktu
        waktu_match = re.search(
            r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}', baris)
        waktu_filter.append(waktu_match.group(
            0) if waktu_match else "01/01/1000 01:01:01")

        # Tambahkan ke daftar KET
        ket_list.append(ket)

    # Tentukan nilai INFO SUKSES berdasarkan isi KET
    for i, gi in enumerate(hasil_filter):
        # Ambil semua status yang pernah muncul
        status_set = set(grouped_status.get(gi, []))
        if all("open" in s for s in status_set) and not any("close" in s for s in status_set):
            info_sukses.append("open")
        elif all("close" in s for s in status_set) and not any("open" in s for s in status_set):
            info_sukses.append("close")
        elif any("open" in s for s in status_set) and any("close" in s for s in status_set):
            info_sukses.append("open/close")
        elif any("Tap Position" in s for s in status_set) and not any("open" in s or "close" in s for s in status_set):
            info_sukses.append("Tidak Diketahui")
        elif any("Tap Position" in s for s in status_set) and all("open" in s or "Tap Position" in s for s in status_set):
            info_sukses.append("open")
        elif any("Tap Position" in s for s in status_set) and all("close" in s or "Tap Position" in s for s in status_set):
            info_sukses.append("close")
        else:
            info_sukses.append("Tidak Ada Status")

    return hasil_filter, waktu_filter, info_sukses, ket_list


def get_temp_filename():
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    return temp_file.name


@app.route('/process_input', methods=['POST'])
def process_input():
    program_choice = request.form.get('program_choice')
    data_choice = request.form.get('data_choice')
    data_lines = request.form.get('raw_data', '').splitlines()

    try:
        if program_choice == 'filter':
            if data_choice == 'gagal':
                hasil_filter, waktu_filter, jumlah_kali_gagal = filter_data_gagal(
                    data_lines)

                # Buat DataFrame untuk Data Gagal
                df_gagal = pd.DataFrame({
                    "NAMA GI": hasil_filter,
                    "WAKTU": waktu_filter,
                    "JUMLAH KALI (GAGAL)": jumlah_kali_gagal
                })

                # Grouping berdasarkan NAMA GI
                df_gagal_grouped = df_gagal.groupby('NAMA GI').agg({
                    'WAKTU': lambda x: '; '.join(set(filter(None, x))),
                    'JUMLAH KALI (GAGAL)': 'first'
                }).reset_index()

                # Simpan file hasil filter
                file_path = get_temp_filename()
                df_gagal_grouped.to_excel(file_path, index=False)
                # Simpan path file untuk download
                file_store['file_path'] = file_path

                logging.debug(
                    f"File Excel untuk data gagal disimpan di: {file_path}")

                return render_template('result_gagal.html', data=df_gagal_grouped.to_dict(orient='records'))

            else:  # Jika data_choice == 'sukses'
                hasil_filter, waktu_filter, info_sukses_filter, ket_filter = filter_data_sukses(
                    data_lines)

                # Buat DataFrame untuk Data Sukses
                df_sukses = pd.DataFrame({
                    "NAMA GI": hasil_filter,
                    "WAKTU": waktu_filter,
                    "INFO SUKSES": info_sukses_filter,
                    "KET": ket_filter
                })

                # Grouping Data Sukses
                df_sukses_grouped = df_sukses.groupby('NAMA GI').agg({
                    'WAKTU': lambda x: '; '.join(set(filter(None, x))),
                    'INFO SUKSES': lambda x: '; '.join(set(filter(None, x))),
                    'KET': lambda x: '; '.join(set(filter(None, x)))
                }).reset_index()

                df_sukses_grouped['JUMLAH KALI (SUKSES)'] = df_sukses.groupby(
                    'NAMA GI').size().reset_index(name='count')['count']

                # Simpan file hasil filter
                file_path = get_temp_filename()
                df_sukses_grouped.to_excel(file_path, index=False)
                # Simpan path file untuk download
                file_store['file_path'] = file_path

                logging.debug(
                    f"File Excel untuk data sukses disimpan di: {file_path}")

                return render_template('result_sukses.html', data=df_sukses_grouped.to_dict(orient='records'))

    except Exception as e:
        logging.error(
            f"Terjadi kesalahan saat memproses data: {str(e)}", exc_info=True)
        return f"Terjadi kesalahan: {str(e)}"
        logging.debug(f"Memasukkan ke rekap: GI={nama_gi}, Waktu={waktu}")


def filter_data_sukses(data):
    hasil_filter, waktu_filter, info_sukses, ket_list = [], [], [], []
    grouped_status = {}

    for baris in data:
        nama_gi_match = re.search(
            r'([A-Z][A-Z0-9\s/-]+?)\s+(CB|BI\d+|TRAFO\s?\d+|TRAF0\s?\d+)',
            baris, re.IGNORECASE
        )
        if nama_gi_match:
            nama_gi = f"{nama_gi_match.group(1)} {nama_gi_match.group(2)}".strip(
            )
        else:
            nama_gi = "Tidak Dikenali"

        # Ambil status open/close/tap position
        status_list = []
        if "open" in baris.lower():
            status_list.append("open")
        if "close" in baris.lower():
            status_list.append("close")

        # Tap Position jika ada
        tap_position_match = re.search(
            r'Tap Position\s?(\d+)', baris, re.IGNORECASE)
        if tap_position_match:
            status_list.append(f"Tap Position {tap_position_match.group(1)}")

        # Gabungkan semua status ke KET dalam urutan waktu
        ket = "; ".join(status_list) if status_list else "Tidak Ada Status"

        # Kelompokkan data berdasarkan Nama GI
        if nama_gi in grouped_status:
            grouped_status[nama_gi].append(ket)
        else:
            grouped_status[nama_gi] = [ket]

        # Tambahkan hasil filter
        hasil_filter.append(nama_gi)

        # Ambil waktu
        waktu_match = re.search(
            r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}(?:,\d+)?', baris)
        waktu_filter.append(waktu_match.group(0) if waktu_match else "")

        # Tambahkan ke daftar KET
        ket_list.append(ket)

    # Tentukan nilai INFO SUKSES berdasarkan isi KET
    for i, gi in enumerate(hasil_filter):
        # Ambil semua status yang pernah muncul
        status_set = set(grouped_status.get(gi, []))
        if all("open" in s for s in status_set) and not any("close" in s for s in status_set):
            info_sukses.append("open")
        elif all("close" in s for s in status_set) and not any("open" in s for s in status_set):
            info_sukses.append("close")
        elif any("open" in s for s in status_set) and any("close" in s for s in status_set):
            info_sukses.append("open/close")
        elif any("Tap Position" in s for s in status_set) and not any("open" in s or "close" in s for s in status_set):
            info_sukses.append("Tidak Diketahui")
        elif any("Tap Position" in s for s in status_set) and all("open" in s or "Tap Position" in s for s in status_set):
            info_sukses.append("open")
        elif any("Tap Position" in s for s in status_set) and all("close" in s or "Tap Position" in s for s in status_set):
            info_sukses.append("close")
        else:
            info_sukses.append("Tidak Ada Status")

    return hasil_filter, waktu_filter, info_sukses, ket_list

# GET rekap sukses
@app.route('/rekap-sukses', methods=['GET'])
def getRekapSukses():
    # Periksa dan buat tabel jika belum ada
    cur = mysql.connection.cursor()
    cur.execute("""
                CREATE TABLE IF NOT EXISTS rekap_data_sukses(
                    unique_waktu VARCHAR(255) NOT NULL,
                    unique_gi VARCHAR(255) NOT NULL,
                    info_sukses VARCHAR(255) NOT NULL, 
                    ket_list VARCHAR(255) NOT NULL,
                    bulan VARCHAR(255) NOT NULL,
                    tahun VARCHAR(255) NOT NULL,
                    PRIMARY KEY( unique_gi,tahun)
                )
            """)
    mysql.connection.commit()
    cur.close()

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT * FROM rekap_data_sukses ORDER BY tahun DESC, bulan DESC, unique_waktu DESC")

    data = cur.fetchall()
    cur.close()

    if request.args.get("download") == "excel":
        try:
            # Buat DataFrame dari hasil query
            df = pd.DataFrame(
                data, columns=['NAMA GI', 'INFO', 'KET', 'WAKTU', 'BULAN', 'TAHUN'])

            # Simpan DataFrame sebagai file Excel sementara
            file_path = get_temp_filename()
            df.to_excel(file_path, index=False)

            logging.debug(f"File Excel telah dibuat: {file_path}")
            return send_file(file_path, as_attachment=True, download_name="Rekap_Data_Sukses.xlsx")

        except Exception as e:
            logging.error(
                f"Terjadi kesalahan saat mengunduh Excel: {str(e)}", exc_info=True)
            return f"Terjadi kesalahan saat mengunduh file Excel: {str(e)}", 500
    return render_template('rekap-sukses.html', data=data, data_type="sukses")


# GET rekap gagal
@app.route('/rekap-gagal', methods=['GET'])
def getRekapGagal():
    # Periksa dan buat tabel jika belum ada
    cur = mysql.connection.cursor()
    cur.execute("""
                CREATE TABLE IF NOT EXISTS rekap_data_gagal(
                    unique_waktu VARCHAR(255) NOT NULL,
                    unique_gi VARCHAR(255) NOT NULL,
                    bulan VARCHAR(255) NOT NULL,
                    tahun VARCHAR(255) NOT NULL,
                    PRIMARY KEY( unique_gi,tahun)
                )
            """)
    mysql.connection.commit()
    cur.close()

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT * FROM rekap_data_gagal ORDER BY tahun DESC, bulan DESC, unique_waktu DESC")

    data = cur.fetchall()
    cur.close()

    if request.args.get("download") == "excel":
        try:
            # Buat DataFrame dari hasil query
            df = pd.DataFrame(
                data, columns=['NAMA GI',  'WAKTU', 'BULAN', 'TAHUN'])

            # Simpan DataFrame sebagai file Excel sementara
            file_path = get_temp_filename()
            df.to_excel(file_path, index=False)

            logging.debug(f"File Excel telah dibuat: {file_path}")
            return send_file(file_path, as_attachment=True, download_name="Rekap_Data_Gagal.xlsx")

        except Exception as e:
            logging.error(
                f"Terjadi kesalahan saat mengunduh Excel: {str(e)}", exc_info=True)
            return f"Terjadi kesalahan saat mengunduh file Excel: {str(e)}", 500
    return render_template('rekap-gagal.html', data=data, data_type="gagal")


# POST rekap sukses
@app.route('/rekap-sukses/add', methods=['POST'])
def addRekapSukses():
    try:
        # 🔹 Ambil data dari form
        bulan = request.form.get('bulan_choice')
        raw_data = request.form.get('raw_data', '').splitlines()

        # 🔹 Proses data
        hasil_filter, waktu_filter, info_sukses, ket_list = filter_data_sukses_rekap(
            raw_data)

        # 🔹 Format ulang waktu
        waktu_filter = [datetime.strptime(
            w, "%d/%m/%Y %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S") for w in waktu_filter]
        tahun_filter = [datetime.strptime(
            w, "%Y-%m-%d %H:%M:%S").strftime("%Y") for w in waktu_filter]

        # 🔹 Simpan ke database
        cur = mysql.connection.cursor()
        cur.execute("""
    CREATE TABLE IF NOT EXISTS rekap_data_sukses(
        unique_waktu VARCHAR(255) NOT NULL,
        unique_gi VARCHAR(255) NOT NULL,
        info_sukses VARCHAR(255) NOT NULL, 
        ket_list VARCHAR(255) NOT NULL,
        bulan VARCHAR(255) NOT NULL,
        tahun VARCHAR(255) NOT NULL,
        jumlah_unique_waktu INT NOT NULL DEFAULT 1,
        PRIMARY KEY(unique_gi, tahun)
    )
""")
        mysql.connection.commit()
        for gi, waktu, tahun, info, ket in zip(hasil_filter, waktu_filter, tahun_filter, info_sukses, ket_list):
            cur.execute("""
        INSERT INTO rekap_data_sukses (unique_waktu, unique_gi, info_sukses, ket_list, bulan, tahun, jumlah_unique_waktu)
        VALUES (%s, %s, %s, %s, %s, %s, 1)
        ON DUPLICATE KEY UPDATE 
            unique_waktu = CASE 
                WHEN LOCATE(%s, unique_waktu) = 0 THEN CONCAT_WS(', ', unique_waktu, %s) 
                ELSE unique_waktu 
            END,
            bulan = CASE 
                WHEN LOCATE(%s, bulan) = 0 THEN CONCAT_WS(', ', bulan, %s) 
                ELSE bulan 
            END,
            jumlah_unique_waktu = 
                1 + LENGTH(unique_waktu) - LENGTH(REPLACE(unique_waktu, ',', ''))
    """, (waktu, gi, info, ket, bulan, tahun, waktu, waktu, bulan, bulan))

        mysql.connection.commit()
        cur.close()

        return redirect('/rekap-sukses')

    except Exception as e:
        logging.error(
            f"Terjadi kesalahan saat menyimpan ke database: {str(e)}", exc_info=True)
        return f"Terjadi kesalahan saat menyimpan ke database: {str(e)}", 500
# POST rekap gagal


@app.route('/rekap-gagal/add', methods=['POST'])
def addRekapGagal():
    try:
        # Ambil data dari form
        bulan = request.form.get('bulan_choice')
        raw_data = request.form.get('raw_data', '').splitlines()

        # Proses data
        hasil_filter, waktu_filter,  = filter_data_gagal_rekap(
            raw_data)

        # Format ulang waktu
        waktu_filter = [datetime.strptime(
            w, "%d/%m/%Y %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S") for w in waktu_filter]
        tahun_filter = [datetime.strptime(
            w, "%Y-%m-%d %H:%M:%S").strftime("%Y") for w in waktu_filter]

        # Simpan ke database
        cur = mysql.connection.cursor()
        cur.execute("""
    CREATE TABLE IF NOT EXISTS rekap_data_gagal(
        unique_waktu VARCHAR(255) NOT NULL,
        unique_gi VARCHAR(255) NOT NULL,
        bulan VARCHAR(255) NOT NULL,
        tahun VARCHAR(255) NOT NULL,
        jumlah_unique_waktu INT NOT NULL DEFAULT 1,
        PRIMARY KEY(unique_gi, tahun)
    )
""")
        mysql.connection.commit()
        for gi, waktu, tahun in zip(hasil_filter, waktu_filter, tahun_filter):
            cur.execute("""
        INSERT INTO rekap_data_gagal (unique_waktu, unique_gi, bulan, tahun, jumlah_unique_waktu)
        VALUES (%s, %s, %s, %s, 1)
        ON DUPLICATE KEY UPDATE 
            unique_waktu = CASE 
                WHEN LOCATE(%s, unique_waktu) = 0 THEN CONCAT_WS(', ', unique_waktu, %s) 
                ELSE unique_waktu 
            END,
            bulan = CASE 
                WHEN LOCATE(%s, bulan) = 0 THEN CONCAT_WS(', ', bulan, %s) 
                ELSE bulan 
            END,
            jumlah_unique_waktu = 
                1 + LENGTH(unique_waktu) - LENGTH(REPLACE(unique_waktu, ',', ''))
    """, (waktu, gi, bulan, tahun, waktu, waktu, bulan, bulan))

        mysql.connection.commit()
        cur.close()

        return redirect('/rekap-gagal')

    except Exception as e:
        logging.error(
            f"Terjadi kesalahan saat menyimpan ke database: {str(e)}", exc_info=True)
        return f"Terjadi kesalahan saat menyimpan ke database: {str(e)}", 500


# DELETE rekap sukses
@app.route('/rekap-sukses/delete', methods=['POST'])
def deleteSukses():
    try:
        unique_waktu = request.form.get('unique_waktu')
        unique_gi = request.form.get('unique_gi')

        if not unique_waktu or not unique_gi:
            return "Error: Data tidak lengkap untuk dihapus!", 400

        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM rekap_data_sukses WHERE unique_waktu = %s AND unique_gi = %s",
                    (unique_waktu, unique_gi))
        mysql.connection.commit()
        cur.close()

        return redirect('/rekap-sukses')

    except Exception as e:
        logging.error(
            f"Terjadi kesalahan saat menghapus satu data: {str(e)}", exc_info=True)
        return f"Terjadi kesalahan saat menghapus data: {str(e)}", 500
# DELETE rekap gagal


@app.route('/rekap-gagal/delete', methods=['POST'])
def deleteGagal():
    try:
        unique_waktu = request.form.get('unique_waktu')
        unique_gi = request.form.get('unique_gi')

        if not unique_waktu or not unique_gi:
            return "Error: Data tidak lengkap untuk dihapus!", 400

        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM rekap_data_gagal WHERE unique_waktu = %s AND unique_gi = %s",
                    (unique_waktu, unique_gi))
        mysql.connection.commit()
        cur.close()

        return redirect('/rekap-gagal')

    except Exception as e:
        logging.error(
            f"Terjadi kesalahan saat menghapus satu data: {str(e)}", exc_info=True)
        return f"Terjadi kesalahan saat menghapus data: {str(e)}", 500


@app.route('/rekap-gagal/delete-all', methods=['POST'])
def deleteAllGagal():
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM rekap_data_gagal")
        mysql.connection.commit()
        cur.close()

        return redirect('/rekap-gagal')

    except Exception as e:
        logging.error(
            f"Terjadi kesalahan saat menghapus semua data: {str(e)}", exc_info=True)
        return f"Terjadi kesalahan saat menghapus data: {str(e)}", 500


@app.route('/rekap-sukses/delete-all', methods=['POST'])
def deleteAllSukses():
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM rekap_data_sukses")
        mysql.connection.commit()
        cur.close()

        return redirect('/rekap-sukses')

    except Exception as e:
        logging.error(
            f"Terjadi kesalahan saat menghapus semua data: {str(e)}", exc_info=True)
        return f"Terjadi kesalahan saat menghapus data: {str(e)}", 500


@app.route('/rekap-sukses/delete-selected', methods=['POST'])
def deleteSelectedSukses():
    try:
        # Ambil data yang dikirim (bisa dari form atau JSON)
        selected_data = request.form.getlist(
            'selected_items') or request.json.get('selected_items', [])

        selected_data = selected_data[0].split(',')

        # Debug: Cek apakah data diterima dengan benar
        logging.debug(f"Data yang diterima untuk dihapus: {selected_data}")

        if not selected_data:
            return "Error: Tidak ada data yang dipilih untuk dihapus!", 400

        cur = mysql.connection.cursor()
        gi = []
        waktu = []
        for item in selected_data:

            try:
                if "|" in item:
                    unique_gi, unique_waktu = item.rsplit("|", 1)
                    unique_gi = unique_gi.strip()
                    unique_waktu = unique_waktu.strip()
                    gi.append(unique_gi)
                    waktu.append(unique_waktu)

                    cur.execute(
                        "DELETE FROM rekap_data_sukses WHERE unique_gi = %s AND unique_waktu = %s",
                        (unique_gi, unique_waktu)
                    )
                else:
                    logging.warning(f"Format item tidak valid: {item}")

            except Exception as e:
                logging.error(
                    f"Kesalahan saat menghapus item {item}: {str(e)}", exc_info=True)

        mysql.connection.commit()
        cur.close()

        logging.debug(
            f"{len(selected_data)} data telah dihapus dari rekap_data_sukses.")
        return redirect('/rekap-sukses')

    except Exception as e:
        logging.error(
            f"Terjadi kesalahan saat menghapus banyak data: {str(e)}", exc_info=True)
        return f"Terjadi kesalahan saat menghapus banyak data: {str(e)}", 500


@app.route('/rekap-gagal/delete-selected', methods=['POST'])
def deleteSelectedGagal():
    try:
        # Ambil data yang dikirim (bisa dari form atau JSON)
        selected_data = request.form.getlist(
            'selected_items') or request.json.get('selected_items', [])

        selected_data = selected_data[0].split(',')

        # Debug: Cek apakah data diterima dengan benar
        logging.debug(f"Data yang diterima untuk dihapus: {selected_data}")

        if not selected_data:
            return "Error: Tidak ada data yang dipilih untuk dihapus!", 400

        cur = mysql.connection.cursor()
        gi = []
        waktu = []
        for item in selected_data:

            try:
                if "|" in item:
                    unique_gi, unique_waktu = item.rsplit("|", 1)
                    unique_gi = unique_gi.strip()
                    unique_waktu = unique_waktu.strip()
                    gi.append(unique_gi)
                    waktu.append(unique_waktu)

                    cur.execute(
                        "DELETE FROM rekap_data_gagal WHERE unique_gi = %s AND unique_waktu = %s",
                        (unique_gi, unique_waktu)
                    )
                else:
                    logging.warning(f"Format item tidak valid: {item}")

            except Exception as e:
                logging.error(
                    f"Kesalahan saat menghapus item {item}: {str(e)}", exc_info=True)

        mysql.connection.commit()
        cur.close()

        logging.debug(
            f"{len(selected_data)} data telah dihapus dari rekap_data_gagal.")
        return redirect('/rekap-gagal')

    except Exception as e:
        logging.error(
            f"Terjadi kesalahan saat menghapus banyak data: {str(e)}", exc_info=True)
        return f"Terjadi kesalahan saat menghapus banyak data: {str(e)}", 500

# Daftar keyword
keywords = [
    "ALTAPRIMA", "ASIA", "AWAR", "BABAT", "BALONGBENDO", "BAMBE", "BANARAN", "BANGIL", 
    "BANGKALAN", "BANGUN", "BANYUWANGI", "BARATA", "BLIMBING", "BLITAR", "BOJONEGORO", 
    "BONDOWOSO", "BUDURAN", "BULU", "BUMI", "BUNGAN", "CARUBAN", "CERME", "CHEIL", 
    "DARMO", "DOLOPO", "DRIYOREJO", "GAMPINGAN", "GARAM", "GEMBONG", "GENTENG", "GILI", 
    "GIRINGAN", "GOLANG", "GONDANG", "GRATI", "GRESIK", "GULUK", "GUNUNG", "HANIL", 
    "HOLCIM", "IJEN", "IMASCO", "INDO", "ISPAT", "JATIGEDONG", "JATIM", "JAYA", "JEDANG", 
    "JEMBER", "JOMBANG", "KALISARI", "KARANG", "KASIH", "KEBONAGUNG", "KEDINDING", "KEDIRI", 
    "KENJERAN", "KEREK", "KERTOSONO", "KIMIA", "KIS", "KRAKSAAN", "KREM", "KUPANG", "LAMONGAN", 
    "LAWANG", "LUMAJANG", "MAGETAN", "MANISREJO", "MANYAR", "MASPION", "BUS", "MENDALAN", 
    "MIWON", "MLIWANG", "MOJO", "MRANGGEN", "NGAGEL", "NGANJUK", "NGAWI", "NGEBEL", "NGIMBANG", 
    "NGORO", "NOMOTO", "PACIRAN", "SUTAMI", "PACITAN", "PAITON", "PAKIS", "PAMENGKASAN", "PANDAAN", 
    "PARE", "PERAK", "PETROKIMIA", "PIER", "PLOSO", "DIAMETER", "PLTP", "POLEHAN", "PONOROGO", 
    "PORONG", "PROBOLINGGO", "PUGER", "PURWOSARI", "RUNGKUT", "SAMBIKEREP", "SAMPANG", "SAWAHAN", 
    "SEDATI", "SEGOROMADU", "SEKARPUTIH", "SELOREJO", "SEMEN", "TRAF", "SENGGURUH", "SENGKALING", 
    "SIDOA", "SIMAN", "SIMPANG", "SITUBONDO", "STEEL", "SUKOLILO", "SUKOREJO", "SUMENEP", 
    "SURABAYA", "IBT", "SURYA", "TANDES", "TANGGUL", "TARIK", "TJIWI", "TRENGGALEK", "TUBAN", 
    "TULUNG", "TUREN", "UJUNG", "UNDAAN", "WARU", "WILMAR", "WLINGI", "WONOKROMO", "TRF"
]

# Mapping khusus IBT ke TRAF/TRF
keyword_mapping = {
    "IBT": ["TRAF", "TRF"],
    "TRAF": ["IBT"],
    "TRF": ["IBT"]
}

# Pola regex untuk mendeteksi format waktu
time_pattern = re.compile(r"\d{2}:\d{2}-\d{2}:\d{2} WIB")

@app.route('/program3', methods=['POST'])
def program3():
    program_choice = request.form.get('program_choice')
    data_choice = request.form.get('data_choice')
    data_lines = request.form.get('raw_data', '').splitlines()

    print("Data Input (Sebelum Diproses):", data_lines)  # Debugging

    try:
        # Ambil data dari tabel rekap_data_gagal
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM rekap_data_gagal ORDER BY tahun DESC, bulan DESC, unique_waktu DESC")
        rekap_data = cur.fetchall()
        cur.close()

        # Gabungkan kembali data yang terpisah menjadi satu baris
        merged_lines = []
        temp_line = ""

        for line in data_lines:
            line = line.strip().replace('"', '')  # Hapus tanda kutip

            if "\t" in line:
                if temp_line:
                    merged_lines.append(temp_line)
                temp_line = line
            else:
                temp_line += " " + line.strip()

        if temp_line:
            merged_lines.append(temp_line)

        print("Merged Input:", merged_lines)

        # Proses data inputan
        result_data = []
        processed_rekap_names = set()

        for line in merged_lines:
            print("\n=== Processing New Line ===")
            print("Processing Line:", line)

            parts = line.split("\t")
            print("Jumlah Elemen dalam Parts:", len(parts), "->", parts)

            if len(parts) >= 4:
                start_date = parts[0].strip()
                end_date = parts[1].strip()
                location = parts[2].strip()
                equipment_and_info = parts[3].strip()

                time_match = time_pattern.search(equipment_and_info)

                if time_match:
                    time_range = time_match.group()
                    equipment = equipment_and_info[:time_match.start()].strip()
                    keterangan = equipment_and_info[time_match.end():].strip()
                else:
                    equipment = equipment_and_info
                    time_range = ""
                    keterangan = ""

                # Tangani keterangan jika dalam tanda kurung
                keterangan = re.sub(r'^\((.*?)\)$', r'\1', keterangan).strip()

                # Pastikan keterangan mencakup waktu dan info tambahan
                if not keterangan:
                    keterangan = time_range
                else:
                    keterangan = f"{time_range} {keterangan}".strip()

                # Pembersihan teks peralatan
                equipment = equipment.replace("#", " ")  # Hapus simbol #

                number_keywords = ["500", "150", "70", "20"]

                # Cari keyword yang cocok dari daftar lokasi dan angka
                location_keywords = [kw for kw in keywords if kw in location] + [num for num in number_keywords if num in location]
                equipment_keywords = [kw for kw in keywords if kw in equipment] + [num for num in number_keywords if num in equipment]

                # Gunakan mapping jika ada
                for kw in list(equipment_keywords):
                    if kw in keyword_mapping:
                        equipment_keywords.extend(keyword_mapping[kw])

                print(f"Processed Input Location: {location}")
                print(f"Processed Input Equipment: {equipment}")
                print(f"Processed Location Keywords: {location_keywords}")
                print(f"Processed Equipment Keywords: {equipment_keywords}")

                # Pencocokan untuk Kata Pertama di Data Rekap
                matched_rekap_data = []
                for rekap_entry in rekap_data:
                    rekap_string = rekap_entry[1]

                    # Ambil kata pertama dari data rekap
                    first_word_rekap = rekap_string.split()[0]

                    # Ambil semua keyword yang cocok dalam rekap data
                    rekap_keywords = [kw for kw in keywords if kw in rekap_string] + [num for num in number_keywords if num in rekap_string]

                    # Gunakan mapping keyword
                    for kw in list(rekap_keywords):
                        if kw in keyword_mapping:
                            rekap_keywords.extend(keyword_mapping[kw])

                    print(f"Processed Rekap: {rekap_string}")
                    print(f"Processed Rekap Keywords: {rekap_keywords}")

                    # Cek apakah ada minimal 1 keyword dari lokasi yang cocok dengan kata pertama rekap
                    first_word_match = any(kw in first_word_rekap for kw in location_keywords)

                    # Cek apakah ada minimal 1 keyword yang cocok di peralatan
                    equipment_match = any(kw in rekap_keywords for kw in equipment_keywords)

                    # Cek apakah ada minimal 2 angka yang sama (di lokasi atau peralatan)
                    matched_numbers = set(rekap_keywords) & set(number_keywords)
                    number_match = len(matched_numbers) >= 2

                    # Syarat Pencocokan
                    if first_word_match and equipment_match and number_match:
                        if rekap_entry[1] not in processed_rekap_names:
                            matched_rekap_data.append(rekap_entry)
                            processed_rekap_names.add(rekap_entry[1])

                # Gabungkan hasil yang cocok dengan data input di baris yang sama
                for rekap_entry in matched_rekap_data:
                    final_entry = {
                        'rekap': rekap_entry[1],
                        'location': location,
                        'start_date': start_date,
                        'end_date': end_date,
                        'equipment': equipment.strip(),
                        'keterangan': keterangan
                    }
                    result_data.append(final_entry)

        print("\n=== Final Result Data ===")
        print(result_data)

        return render_template('result_program3.html', data=result_data)

    except Exception as e:
        logging.error(f"Error saat memproses program3: {str(e)}", exc_info=True)
        return f"Terjadi kesalahan saat memproses program3: {str(e)}", 500

def process_program3_data(data):
    # Logika pengolahan data untuk program3
    processed_data = []
    for line in data:
        # Proses baris data untuk mendapatkan lokasi, peralatan, dan waktu
        parts = line.split("\t")  # Misalnya, data dipisahkan tab
        if len(parts) >= 4:
            location = parts[2]
            equipment = parts[3]
            time = parts[0]  # Atau sesuaikan dengan bagian yang tepat
            processed_data.append({
                'location': location,
                'equipment': equipment,
                'time': time
            })
    return processed_data

if __name__ == '__main__':
    app.run(debug=True)
