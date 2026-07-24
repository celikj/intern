# intern-watch

Staj ilanı erken-uyarı sistemi. 6 kaynağı tarar, sadece **yeni** ilanları telefona push bildirim olarak gönderir. FAANG+ ilanlar ayrı ve yüksek öncelikli kanaldan gider.

GitHub Actions üzerinde çalışır — bilgisayarın kapalıyken de bildirim alırsın.

## Kaynaklar

| Kaynak | Kapsam |
|---|---|
| zshah101 Internship Engine (JSON API) | 3.870 şirketin ATS'i, saatlik |
| speedyapply/2027-SWE-College-Jobs | ABD, FAANG+/Quant/Other bölümlü |
| speedyapply INTERN_INTL.md | Uluslararası (Avrupa dahil) |
| speedyapply/2027-AI-College-Jobs | AI/ML, uluslararası |
| vanshb03/Summer2027-Internships | ABD/Kanada topluluk listesi |
| LorenzoLaCorte/european-tech-internships | Avrupa |

Ayrıca `SimplifyJobs/Summer2027-Internships` açıldığı an haber verir.

---

## Kurulum

### 1. Repo oluştur

GitHub'da yeni repo aç (**Public** öner — aşağıdaki nota bak), bu dosyaları içine koy:

```
intern_watch.py
README.md
.github/workflows/watch.yml
```

```bash
git init
git add .
git commit -m "intern-watch kurulum"
git branch -M main
git remote add origin https://github.com/KULLANICI_ADIN/intern-watch.git
git push -u origin main
```

> **Public mi private mi?** Public repo'larda zamanlanmış workflow'lar sınırsız ve ücretsiz.
> Private repo aylık dakika kotandan yer (ücretsiz hesapta 2.000 dk/ay — 15 dk'da bir çalışma bunu zorlar).
> Bildirim topic'lerin zaten Secrets içinde saklanır, repo public olsa da görünmez.

### 2. Telefonu hazırla

1. **ntfy** uygulamasını kur (Android: Play Store / F-Droid, iOS: App Store)
2. İki topic'e abone ol — isimleri **uzun ve tahmin edilemez** seç
   (ntfy.sh'de topic adını bilen herkes mesajları okuyabilir):
   - `intern-genel-<rastgele>`
   - `intern-faang-<rastgele>`
3. FAANG topic'ine uygulamadan özel zil sesi / yüksek öncelik ata

### 3. Secrets ekle

Repo → **Settings → Secrets and variables → Actions → Secrets → New repository secret**

| Secret | Değer |
|---|---|
| `NTFY_TOPIC` | genel topic adın |
| `NTFY_TOPIC_FAANG` | FAANG topic adın |

E-posta da istersen (opsiyonel): `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `TO_EMAIL`.
Gmail için normal şifre değil [Uygulama Şifresi](https://myaccount.google.com/apppasswords) gerekir.

### 4. Filtreler (opsiyonel)

Aynı sayfada **Variables** sekmesi → New repository variable

| Variable | Varsayılan | Açıklama |
|---|---|---|
| `SEASONS` | `2027` | Sezon filtresi |
| `REGIONS` | `all` | `all` veya `eu` (sadece Avrupa/Türkiye) |
| `CATEGORIES` | *(boş)* | `Software`, `Data & ML/AI`, `AI/ML`, `Quant`, `Hardware`, `Security` |
| `EXCLUDE_SPONSORSHIP` | `no-sponsorship,citizens-only` | Sana kapalı olanları ele |
| `TITLE_EXCLUDE` | `phd,ph.d,masters,master's,mba` | Başlıkta geçerse ele |
| `NTFY_MAX_PER_RUN` | `12` | Bu sayıyı aşarsa tek özet bildirim gönderir |

### 5. İLK ÇALIŞTIRMA — önce seed!

⚠️ Bunu atlarsan mevcut ~800 ilanın hepsi "yeni" sayılır.

Repo → **Actions** → `intern-watch` → **Run workflow** → mode: **`seed`** → Run

Bu, şu anki ilanları "görüldü" işaretler ve `state/state.json` olarak commit eder. Bildirim göndermez.

### 6. Bitti

Bundan sonra 15 dakikada bir otomatik çalışır. Sadece gerçekten **yeni** açılan ilanlar bildirim olarak gelir.

---

## Kullanım notları

**Elle çalıştırma:** Actions → Run workflow → mode seç
- `normal` — standart (varsayılan)
- `faang-only` — sadece FAANG+ bildir
- `dry-run` — bildirim atmadan logda göster
- `seed` — mevcutları görüldü işaretle

**Log görme:** Actions → son çalışma → `Taramayı çalıştır` adımı.
Kaç ilan bulundu, kaçı yeni, kaçı FAANG+ orada yazar.

**Filtre değiştirme:** Variables'ı güncelle, kod değişikliği gerekmez.

---

## Bilinmesi gerekenler

- **Cron gecikmesi:** GitHub zamanlanmış işleri yoğunlukta geciktirebilir; `*/15` yazsan da bazen 20–30 dk olabilir. Garanti dakika hassasiyeti isteyen biri için bu yeterli değil, ama "ilanı gün içinde yakala" için fazlasıyla yeterli.
- **60 gün kuralı:** Repo'da 60 gün hiç aktivite olmazsa GitHub zamanlanmış workflow'ları devre dışı bırakır ve mail atar. Bu sistem her yeni ilanda state commit'lediği için normalde tetiklenmez; yine de o maili görürsen Actions'tan tek tıkla yeniden aç.
- **Yeni sezon:** `SimplifyJobs/Summer2027-Internships` açıldığında bildirim gelir. Kaynak listesine eklemek için `intern_watch.py` içindeki `SOURCES`'a bir satır eklemen yeterli.
- **Vize gerçeği:** Kaynakların çoğu ABD odaklı. ABD stajları genelde ABD'de kayıtlı öğrenci ister (F-1/CPT). Avrupa'daysan `REGIONS=eu` daha isabetli sonuç verir.
