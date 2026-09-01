# q50depth — Atinen HEC-RAS Q50 derinlik haritası

Bu bir müşteri işi (Atinen, irtibat: Sezer Bey). Bir HEC-RAS projesinden Q50
senaryosunun maksimum su derinliği haritasını tek komutla üreten Python
uygulaması. **Teslim: 5 Eylül 2026 Cumartesi.**

Türkçe konuş. Kullanıcı Emirhan. Ton: kısa, direkt, dolgu cümlesi yok.

## Bu depoda çalışırken bağlayıcı kurallar

- **Ölçmeden yazma.** Rapora, README'ye veya bir yoruma koyduğun her sayı için
  onu üreten komut çalıştırılmış olmalı. Emin değilsen "bilinmiyor" yaz.
  Bu depoda daha önce üç sayı ölçümle tutmadı; o yüzden bu kural var.
- **Doğrulamadığın kütüphane API'si için kod yazma.** `ras-commander`
  imzaları `inspect.signature` ile kurulu paketten okundu, belgeden değil.
- **Teslim edilen veriye dokunma.** Her onarım çalışma kopyasında yapılır.
- **Ölçemediğin bir bulguyu ölçülmüş kanıtla aynı düzeyde sunma.**

## Nerede ne var

| İş | Dosya |
| --- | --- |
| Giriş noktası | `main.py`, `q50depth/cli.py` |
| Su yüzeyi modelleri (sloping / flat) | `q50depth/surface.py` |
| Derinlik ızgarası | `q50depth/depth.py` |
| Sonuç HDF okuma | `q50depth/results.py` |
| Arazi + bina kot değişiklikleri | `q50depth/terrain.py` |
| HEC-RAS koşusu (yalnız Windows) | `q50depth/compute.py` |
| Proje onarımı | `q50depth/references.py`, `q50depth/geometry.py`, `q50depth/project.py` |
| Referansla karşılaştırma | `tools/compare_reference.py` |
| **Windows koşu betiği** | `tools/windows_verify.py` |
| Windows sağlama listesi | `docs/WINDOWS-DOGRULAMA.md` |
| Yöntemin tamamı | `README.md` |

Testler: `python -m pytest -q` → **94 test**. Veri varken `94 passed`,
veri yokken `87 passed, 7 skipped` — atlanan yediyi `tests/test_real_data.py`
içindekiler oluşturur ve `Q50_CASE_DATA` gerektirir.

## Veri

`CASE DATA 2` (1 Eylül 2026'da gelen düzeltilmiş veri, ~317 MB). Depoda
**yok**, müşteri verisi. Yolu `Q50_CASE_DATA` ile verilir.

Eski `CASE_DATA` hatalıydı, kullanma.

## Şu an açık olan tek iş: HEC-RAS'ı Windows'ta çalıştırmak

Harita tarafı bitti. Kalan iş, `RasUnsteady.exe`'nin
`forrtl: severe (157) access violation` ile `READ_UN_HDF_STRUC` içinde
ölmesini çözmek.

**En güçlü hipotez (henüz sınanmadı):** `A_A_B_INPINAR.p05` dosyası

```
UNET Use Existing IB Tables=-1
```

diyor, yani yapı (internal boundary) tablolarını geometriden hazır oku. Ama
teslim edilen `A_A_B_INPINAR.g03.hdf` içinde `Geometry/Structures/Property
Tables` yok. Çöken rutinin adı tam olarak o tabloları okuyan rutin. Daha
önceki yedi deneme bu bayrağa hiç dokunmadı. `--ib-tables rebuild` bunu
kapatır.

Çalıştırılacak komut:

```
python tools\windows_verify.py ^
  --project "<CASE DATA 2 yolu>" ^
  --ras-dir "C:\Program Files (x86)\HEC\HEC-RAS\6.6" ^
  --reference "<CASE DATA 2 yolu>\AKA_AFY_BAY_INPINAR_1\3_Pafta\6_derinlik\q50_d.tif"
```

Altı adayı sırayla dener, ilk başarılıda durur, her denemenin kanıtını
(uygulama çıktısı + HEC-RAS'ın plan HDF'i içindeki hesap günlüğü + `.bco`)
`evidence/` altına yazar. **Başarısız koşu da kanıttır, hiçbir log silinmez.**

Koşu tutarsa: GeoTIFF künyesindeki `HEC_RAS_EXECUTED` `True` olur, sonra
RASMapper'a haritayı kendisine ürettirip bizim çıktıyla karşılaştıracağız.

## Bilinen veri kusurları (müşteri verisinde, bizde değil)

1. `u05` debisini `.\_CBS\akarcay_debiler\akarcay_debi.dss` yolundan okuyor;
   diskteki klasörün adı **`2_CBS`**. Program çalışma kopyasında onarır.
2. `g01`–`g03` geometrilerinde ön işlenmiş 2B tabloları yok.
3. `g03.hdf` ile `p05.hdf` aynı mesh'i **farklı yüz/hücre numaralandırmasıyla**
   tutuyor (`Faces FacePoint Indexes`'in 25.736 değerinin 21.111'i farklı).
   Tabloları p05'ten aşılayan `--geometry harvest` yolunun riski bu.
4. Yedi planın beşi yüklenemiyor; bir bozuk plan bütün proje açılışını düşürür.
   Program çalışma kopyasını seçilen plana indirger.

Ayrıntı: `docs/VERI-DENETIMI.md`.

## Haritanın kök nedeni (1 Eylül'de bulundu, çözüldü)

Harita müşterininkinden farklıydı. Sebep projenin kendi dosyasında yazıyordu:
`A_A_B_INPINAR.rasmap` içinde `<RenderMode>sloping</RenderMode>`. RASMapper
eğimli su yüzeyi çiziyor, kod ise her hücreye düz bir kot boyuyordu.

Ayrıca `p05.hdf` içinde 1247 hücre float32 yuvarlamasıyla 0,0001 m "ıslak"
geliyor; bunlar +20 m bina kotundaki hücreler ve eğimli yüzeye girdiklerinde
komşu köşeyi yukarı çekip 13,5 m derinlik üretiyorlardı. Islaklık toleransı
varsayılan 1 mm.

Referansın kendi ızgarasında ölçülen sonuç:

| Yüzey | IoU | ort. mutlak fark | sapma | ortalama | maksimum |
| --- | --- | --- | --- | --- | --- |
| Düz (eski) | %56,42 | 0,0390 m | +0,0139 m | 0,1336 m | 1,6254 m |
| Eğimli (yeni) | %72,82 | 0,0187 m | −0,0008 m | 0,1280 m | 1,5724 m |
| Referans | — | — | — | 0,1285 m | 1,5705 m |

Bit düzeyinde birebir kopya bu veriyle mümkün değil: referans bir noktada
ArcGIS'te yeniden örneklenmiş (ızgara yarım piksel kaymış) ve onu üreten ham
RASMapper çıktısı pakette yok. Bu, Windows koşusu tuttuktan sonra RASMapper'a
haritayı ürettirerek kapatılacak.

Altı alternatif yüzey varyantı denendi, hepsi daha kötü. Yeniden denemeye
gerek yok; hangi varyantların elendiği `README.md` ve
`🔮 850-Companion/Last-Session.md` (Emirhan'ın vault'u, bu makinede olmayabilir)
içinde yazılı.
