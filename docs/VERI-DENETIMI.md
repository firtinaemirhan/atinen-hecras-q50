# Teslim Edilen Verinin Denetimi

`tools/audit_project.py` çıktısı. Bu rapor elle yazılmadı, araç üretti:

```
python tools/audit_project.py --project /path/to/CASE_DATA
```

```text
Audit of <CASE_DATA>

BLOCKER (8)
-------------
  plan p03                     uses unsteady flow u01, which the project file does not declare (the file exists on disk)
  plan p04 inflow              boundary condition reads ..\..\akarcay_debi.dss, which does not resolve
  plan p05 inflow              boundary condition reads .\_CBS\akarcay_debiler\akarcay_debi.dss, which does not resolve
  plan p06 inflow              boundary condition reads .\_CBS\akarcay_debiler\akarcay_debi.dss, which does not resolve
  plan p07 inflow              boundary condition reads .\_CBS\akarcay_debiler\akarcay_debi.dss, which does not resolve
  geometry g01                 A_A_B_INPINAR.g01.hdf lacks Geometry/Structures/Property Tables, Geometry/GeomPreprocess; the unsteady engine reads these and crashes without them
  geometry g02                 A_A_B_INPINAR.g02.hdf lacks Geometry/Structures/Property Tables, Geometry/GeomPreprocess; the unsteady engine reads these and crashes without them
  geometry g03                 A_A_B_INPINAR.g03.hdf lacks Geometry/Structures/Property Tables, Geometry/GeomPreprocess; the unsteady engine reads these and crashes without them

WARNING (23)
-------------
  plan p03 output              DSS destination dss does not resolve
  plan p02 output              DSS destination dss does not resolve
  plan p01 output              DSS destination dss does not resolve
  plan p04 output              DSS destination dss does not resolve
  plan p05 output              DSS destination .\Q50\Q50.dss does not resolve
  plan p06 output              DSS destination .\Q100\Q100.dss does not resolve
  plan p07 output              DSS destination .\Q1000\Q1000.dss does not resolve
  project DSS list             .\Q500\Q500.dss does not resolve
  project DSS list             .\_CBS\akarcay_debiler\akarcay_debi.dss does not resolve
  project DSS list             malformed entry 'dss'
  project DSS list             .\Q1000\Q1000.dss does not resolve
  project DSS list             .\Q100\Q100.dss does not resolve
  project DSS list             .\Q50\Q50.dss does not resolve
  rasmap layer                 %LocalAppData%\HEC\Mapping\5.1\XML\Google Hybrid.xml does not resolve
  rasmap layer                 .\A_A_B_INPINAR.u02.hdf does not resolve
  rasmap layer                 .\A_A_B_INPINAR.u03.hdf does not resolve
  rasmap layer                 .\Calculated Layers\q1000_d.rasscript does not resolve
  rasmap layer                 .\Calculated Layers\q1000_d.tif does not resolve
  rasmap layer                 .\Q1000\Depth (Max).vrt does not resolve
  rasmap layer                 .\Q1000\Velocity (Max).vrt does not resolve
  rasmap layer                 .\Q100\Depth (Max).vrt does not resolve
  rasmap layer                 .\Q100\Velocity (Max).vrt does not resolve
  rasmap layer                 .\_CBS\AKA_AFY_BAY_INPINAR_1\ROLEVE\KOPRU_AD_HAT\KOPRU_AD_HAT.shp does not resolve

NOTE (18)
----------
  project file                 A_A_B_INPINAR.prj
  declared by project          3 geometry, 1 steady, 4 unsteady, 7 plans
  current plan                 p05
  plan p03                     A_A_B_INPINAR_UNSTEADY_2D (geom g03, flow u01)
  plan p02                     A_A_B_INPINAR_STEADY (geom g01, flow f01)
  plan p01                     A_A_B_INPNAR_STEADY (geom g01, flow f01)
  plan p04 inflow              u04 stores no hydrograph ordinates; it depends on the DSS file
  plan p04                     A_A_B_INPINAR_Q500 (geom g03, flow u04)
  plan p05 inflow              u05 stores no hydrograph ordinates; it depends on the DSS file
  plan p05                     A_A_B_INPINAR_Q50 (geom g03, flow u05)
  plan p06 inflow              u06 stores no hydrograph ordinates; it depends on the DSS file
  plan p06                     A_A_B_INPINAR_Q100 (geom g03, flow u06)
  plan p07 inflow              u08 stores no hydrograph ordinates; it depends on the DSS file
  plan p07                     A_A_B_INPINAR_Q1000 (geom g03, flow u08)
  undeclared file              A_A_B_INPINAR.u01 exists but is not in the project
  undeclared file              A_A_B_INPINAR.u07 exists but is not in the project
  stray plan file              Backup.p01 looks like a plan but belongs to no project
  rasmap references            38 declared, 10 missing

Summary: 8 blocker, 23 warning, 18 note
```

---

## Ne anlama geliyor

### Engelleyiciler

**1. `p03` akış dosyası projede kayıtlı değil.**
`A_A_B_INPINAR.p03` içinde `Flow File=u01` yazıyor. Dosya diskte var, ama
`.prj`'nin akış dosyası listesi yalnız `u04, u05, u06, u08` diyor. HEC-RAS
kayıtlı olmayan dosyayı plana bağlayamıyor.

**2–5. Dört planın giriş debisi çözülmeyen bir yola bakıyor.**
Q50, Q100 ve Q1000 planları `.\_CBS\akarcay_debiler\akarcay_debi.dss` diyor;
klasörün diskteki adı **`2_CBS`**. Q500 planı ise `..\..\akarcay_debi.dss`
diyor — proje klasörünün iki üstü, yani teslim paketinin tamamen dışı.

