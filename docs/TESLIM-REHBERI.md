# Atinen Case Study — Teslim Paketi

**HEC-RAS Q50 Maksimum Derinlik Otomasyonu**
Hazırlayan: Emirhan Fırtına · 29 Ağustos 2026

---

## Nereden başlamalı

**[`RAPOR.pdf`](RAPOR.pdf)** — teknik rapor. Aynı içerik
[`RAPOR.html`](RAPOR.html) olarak da pakette. Q50'nin nasıl belirlendiği, HEC-RAS
ile nasıl etkileşim kurulduğu, çıktının nasıl doğrulandığı ve hataların nasıl
yönetildiği burada anlatılıyor; belgenin 6. ve 7. maddelerinin karşılığıdır.

---

## Teslim kalemleri

Belgenin 5. maddesindeki liste ve bu paketteki karşılıkları:

| Teslim kalemi | Konum |
| --- | --- |
| **Kaynak kod** | `uygulama/main.py`, `uygulama/q50depth/` (14 modül), `uygulama/tools/` |
| **Çıktı** | `uygulama/OUTPUT/q50_depth.tif` |
| **Bağımlılıklar** | `uygulama/requirements.txt`, `requirements-windows.txt`, `requirements-dev.txt` |
| **README** | `uygulama/README.md` |
| **Çalışma kaydı** | `uygulama/OUTPUT/run.log`, `uygulama/docs/ornek-calisma-kaydi.txt` |
| **Teknik açıklama** (madde 6) | `RAPOR.pdf` (ve `RAPOR.html`) |
| **Yapay zekâ beyanı** (madde 7) | `RAPOR.pdf` bölüm 10, `uygulama/docs/AI-KULLANIMI.md` |

### Ek belgeler

| Dosya | İçerik |
| --- | --- |
| `q50_depth_onizleme.png` | Çıktının görüntüsü ve derinlik dağılımı |
| `referans_karsilastirma.png` | Toplantıda gösterilen referans çıktı ile karşılaştırma |
| `uygulama/docs/VERI-DENETIMI.md` | Teslim edilen projedeki sekiz tutarsızlığın ayrıntılı analizi |
| `uygulama/docs/veri-denetimi-ciktisi.txt` | Denetim aracının ham çıktısı |
| `uygulama/docs/WINDOWS-DOGRULAMA.md` | Windows'ta adım adım sağlama listesi |

---

## Çalıştırma

Python 3.13 veya 3.14. Windows'ta ayrıca HEC-RAS 6.6.

```bat
cd uygulama
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements-windows.txt
```

**Haritayı üretmek** (projenin hesaplanmış sonuçlarından):

```bat
python main.py --project <CASE_DATA yolu> --use-existing-results
```

**HEC-RAS'ı da çalıştırarak:**

```bat
python main.py --project <CASE_DATA yolu> ^
  --ras-dir "C:\Program Files (x86)\HEC\HEC-RAS\6.6"
```

**Testler** (`pip install -r requirements-dev.txt` sonrası):

```bat
python -m pytest tests -q
```

**Veri denetimi:**

```bat
python tools\audit_project.py --project <CASE_DATA yolu>
```

Ayrıntılı kullanım ve tüm seçenekler: `uygulama/README.md`.

---

## Bilinmesi gereken üç şey

**0. Çıktı referansla örtüşüyor.** Toplantıda gösterilen görüntüdeki pürüzsüz
şerit su değil, projenin 1D nehir geometrisidir; taşkını temsil eden koyu
lekeler ise üretilen haritadaki ıslak alanlarla aynı konumdadır. Karşılaştırma
raporun 6. bölümünde ve `referans_karsilastirma.png` dosyasında.

**1. Orijinal veriye yazılmıyor.** Uygulama proje ağacını bir çalışma dizinine
kopyalar ve hesabı orada yapar. Bu, her çalıştırmada kaynak klasörün parmak izi
çıkarılıp karşılaştırılarak kanıtlanır (`--integrity full` ile SHA-256).

**2. HEC-RAS motoru teslim edilen veriyle çöküyor.** Uygulama planı çalıştırıyor,
HEC-RAS geometriyi işliyor, ardından unsteady motoru `access violation` ile
duruyor. Aynı hata proje HEC-RAS arayüzünde elle açıldığında da oluşuyor. Yedi
farklı yapılandırma denenerek nedenler elendi; ayrıntı raporun 8. bölümünde.

Bu nedenle paketteki çıktı, projenin **kendi hesaplanmış sonuçlarından**
üretilmiştir. Hazır bir raster kopyalanmamıştır — harita her çalıştırmada
HEC-RAS'ın sonuç dosyasından yeniden hesaplanır. GeoTIFF künyesindeki
`HEC_RAS_EXECUTED` etiketi hangi durumun geçerli olduğunu bildirir.
