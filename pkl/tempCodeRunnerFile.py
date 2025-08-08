 cur.execute("""INSERT INTO rekap_data_sukses(unique_waktu, unique_gi,info_sukses,ket_list, bulan, tahun)
            VALUES ( % s, % s, % s, % s, % s, % s)
            ON DUPLICATE KEY UPDATE unique_waktu=VALUES(unique_waktu)
            """,
                        (waktu, gi, info, ket, bulan, tahun)
                        )