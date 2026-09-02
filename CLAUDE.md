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

`CASE DATA 2` (1 Eylül 2026'da gelen düzeltilmiş veri, 317 MB, 251 dosya).
Depoda **yok**, müşteri verisi. Yolu `Q50_CASE_DATA` ile verilir; verilmezse
masaüstünde `CASE DATA 2`, `CASE_DATA 2`, `CASE_DATA_2` adları denenir (klasör
aktarımda ad değiştirebiliyor).

Doğrulama işaretleri:
- `AKA_AFY_BAY_INPINAR_1/3_Pafta/6_derinlik/q50_d.tif` var (1 561 857 bayt).
  Eski veride `3_Pafta` ağacı hiç yok, ayırt edici işaret bu.
- `1_Modeller/A_A_B_INPINAR.p05.hdf` SHA-256:
  `f3df669a9abde3d6c53ce69254f3649a11da1c776b198145d21fc9ec114a43cd`
  (bu dosya eski veride de aynı, yani tek başına yeni/eski ayrımı yapmaz).
- Alt klasörler: `1_Modeller` 182 dosya, `2_Rapor` **boş** (müşteriden öyle
  geldi), `3_Pafta` 69 dosya.

Eski `CASE_DATA` hatalıydı, kullanma.

## Şu an açık olan tek iş: HEC-RAS'ı Windows'ta çalıştırmak

Harita tarafı bitti. Kalan iş, `RasUnsteady.exe`'nin
`forrtl: severe (157) access violation` ile `READ_UN_HDF_STRUC` içinde
ölmesini çözmek.

**Sınanan ve ÇÜRÜYEN hipotez (1-2 Eylül gecesi):** `A_A_B_INPINAR.p05`
`UNET Use Existing IB Tables=-1` diyor ve teslim edilen `g03.hdf`'te
`Geometry/Structures/Property Tables` yok. `--ib-tables rebuild` ile bayrak
kapatıldı, ön işlemci çalıştı, **motor gene aynı yerde öldü:**

```
Computing 2D Flow Area 'inpinar' tables: Property tables do not exist.
2D Flow Area 'inpinar' tables complete 4,56 sec
Geometric Preprocessor HEC-RAS 6.6 September 2024
Finished Processing Geometry
Performing Unsteady Flow Simulation  HEC-RAS 6.6 September 2024
forrtl: severe (157): Program Exception - access violation
RasUnsteady.exe  READ_UN_HDF_STRUC  330  Read_UN_HDF_STRUC_GRP.for
```

Kaçırılan ayrım: ön işlemcinin kurduğu şey **2D Flow Area** (mesh) tabloları,
`READ_UN_HDF_STRUC`'un okuduğu şey **Structures** property tabloları. İkisi ayrı.
`Geometry/Structures` var, içinde `Property Tables` yok, ön işlemci de onu
kurmuyor.

**Altı adayın altısı da düştü** (ib-rebuild, rasprocess, harvest, controller,
single-core, inline-hydrograph), dördü aynı imzayla: `READ_UN_HDF_STRUC` 330.
Kanıt: `evidence/` klasörü.

**Kritik gözlem:** `harvest` adayı `p05.hdf`'ten TÜM Geometry grubunu kopyalar,
yani o denemede `Structures/Property Tables` **vardı** ve gene çöktü. Demek ki
tabloların varlığı tek başına yetmiyor; sorun ya tabloların içeriğinde, ya da
onlara işaret eden indekslerin (`Structures/Table Info`) tutmamasında.
`harvest` logunda ayrıca "inpinar: Mesh property tables are current." yazıyor —
mesh tarafı sebep değil.

**Model çalışıyor, sorun teslim edilen veride.** Müşterinin kendi 9 Temmuz
koşusu `p05.hdf` içinde duruyor: 1 dk 35 sn, hacim hatası %0,16, ve içinde
`0302_4` SA/2D bağlantısı menfeziyle birlikte sorunsuz çalışmış. Yani çöküş
modelin doğasında değil, geometrinin 10 Ağustos'ta yeniden kaydedilirken yapı
tablolarını kaybetmiş olmasında.

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