Bu dört akış dosyasının hiçbirinde hidrograf gömülü değil (`Flow Hydrograph= 0`),
yani DSS olmadan senaryo çalıştırılamaz.

**6–8. Üç geometri dosyasının da ön işlenmiş tabloları yok.**
`A_A_B_INPINAR.g01/g02/g03.hdf` dosyalarında `Geometry/Structures` var ama
`Geometry/Structures/Property Tables` ve `Geometry/GeomPreprocess` yok. Unsteady
motoru başlarken tam olarak bu tabloları okuyor (`READ_UN_HDF_STRUC`) ve
bulamayınca **eksik olduğunu söylemek yerine çöküyor**:

```
Performing Unsteady Flow Simulation  HEC-RAS 6.6 September 2024
forrtl: severe (157): Program Exception - access violation
RasUnsteady.exe   READ_UN_HDF_STRUC   330   Read_UN_HDF_STRUC_GRP.for
RasUnsteady.exe   SNETREAL2           179   Snetreal2.for
RasUnsteady.exe   UNET_START          144   Unet_start.for
Error with program: RasUnsteady.exe  Exit Code = 157
```

Geometri ön işlemcisini yeniden çalıştırmak yetmiyor: o yalnızca 2D akış alanı
tablolarını üretiyor (*"Computing 2D Flow Area 'inpinar' tables"*), yapı
tablolarına dokunmuyor. Yani `Run HTab=-1` ile her koşuda aynı yere düşülüyor.

Tablolar aslında teslim paketinde **var** — orijinal başarılı koşunun ürettiği
`A_A_B_INPINAR.p05.hdf` içinde eksiksiz bir `Geometry` grubu duruyor, aynı
geometri ve aynı arazi için.

### Bunun pratik sonucu

HEC-RAS bir projeyi açarken **bildirilen bütün planları** yükler. Yedi planın
beşi yüklenemiyor ve tek bir "Error in Loading Plan Data" kutusu bütün açılışı
düşürüyor — p05 kendi başına tutarlı olmasına rağmen. Komut satırından
çalıştırıldığında bu daha da sinsi: çalıştırıcı yine "başarılı" raporluyor,
geriye yarım bir `p05.hdf` kalıyor.

Bu 2026-08-29'da Windows 11 + HEC-RAS 6.6 üzerinde birebir gözlendi; hem
komut satırından hem de HEC-RAS arayüzünden elle açıldığında aynı hata çıktı.

### Uygulama ne yapıyor

Çalışma kopyasında, sırayla:

1. **Çözülmeyen giriş dosyasını yerine koyuyor.** Proje ağacında aynı adlı
   dosya aranıyor; tam bir tane bulunursa modelin beklediği yola kopyalanıyor.
   Hiç ya da birden fazla aday varsa tahmin yürütmüyor, duruyor.
2. **Çıktı DSS klasörünü oluşturuyor** (`Q50/`), çünkü HEC-RAS dosyayı kendi
   yazıyor ama klasörü yaratmıyor.
3. **Proje dosyasını seçilen plana indiriyor.** Yalnız `p05`, `g03` ve `u05`
   bildiriliyor; açılamayan diğer planlar listeden çıkarılıyor. Böylece
   HEC-RAS'ın yükleyeceği başka bir şey kalmıyor. Bu adım yalnızca başka bir
   plan bozuksa yapılıyor (`--trim-project auto`, varsayılan).
4. **Geometri dosyasını yeniden kuruyor.** Eksik ön işlenmiş tablolar, teslim
   edilen sonuç dosyasındaki eksiksiz `Geometry` grubundan alınıp çalışma
   kopyasının `g03.hdf` dosyasına yazılıyor; geometri dosyasının kendi kök
   öznitelikleri korunuyor. Ardından plan dosyasında `Run HTab=-1 → 0`
   yapılıyor, çünkü ön işlemci yeniden çalışırsa o tabloları tekrar siler.
5. **RASMapper'ın hazır harita üretimini kapatıyor.**
6. **Önceki koşumdan kalan sonuç dosyasını siliyor**, yarım bir HDF'in yeni
   koşuyu kirletmemesi için.
7. İstenirse (`--inflow inline`) **sınır koşulu hidrografını akış dosyasına
   gömüyor**, böylece koşu DSS okumaya hiç bağlı kalmıyor.

Bunların hiçbiri `CASE_DATA`'ya dokunmuyor; çalışma sonundaki bütünlük
kontrolü bunu her koşuda kanıtlıyor.

### Uyarılar ve notlar

`Q100`, `Q500`, `Q1000` senaryo klasörleri teslim paketinde yok — ama `.rasmap`
içinde `Q100\Depth (Max).vrt` ve `Q1000\Depth (Max).vrt` katmanları hâlâ
tanımlı. Yani orijinal projede her senaryo için **hazır RASMapper derinlik
haritaları** vardı ve bu klasörler teslim öncesi çıkarılmış. Belgedeki "hazır
bir maksimum derinlik çıktısı sağlanmamaktadır" cümlesinin diskteki karşılığı
budur; kalan referanslar da bunun izi.

`Backup.p01` ise plan gibi görünen ama hiçbir projeye ait olmayan bir dosya:
başlığı tam olarak `A_A_B_INPINAR_Q50`, kısa kimliği `Q50`. Klasör tarayan bir
plan seçici bunu da bulur — uygulamanın plan listesini `.prj`'den okumasının
sebebi bu.
