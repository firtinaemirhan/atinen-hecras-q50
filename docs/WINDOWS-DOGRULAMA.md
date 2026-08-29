# Windows Sağlama Listesi

Boru hattının okuma-hesap-yazma tarafı hem macOS'ta hem Windows 11'de gerçek
`p05.hdf` üzerinde doğrulandı. Kapatılacak tek adım **HEC-RAS'ın Python'dan
çalıştırılması**.

2026-08-29'da Windows 11 + HEC-RAS 6.6 ile yapılan ilk denemede HEC-RAS
"Error in Loading Plan Data" verip yarım bir sonuç dosyası yazdı. Nedeni
bulundu ve uygulamaya çözümü eklendi — ayrıntısı
[`VERI-DENETIMI.md`](VERI-DENETIMI.md), özeti: teslim edilen projedeki yedi
planın beşi yüklenemiyor ve tek bozuk plan bütün proje açılışını düşürüyor.
Bu liste o düzeltmeyle birlikte baştan yürütülür.

---

## 0. Ortam

- [ ] **HEC-RAS 6.6** kurulu. Doğrula:
      `dir /s /b "C:\Program Files (x86)\HEC\Ras.exe"`
- [ ] **Python 3.13 veya 3.14** (python.org installer, "Add python.exe to PATH"
      işaretli). 3.12 kullanmayın: artık Windows installer'ı yayınlanmıyor.
      41 paketin tamamı bu iki sürümde hazır tekerlek olarak iner.
- [ ] `CASE_DATA` makinede ve şu dosya duruyor:
      `<CASE_DATA>\AKA_AFY_BAY_INPINAR_1\1_Modeller\A_A_B_INPINAR.prj`

Depoyu alın (git yoksa GitHub'da **Code → Download ZIP**, klasör adı
`atinen-hecras-q50-main` olur):

```bat
cd C:\atinen\atinen-hecras-q50-main
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-windows.txt
pip install -r requirements-dev.txt
```

⚠️ `-r` işaretini atlamayın. `pip install .` veya `pip install C:\atinen\...`
demeyin — proje `python main.py` ile çalışır.
İkinci satır testler ve `tools/preview.py` içindir.

**Beklenen:** her paket hazır `.whl` olarak iner. Çıktıda `Building wheel for ...`
görürseniz Python sürümü uyumsuzdur. Komut İstemi (cmd) kullanın; PowerShell
`activate` betiğini engelleyebilir.

> Bağımlılık ağacı, 2014'ten kalma `pathlib` 1.0.1 paketini de getiriyor
> (ras-commander üzerinden). Standart kütüphane `sys.path`'te önce geldiği için
> gölgeleme olmuyor; kod ras-commander kurulu bir ortamda sınandı.

---

## 1. Testler (HEC-RAS'a dokunmadan)

```bat
set Q50_CASE_DATA=C:\atinen\CASE_DATA
python -m pytest tests -q
```

**Beklenen:** `80 passed`. `CASE_DATA` yoksa gerçek veri testleri atlanır.
`No module named pytest` derse 0. adımdaki `requirements-dev.txt` satırı
atlanmıştır.

---

## 2. Referans sayılar (HEC-RAS'sız)

Projede hazır duran sonuçlardan haritayı üretir; okuma-hesap-yazma zincirini
uçtan uca sınar.

```bat
python main.py --project C:\atinen\CASE_DATA --use-existing-results --output OUTPUT\q50_ref.tif
```

