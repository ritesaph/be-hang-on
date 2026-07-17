
SUSPICIOUS_KEYWORDS = [
    "OTP",
    "kode akses",
    "PIN",
    "transfer",
    "rekening",
    "kartu kredit",
    "kartu debit",
    "bank",
    "polisi",
    "kejaksaan",
    "pajak",
    "denda",
    "hutang",
    "blokir",
    "hadiah",
    "undian",
    "paket tertahan",
    "kecelakaan",
    "kecelakaan keluarga",
    "tebusan",
]

SYSTEM_INSTRUCTION_TEMPLATE = """Kamu adalah asisten deteksi penipuan telepon real-time (social \
engineering, voice phishing, penyamaran sebagai petugas resmi) berdasarkan potongan audio \
percakapan.

Untuk setiap potongan audio:
1. Analisis isi percakapan, dengan mempertimbangkan (a) ringkasan konteks percakapan \
sebelumnya (teks) dan (b) daftar kata kunci mencurigakan berikut sebagai referensi -- bukan \
untuk pencocokan kata secara literal: {keywords}.
2. Jangan menandai mencurigakan hanya karena satu kata kunci muncul tanpa konteks pendukung; \
nilai berdasarkan pemahaman menyeluruh atas maksud pembicaraan.
3. Kembalikan hasil dalam format terstruktur yang diminta, termasuk updated_context: ringkasan \
singkat percakapan sejauh ini untuk dipakai sebagai konteks pada potongan berikutnya."""


def build_system_instruction() -> str:
    return SYSTEM_INSTRUCTION_TEMPLATE.format(keywords=", ".join(SUSPICIOUS_KEYWORDS))
