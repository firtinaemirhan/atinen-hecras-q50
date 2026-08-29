# Windows Sağlama Listesi

Boru hattının tamamı macOS'ta gerçek `p05.hdf` üzerinde çalıştırıldı. Sınanamayan
tek adım **HEC-RAS'ın Python'dan çalıştırılması**. Bu liste onu kapatmak içindir.

Sırayla gidin; her adımın altında "beklenen" var, tutmuyorsa ne bakılacağı yazıyor.

---

## 0. Ortam

- [ ] **HEC-RAS 6.6** kurulu. Varsayılan yol:
      `C:\Program Files (x86)\HEC\HEC-RAS\6.6\Ras.exe`
- [ ] Python **3.13 veya 3.14** (python.org installer, "Add python.exe to PATH"
      işaretli). Her iki sürümde de 41 paketin tamamı hazır tekerlek olarak iner.
      3.12 kullanmayın: artık Windows installer'ı yayınlanmıyor.
- [ ] Depo klonlandı, `CASE_DATA` makinede

Git kuruluysa:

```bat
git clone https://github.com/firtinaemirhan/atinen-hecras-q50.git
cd atinen-hecras-q50
```

Git yoksa GitHub'da **Code → Download ZIP**, `C:\atinen` altına çıkarın; klasör
adı `atinen-hecras-q50-main` olur.

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-windows.txt
```

**Beklenen:** her paket hazır `.whl` olarak iner, hiçbir şey derlenmez.
**Tutmazsa:** çıktıda `Building wheel for ...` görüyorsanız Python sürümü uyumsuz
demektir — 3.13 veya 3.14'e geçin. Komut İstemi (cmd) kullanın; PowerShell `activate`
betiğini engelleyebilir.

> **Not.** Bağımlılık ağacı, 2014'ten kalma `pathlib` 1.0.1 paketini de getiriyor
> (ras-commander üzerinden). Standart kütüphane `sys.path`'te önce geldiği için
> gölgeleme olmuyor; kod ras-commander kurulu bir ortamda sınandı, 44 test geçti.

---

## 1. Kurulum ayakta mı (HEC-RAS'sız)

```bat
python -m pytest tests -q
```

**Beklenen:** 44 test geçer. `CASE_DATA` yoksa gerçek veri testleri atlanır.
`CASE_DATA` başka yerdeyse:

```bat
set Q50_CASE_DATA=D:\CASE_DATA
python -m pytest tests -q
```

---

## 2. Hesapsız uçtan uca (referans sayılar)

HEC-RAS'ı çalıştırmadan, projede hazır duran sonuçlardan haritayı üretir.

```bat
python main.py --project D:\CASE_DATA --use-existing-results --output OUTPUT\q50_ref.tif
```

**Beklenen (macOS'ta ölçülen değerler):**

| | |
| --- | --- |
| Seçilen plan | `p05` |
| Izgara | 4788 × 2756 @ 0.1 m |
| Islak hücre | 4165 / 5470 |
| Islak piksel | 413 858 |
| Maksimum derinlik | 1.625 m |
| Ortalama derinlik | 0.130 m |
| Doğrulama | 8 kontrolün 8'i `ok` |

Bu sayılar tutuyorsa okuma/hesap/yazma tarafı Windows'ta da aynı çalışıyor demektir.

---

## 3. Asıl sınav: HEC-RAS'ı çalıştır

```bat
python main.py ^
  --project D:\CASE_DATA ^
  --ras-dir "C:\Program Files (x86)\HEC\HEC-RAS\6.6" ^
  --output OUTPUT\q50_depth.tif