**Beklenen** (macOS ve Windows 11'de birebir aynı çıktı):

| | |
| --- | --- |
| Seçilen plan | `p05` |
| Izgara | 4788 × 2756 @ 0.1 m |
| Islak hücre | 4165 / 5470 |
| Islak piksel | 413 858 |
| Maksimum derinlik | 1.625 m |
| Ortalama derinlik | 0.130 m |
| Doğrulama | 8 kontrolün 8'i `ok` |
| Bütünlük | `source unchanged (176 files, fast check)` |

Bu adımda ayrıca teslim edilen projenin kusurları not olarak listelenir
(`note: p03: flow file u01 is not declared...`). Bu beklenen davranış; hazır
sonuç okunurken onarım yapılmaz.

---

## 3. Asıl sınav: HEC-RAS'ı çalıştır

```bat
python main.py ^
  --project C:\atinen\CASE_DATA ^
  --ras-dir "C:\Program Files (x86)\HEC\HEC-RAS\6.6" ^
  --output OUTPUT\q50_depth.tif
```

Projeyi kopyalar (~290 MB, bir-iki dakika), çalışma kopyasını onarır, sonra
hesaplar. **Beklenen akış:**

```
[3/6] workspace   copying project to workspace\A_A_B_INPINAR_Q50
      note: p05 reads .\_CBS\...\akarcay_debi.dss (inflow), which does not resolve ...
      note: p03: flow file u01 is not declared by the project
      note: p04: boundary condition reads ..\..\akarcay_debi.dss, which does not resolve
      ...
[4/6] prepare     repairing 2 unresolved path(s)
      .\_CBS\akarcay_debiler\akarcay_debi.dss -> copied into place from 2_CBS\...
      .\Q50\Q50.dss -> created output folder
      4 unrelated plan(s) in this project cannot be loaded by HEC-RAS;
      reducing the working copy to the selected plan
      A_A_B_INPINAR.prj now declares only p05, g03, u05 (16 declarations removed)
[4/6] hec-ras     computing p05 via cmdr
      RasCmdr.compute_plan -> success=True, NN.N s
[5/6] ...  -> 413858 piksel, max 1.625 m   (2. adımla aynı olmalı)
```

HEC-RAS penceresi açılıp kapanabilir, normal.

**Geometri adımında ne görmek istiyoruz:** `HEC-RAS wrote the tables itself`.
Bunun yerine `RasProcess.exe is not in ...` ya da `still missing: ...` görürseniz
uygulama yedek yola geçer (tabloları teslim edilen sonuç dosyasından alır) ve
`Run HTab -1 -> 0` yapar — o da geçerli bir yol, ama HEC-RAS'ın kendi yazdığı
tablolar tercih edilir.

### Düşerse

Uygulama artık çalıştırıcının "başarılı" demesine güvenmiyor: sonuç dosyasında
`Plan Data` ve `Results` yoksa durur ve **HEC-RAS'ın kendi hesap günlüğünün son
satırlarını hata mesajına ekler.** Yani ekrandaki çıktı çoğu zaman yeterli.

Sırayla denenecekler:

1. **Hidrografı da gömerek deneyin** — sınır koşulunu DSS'ten okumayı tamamen
   devre dışı bırakır:
   ```bat
   python main.py --project C:\atinen\CASE_DATA ^
     --ras-dir "C:\Program Files (x86)\HEC\HEC-RAS\6.6" ^
     --inflow inline --output OUTPUT\q50_depth.tif
   ```
   Seri projedeki DSS metin dökümünden okunup akış dosyasına yazılır; koşu
   artık DSS'e bağlı olmaz. Beklenen satır:
   `embedded the inflow into A_A_B_INPINAR.u05 ...: 15 ordinates at 5 min, peak 1.69 m3/s`
2. Aynı komuta `--runner controller` ekleyin — COM otomasyonu
   (`RAS66.HECRASController`), GUI'nin kullandığı arayüz.
3. Hazırlanmış kopyayı elle açıp bakın:
   ```bat
   python main.py --project C:\atinen\CASE_DATA --prepare-only
   ```
   sonra HEC-RAS'ta `workspace\A_A_B_INPINAR_Q50\A_A_B_INPINAR.prj` — bu proje
   yalnız Q50'yi bildirir, diğer bozuk planlar çıkarılmıştır. Plan listesinde
   tek bir Q50 görmelisiniz. `Run → Unsteady Flow Analysis → Compute`.
4. Hâlâ düşüyorsa `OUTPUT\run.log` ile
   `workspace\A_A_B_INPINAR_Q50\A_A_B_INPINAR.bco05` dosyalarını paylaşın.

---

## 4. Çıktıyı gözle doğrula

```bat
python tools\preview.py OUTPUT\q50_depth.tif --terrain C:\atinen\CASE_DATA\AKA_AFY_BAY_INPINAR_1\1_Modeller\merge.Clone.vrt
gdalinfo OUTPUT\q50_depth.tif
```

- [ ] Sayılar 2. adımla aynı mı? (HEC-RAS yeniden hesapladığı için birebir
      olmalı; küçük fark çekirdek sayısına bağlı olabilir, büyük fark araştırılmalı)
- [ ] Görüntü dere koridorunu takip ediyor mu?
- [ ] **Sezer Bey'in toplantıda gösterdiği çıktıya benziyor mu?**
- [ ] Etiketlerde `SCENARIO=Q50`, `PLAN_NUMBER=p05`, **`HEC_RAS_EXECUTED=True`** var mı?

---

## 5. Orijinal veri gerçekten bozulmadı mı

```bat
python main.py --project C:\atinen\CASE_DATA --ras-dir "C:\Program Files (x86)\HEC\HEC-RAS\6.6" --integrity full
```

**Beklenen:** `integrity   source unchanged (176 files, full check)` — her
dosyanın SHA-256'sı koşu öncesi ve sonrası karşılaştırılır.

---

## 6. RASMapper ile karşılaştırma (opsiyonel)

1. HEC-RAS → RASMapper, `workspace\A_A_B_INPINAR_Q50` projesini yükleyin
2. Results → **Q50** → **Depth → Max** katmanını görüntüleyin
3. Sağ tık → **Export Layer → GeoTIFF** → `q50_depth_RASMAPPER.tif`
4. QGIS'te iki rasteri üst üste koyup farka bakın

Fark beklenir: bizim harita su yüzeyini hücre içinde sabit kabul eder,
RASMapper eğimli çizebilir. Önemli olan taşkın yayılımının ve derinlik
mertebesinin örtüşmesi.

---

## 7. Teslim dosyalarını yenile

HEC-RAS gerçekten çalıştıktan sonra:

```bat
copy OUTPUT\run.log docs\ornek-calisma-kaydi.txt
python tools\preview.py OUTPUT\q50_depth.tif --terrain "...\merge.Clone.vrt" -o docs\q50_depth_preview.png
git add -f OUTPUT\q50_depth.tif OUTPUT\run.log docs\
git commit -m "HEC-RAS ile hesaplanan cikti"
git push
```

Depoyu ZIP olarak indirdiyseniz git yoktur; `OUTPUT\q50_depth.tif`,
`OUTPUT\run.log` ve `docs\q50_depth_preview.png` dosyalarını geri taşımanız
yeterli.

- [ ] README'nin "Bilinen sınırlamalar" bölümündeki "hesap adımı sınanmadı"
      maddesi artık geçersiz — güncelleyin.

---

## Sonuç

- [ ] HEC-RAS Python'dan çalıştı mı, hangi runner ile?
- [ ] Hesaplanan çıktı 2. adımdaki referans sayılarla örtüştü mü?
- [ ] Orijinal `CASE_DATA` bozulmadı mı?
- [ ] Çıktı Sezer Bey'in gösterdiği görüntüye benziyor mu?
