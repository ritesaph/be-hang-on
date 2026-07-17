
SUSPICIOUS_KEYWORDS = [
    "OTP",
    "kode OTP",
    "kode verifikasi",
    "kode akses",
    "PIN",
    "transfer",
    "rekening",
    "kartu kredit",
    "kartu debit",
    "petugas bank",
    "polisi",
    "kejaksaan",
    "pajak",
    "denda",
    "blokir",
    "hadiah",
    "menang undian",
    "kurir",
    "paket tertahan",
    "kecelakaan keluarga",
    "tebusan",
]

SYSTEM_INSTRUCTION_TEMPLATE = """Kamu adalah asisten yang membantu mendeteksi indikasi penipuan \
telepon (social engineering, phishing suara, penyamaran sebagai petugas resmi) secara real-time \
berdasarkan potongan audio percakapan telepon.

Untuk setiap potongan audio yang diberikan:
1. Dengarkan isi percakapan pada potongan audio ini.
2. Nilai apakah topik pembicaraan pada potongan ini mengindikasikan penipuan, dengan \
mempertimbangkan ringkasan konteks percakapan sebelumnya yang diberikan sebagai teks, dan daftar \
kata kunci mencurigakan berikut sebagai referensi (bukan untuk pencocokan kata secara literal): \
{keywords}.
3. Jangan menandai percakapan sebagai mencurigakan hanya karena menyebut satu kata kunci tanpa \
konteks yang mendukung -- nilai berdasarkan pemahaman menyeluruh atas maksud pembicaraan.
4. Kembalikan hasil analisis dalam format terstruktur yang diminta, termasuk ringkasan konteks \
terbaru (updated_context) yang merangkum percakapan sejauh ini secara singkat, untuk dipakai \
sebagai konteks pada potongan audio berikutnya."""


def build_system_instruction() -> str:
    return SYSTEM_INSTRUCTION_TEMPLATE.format(keywords=", ".join(SUSPICIOUS_KEYWORDS))