```

**Beklenen:**
- `[3/6] workspace   copying project to workspace\A_A_B_INPINAR_Q50` (bir-iki dakika, ~500 MB)
- `[4/6] hec-ras     computing p05 via cmdr` ardından `success=True`
- `[5/6]` bölümündeki sayılar 2. adımdakilerle **aynı** çıkmalı
- `integrity   source unchanged (... files, fast check)`

**`cmdr` başarısız olursa** COM otomasyonunu deneyin — aynı komuta
`--runner controller` ekleyin. Bu, HEC-RAS GUI'sinin kullandığı
`RAS66.HECRASController` nesnesini sürer.

**İkisi de başarısız olursa** bakılacak yerler, sırayla:
1. `workspace\A_A_B_INPINAR_Q50\A_A_B_INPINAR.bco05` — HEC-RAS'ın kendi hesap günlüğü
2. `OUTPUT\run.log` — tam yığın izi burada
3. HEC-RAS'ı elle açıp aynı projeyi/planı çalıştırın: elle de çalışmıyorsa sorun
   kodda değil, modelde ya da kurulumdadır

---

## 4. Hesaplanan çıktı doğru mu

```bat
python -m pip install -r requirements-dev.txt
python tools\preview.py OUTPUT\q50_depth.tif --terrain D:\CASE_DATA\AKA_AFY_BAY_INPINAR_1\1_Modeller\merge.Clone.vrt
```

- [ ] Sayılar 2. adımla aynı mı? (HEC-RAS yeniden hesapladığı için birebir aynı
      olmalı; küçük farklar çekirdek sayısına bağlı olabilir, büyük fark
      araştırılmalı)
- [ ] Görüntü dere koridorunu takip ediyor mu?
- [ ] **Sezer Bey'in toplantıda gösterdiği çıktıya benziyor mu?**

```bat
gdalinfo OUTPUT\q50_depth.tif
```

- [ ] `SCENARIO=Q50`, `PLAN_NUMBER=p05`, `HEC_RAS_EXECUTED=True` etiketleri var mı?

---

## 5. Orijinal veri gerçekten bozulmadı mı

```bat
python main.py --project D:\CASE_DATA --ras-dir "..." --integrity full
```

**Beklenen:** `integrity   source unchanged (176 files, full check)`
Bu, her dosyanın SHA-256'sını çalışma öncesi ve sonrası karşılaştırır.

Ek olarak Explorer'da `D:\CASE_DATA` içindeki dosya tarihlerinin değişmediğini
gözle de doğrulayın.

---

## 6. RASMapper ile karşılaştırma (opsiyonel ama değerli)

Kendi haritamızın RASMapper'ın ürettiğine ne kadar yakın olduğunu görmek için:

1. HEC-RAS → RASMapper'ı açın, `workspace\A_A_B_INPINAR_Q50` projesini yükleyin
2. Results altında **Q50** planını, **Depth → Max** katmanını görüntüleyin
3. Katmana sağ tık → **Export Layer → GeoTIFF** → `q50_depth_RASMAPPER.tif`
4. İki rasteri QGIS'te üst üste koyup farkı bakın

Fark beklenir ve normaldir: bizim harita su yüzeyini hücre içinde **sabit**
kabul eder, RASMapper eğimli çizebilir. Önemli olan taşkın **yayılımının** ve
derinlik **mertebesinin** örtüşmesi.

---

## 7. Teslim dosyalarını yenile

HEC-RAS gerçekten çalıştıktan sonra depodaki teslim kalemleri güncellenmeli:

```bat
copy OUTPUT\run.log docs\ornek-calisma-kaydi.txt
python tools\preview.py OUTPUT\q50_depth.tif --terrain "...\merge.Clone.vrt" -o docs\q50_depth_preview.png
git add -f OUTPUT\q50_depth.tif OUTPUT\run.log docs\
git commit -m "HEC-RAS ile hesaplanan çıktı"
git push
```

- [ ] `gdalinfo OUTPUT\q50_depth.tif` çıktısında **`HEC_RAS_EXECUTED=True`** görünüyor mu?
- [ ] README'nin "Bilinen sınırlamalar" bölümündeki "hesap adımı sınanmadı"
      maddesi artık geçersiz — güncellenmeli.

---

## Sonuç

Bittiğinde şunu bilmek istiyoruz:

- [ ] HEC-RAS Python'dan çalıştı mı, hangi runner ile?
- [ ] Hesaplanan çıktı 2. adımdaki referans sayılarla örtüştü mü?
- [ ] Orijinal `CASE_DATA` bozulmadı mı?
- [ ] Çıktı Sezer Bey'in gösterdiği görüntüye benziyor mu?

Takılan bir yer olursa `OUTPUT\run.log` ile `*.bco05` dosyası sorunu bulmaya
yeter.
