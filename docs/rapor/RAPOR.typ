// Q50 Maksimum Su Derinliği Otomasyonu — Teknik Rapor
// Dizgi: Typst 0.15. Derleme:  typst compile RAPOR.typ ../RAPOR.pdf
//
// Rapordaki her kanıt bloğu, kanit/ klasöründeki ham çıktı dosyasından
// derleme anında okunur. Metin elle kopyalanmaz.

#let marka      = rgb("#0b3d70")
#let marka-acik = rgb("#1863dc")
#let mürekkep   = rgb("#1a1a1a")
#let soluk      = rgb("#5b6270")
#let cizgi      = rgb("#d6d9de")
#let zemin      = rgb("#f5f6f8")
#let iyi        = rgb("#0f7b4f")
#let kotu       = rgb("#a4262c")

#let kanit-sayaci = counter("kanit")

// ---- Kanıt bloğu: ham çıktı dosyasını olduğu gibi gösterir -------------
// Uzun satirlari gorunur bir devam isaretiyle katlar; hicbir karakter atilmaz.
#let katla(metin, en: 90) = {
  let cikti = ()
  for satir in metin.split("\n") {
    if satir.len() <= en {
      cikti.push(satir)
    } else {
      let kalan = satir
      let girinti = ""
      while kalan.len() > en {
        cikti.push(girinti + kalan.slice(0, en) + " \u{21B5}")
        kalan = kalan.slice(en)
        girinti = "    "
      }
      cikti.push(girinti + kalan)
    }
  }
  cikti.join("\n")
}

#let kanit(baslik, dosya, satir: none, en: 90) = {
  kanit-sayaci.step()
  let icerik = read(dosya)
  if satir != none {
    icerik = icerik.split("\n").slice(satir.at(0), satir.at(1)).join("\n")
  }
  block(
    breakable: true,
    width: 100%,
    inset: (x: 9pt, y: 8pt),
    fill: zemin,
    stroke: (left: 2pt + marka-acik),
    radius: (right: 2pt),
    {
      set par(justify: false, leading: 0.5em)
      text(font: "Menlo", size: 7.4pt, fill: mürekkep, raw(katla(icerik.trim("\n"), en: en)))
    },
  )
  v(-2pt)
  block(width: 100%, grid(
    columns: (1fr, auto),
    column-gutter: 10pt,
    align: (left, right),
    text(size: 8.2pt, fill: soluk)[
      *Kanıt #context kanit-sayaci.display().* #baslik
    ],
    text(font: "Menlo", size: 7.2pt, fill: soluk)[#dosya],
  ))
  v(5pt)
}

// ---- Booktabs benzeri tablo -------------------------------------------
#let tablo(basliklar, satirlar, hizalar: none, sutunlar: auto) = {
  let n = basliklar.len()
  let hiza = if hizalar == none { (left,) * n } else { hizalar }
  block(width: 100%, above: 8pt, below: 6pt)[
    #table(
      columns: if sutunlar == auto { (auto,) * n } else { sutunlar },
      align: (x, y) => hiza.at(x) + (if y == 0 { bottom } else { top }),
      stroke: (x, y) => (
        top: if y == 0 { 0.9pt + mürekkep } else if y == 1 { 0.5pt + mürekkep } else { 0pt },
        bottom: if y == satirlar.len() { 0.9pt + mürekkep } else { 0pt },
      ),
      inset: (x: 5pt, y: 4.5pt),
      table.header(..basliklar.map(b => text(size: 8.6pt, weight: "semibold")[#b])),
      ..satirlar.flatten().map(c => text(size: 8.8pt)[#c]),
    )
  ]
}

#let uyari(icerik) = block(
  width: 100%, inset: (x: 10pt, y: 8pt), fill: rgb("#fdf6ec"),
  stroke: (left: 2pt + rgb("#b45309")), radius: (right: 2pt), icerik,
)

#let not-kutu(icerik) = block(
  width: 100%, inset: (x: 10pt, y: 8pt), fill: zemin,
  stroke: (left: 2pt + soluk), radius: (right: 2pt), icerik,
)

// ---- Sayfa düzeni -----------------------------------------------------
#set document(
  title: "HEC-RAS Q50 Maksimum Derinlik Otomasyonu — Teknik Rapor",
  author: "Emirhan Fırtına",
)
#set page(
  paper: "a4",
  margin: (top: 27mm, bottom: 24mm, left: 26mm, right: 24mm),
  header: context {
    let sayfa = here().page()
    if sayfa <= 2 { return }
    set text(size: 8pt, fill: soluk)
    grid(
      columns: (1fr, auto),
      align: (left, right),
      [Q50 Maksimum Derinlik Otomasyonu],
      {
        let hepsi = query(heading.where(level: 1))
        let bu = hepsi.filter(h => h.location().page() <= sayfa)
        if bu.len() > 0 {
          let h = bu.last()
          [#counter(heading).at(h.location()).at(0). #h.body]
        }
      },
    )
    v(-6pt)
    line(length: 100%, stroke: 0.4pt + cizgi)
  },
  footer: context {
    let sayfa = here().page()
    if sayfa <= 1 { return }
    align(center, text(size: 8.5pt, fill: soluk)[#sayfa])
  },
)

#set text(font: "Libertinus Serif", size: 10.5pt, lang: "tr", fill: mürekkep)
#set par(justify: true, leading: 0.68em, spacing: 1.0em, first-line-indent: 0pt)
#show raw: set text(font: "Menlo", size: 8.6pt)
#show link: set text(fill: marka-acik)

#set heading(numbering: "1.1")
#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  block(above: 0pt, below: 12pt)[
    #text(size: 9pt, fill: marka-acik, weight: "semibold", tracking: 0.1em)[
      BÖLÜM #counter(heading).display()
    ]
    #v(2pt)
    #text(size: 18pt, weight: "bold")[#it.body]
    #v(3pt)
    #line(length: 100%, stroke: 1.2pt + marka)
  ]
}
#show heading.where(level: 2): it => block(above: 16pt, below: 7pt)[
  #text(size: 12pt, weight: "bold", fill: marka)[
    #counter(heading).display() #h(4pt) #it.body
  ]
]
#show heading.where(level: 3): it => block(above: 12pt, below: 5pt)[
  #text(size: 10.5pt, weight: "semibold", style: "italic")[#it.body]
]

#set figure(numbering: "1")
#show figure.caption: it => text(size: 8.6pt, fill: soluk)[
  *Şekil #it.counter.display().* #it.body
]

// ======================================================================
// KAPAK
// ======================================================================
#v(38mm)
#text(size: 9.5pt, fill: marka-acik, weight: "semibold", tracking: 0.16em)[
  CASE STUDY · TEKNİK RAPOR
]
#v(5mm)
#text(size: 27pt, weight: "bold")[HEC-RAS Q50\ Maksimum Derinlik\ Otomasyonu]
#v(4mm)
#line(length: 42mm, stroke: 2pt + marka-acik)
#v(6mm)
#block(width: 108mm, text(size: 12pt, fill: soluk)[
  Bir HEC-RAS projesinde Q50 senaryosunu otomatik belirleyen ve gerçek proje
  sonuçlarından maksimum su derinliği haritası üreten Python uygulamasının
  üretim ve doğrulama sürecinin tam kaydı.
])

#v(1fr)
#line(length: 100%, stroke: 0.5pt + cizgi)
#v(3mm)
#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: 6mm,
  [
    #text(size: 7.8pt, fill: soluk, tracking: 0.1em)[HAZIRLAYAN]\
    #text(size: 10pt, weight: "semibold")[Emirhan Fırtına]
  ],
  [
    #text(size: 7.8pt, fill: soluk, tracking: 0.1em)[KURUM]\
    #text(size: 10pt, weight: "semibold")[Atinen Mühendislik]
  ],
  [
    #text(size: 7.8pt, fill: soluk, tracking: 0.1em)[TARİH]\
    #text(size: 10pt, weight: "semibold")[29 Ağustos 2026]
  ],
)
#v(4mm)
#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: 6mm,
  [
    #text(size: 7.8pt, fill: soluk, tracking: 0.1em)[UYGULAMA]\
    #text(size: 10pt, weight: "semibold")[q50depth 1.0.0]
  ],
  [
    #text(size: 7.8pt, fill: soluk, tracking: 0.1em)[TEKNOLOJİ]\
    #text(size: 10pt, weight: "semibold")[Python 3.10+ · HEC-RAS 6.6]
  ],
  [
    #text(size: 7.8pt, fill: soluk, tracking: 0.1em)[ÇIKTI]\
    #text(size: 10pt, weight: "semibold", font: "Menlo")[OUTPUT/q50_depth.tif]
  ],
)

// ======================================================================
// İÇİNDEKİLER
// ======================================================================
#pagebreak()
#{
  set page(header: none)
  text(size: 15pt, weight: "bold")[İçindekiler]
  v(3mm)
  line(length: 100%, stroke: 0.8pt + marka)
  v(4mm)
  show outline.entry.where(level: 1): it => {
    v(7pt, weak: true)
    text(weight: "semibold", size: 10.5pt, it)
  }
  show outline.entry.where(level: 2): it => text(size: 9.6pt, fill: soluk, it)
  outline(title: none, depth: 2, indent: 1.2em)
}

// ======================================================================
= Bu belge nedir, nasıl okunur

Bu rapor, case study belgesinin 6. maddesinde istenen teknik açıklamanın
genişletilmiş biçimidir: uygulamanın *hangi adımlardan geçerek* çıktıyı
ürettiğini ve her adımın *nasıl doğrulandığını* anlatır. Belgenin 7. maddesinde
istenen yapay zekâ beyanı @ai bölümündedir.

== Kanıt kuralı

Bu raporda geçen her sayı ve her teknik iddia, bir komutun gerçekten
çalıştırılmasıyla üretilmiştir. Komutların ham çıktısı `docs/rapor/kanit/`
klasöründe metin dosyası olarak durur ve bu PDF derlenirken *o dosyalardan
okunur*; metin elle kopyalanmamıştır. Her kanıt bloğunun sağ alt köşesinde
hangi dosyadan geldiği yazar. Sayfaya sığmayan uzun satırlar `↵` işaretiyle
katlanır; hiçbir karakter atılmaz. Tek düzenleme, kişisel dizin adlarının
`<masaustu>` ve `<gecici>` ile kısaltılmasıdır.

#not-kutu[
  *Üç kanıt sınıfı ayrı ayrı işaretlenmiştir.*
  #v(3pt)
  #text(fill: iyi)[*(A) Yeniden üretilebilir.*] Bu makinede, bu belge
  hazırlanırken komut çalıştırılarak ölçüldü. Kanıt bloğu ham çıktıdır.
  #v(2pt)
  #text(fill: soluk)[*(B) Kod içinde sabitlenmiş.*] Otomatik testle korunuyor;
  test adı verilir.
  #v(2pt)
  #text(fill: kotu)[*(C) Başka bir makinede ölçüldü, burada tekrarlanamaz.*]
  HEC-RAS Windows programı olduğu için motorun çalıştırılmasına ilişkin
  bulgular bu sınıfa girer. Bu bulgular @cokme bölümünde toplanmış ve
  kaynakları açıkça belirtilmiştir — hiçbiri (A) sınıfıymış gibi sunulmamıştır.
]

== Denetim ortamı

Aşağıdaki bütün ölçümler tek bir makinede, tek bir sanal ortamda yapıldı.

#kanit(
  "Denetimin yapıldığı makine, yorumlayıcı ve kütüphane sürümleri.",
  "kanit/A1-ortam.txt",
)

Uygulamanın kendisi üç kütüphaneye dayanır: `h5py` (HEC-RAS sonuç dosyası),
`numpy` (ızgara), `rasterio` (GeoTIFF). HEC-RAS'ı çalıştırmak için gereken
`ras-commander` yalnızca Windows teslim ortamında zorunludur ve tek bir modülde
kullanılır.

== Girdi verisi

#kanit(
  "Teslim edilen veri setinin envanteri. Belgede bildirilen konum doğrulandı.",
  "kanit/A2-veri-envanteri.txt",
)

176 dosya, 280 MB. Belgenin 2. maddesi veri konumunu
`CASE_DATA\\AKA_AFY_BAY_INPINAR_1\\1_Modeller` olarak veriyor; envanterdeki
klasör yapısı bununla birebir örtüşüyor.

// ======================================================================
= Veri setinin keşfi <kesif>

Belgenin 2. maddesi hazır bir maksimum derinlik çıktısı sağlanmadığını söylüyor
ve adayın dosya ilişkilerini kendisinin belirlemesini bekliyor. İlk iş, sonuç
dosyasının gerçekten ne içerdiğini ölçmekti.

== Sonuç dosyasında hazır derinlik var mı?

Plan sonuç dosyası `A_A_B_INPINAR.p05.hdf` bir HDF5 arşividir. İçindeki bütün
yollar tarandı ve adında "depth" geçen her veri seti listelendi.

#kanit(
  [Sonuç dosyasındaki 439 yolun tamamı tarandı. Tek "depth" eşleşmesi bir sınır
   koşuludur (mansap normal derinliği), derinlik rasteri değildir.],
  "kanit/A3-hdf-yollari.txt",
)

Bu, raporun en belirleyici bulgusudur: *HEC-RAS hazır bir maksimum derinlik veri
seti üretmiyor.* Derinlik türetilmek zorunda.

== Elde ne var: maksimum su kotu

#kanit(
  [Özet çıktı veri setleri ve `Maximum Water Surface`'ın içeriği. Birim ve
   satır adları HDF özniteliklerinden okundu, varsayılmadı.],
  "kanit/A4-maksimum-su-kotu.txt",
)

Veri seti $2 times 5667$: birinci satır su yüzeyi *kotu* (m), ikinci satır o
kotun görüldüğü zaman (gün). `Rows Variables` özniteliği bunu kendisi
söylüyor — `[WSEL, Time]` — yani sıralama tahmin edilmedi.

Aynı kanıt bloğunun son satırı ileride kritik olacak bir gerçeği de gösteriyor:
hiç ıslanmamış hücreler için HEC-RAS maksimum su kotunu *hücrenin kendi taban
kotu* olarak raporluyor. Bu, su değildir; @kuru bölümünde ele alınıyor.

== Ağın gerçek hücreleri

Hücre dizileri 5667 uzunluğunda, ama bunların hepsi gerçek hücre değil.

#kanit(
  [Hayalet hücrelerin sayımı ve ıslanma filtresinin hücre düzeyindeki etkisi.
   Kimlik alanları da dosyadan okundu.],
  "kanit/B1-mesh-ve-kimlik.txt",
)

HEC-RAS hücre dizilerini sınırda "hayalet" hücrelerle dolduruyor: üçten az köşe
noktası ve NaN taban kotu taşıyorlar. 5667 girdinin *197'si* hayalet, *5470'i*
gerçek hücre. Uygulamanın `Mesh.real_cells` özelliği bu iki koşulu birlikte
uyguluyor; ilgili test `test_ghost_cells_are_excluded`.

// ======================================================================
= Q50 senaryosunun belirlenmesi <secim>

Belgenin 4. maddesi Q50'nin manuel yazılmasını veya kullanıcıya seçtirilmesini
yasaklıyor. Doğru planı bulmak ilk bakışta bir metin araması gibi görünüyor;
uygulamada iki ayrı tuzak barındırıyor.

== Plan listesi nereden okunuyor

#kanit(
  [Plan listesinin kaynağı ve diskteki plan dosyaları. `Backup.p01`, proje
   dosyasında *bildirilmediği hâlde* p05 ile birebir aynı kimliği taşıyor.],
  "kanit/C1-plan-kaynagi.txt",
)

Kanıtın son iki bloğu tuzağı tek başına anlatıyor: `Backup.p01` ile
`A_A_B_INPINAR.p05` dosyalarının ilk satırları aynı — `Plan Title=A_A_B_INPINAR_Q50`,
`Short Identifier=Q50`. Klasörü `*.p??` deseniyle tarayan bir seçici *iki* tam
eşleşme bulur ve hangisinin doğru olduğunu bilemez. Ne kadar iyi bir kalıp
yazılırsa yazılsın bu ayrım yapılamaz, çünkü metin gerçekten aynıdır.

#not-kutu[
  *Alınan karar:* plan listesi klasör taramasıyla değil, `A_A_B_INPINAR.prj`
  dosyasındaki `Plan File=` satırlarından okunur. Proje dosyası yalnızca
  p01–p07'yi bildirir; `Backup.p01` orada yer almadığı için hiç değerlendirmeye
  girmez. Tuzak bir istisna ile değil, *doğru kaynağı seçerek* çözülür.
  İlgili test: `test_plan_list_comes_from_the_project_file_not_the_folder`.
]

Proje dosyasında `Current Plan=p05` de yazıyor ve bu seçimle uyuşuyor. Bu alan
*seçim ölçütü olarak kullanılmadı*: projeyi en son kimin nasıl kapattığına bağlı
bir durumdur, belgenin istediği otomatik belirleme değildir. Yalnızca çalışma
kaydına "seçimle uyuşuyor" notu olarak düşülür; üretim koşusunun tam kaydı
@dogrulama bölümündedir.

== Alt dize araması neden yanlış

#kanit(
  [Sınır kontrollü kalıp ile naif alt dize aramasının aynı girdiler üzerinde
   karşılaştırılması. "FARK" işaretli satırlar naif yaklaşımın hata verdiği
   yerlerdir.],
  "kanit/C2-regex.txt",
)

Dört ayrım noktası var. Naif arama `Q500` ve `Q5000` içinde `Q50` görüp yanlış
eşleşiyor; buna karşılık `Q050` yazımını kaçırıyor. Kalıptaki `0*` sıfır
dolgusunu kabul ederken, iki yandaki `(?<![0-9])` ve `(?![0-9])` komşu rakamı
reddediyor.

Bu davranış `TestScenarioPattern` sınıfındaki 13 testle sabitlenmiştir
(@testler); ayrıca gerçek veri üzerinde `--scenario Q050` komutu da p05'i seçer.

== Sıfır ve çoklu eşleşme

Hiçbir durumda "ilkini al" davranışı yoktur. Bu projede `--scenario Q500` iki
planla eşleştiği için bilinçli olarak reddedilir; kanıtı @hata bölümündedir.

// ======================================================================
= HEC-RAS ile etkileşim <hecras>

HEC-RAS bir Windows programıdır; bu, boru hattındaki tek platforma bağlı adımdır
ve `q50depth/compute.py` modülüne hapsedilmiştir.

== Kütüphane imzaları hatırdan değil, paketten okundu

Belgenin 2. maddesi `ras-commander` kütüphanesini öneriyor. Kütüphanenin
fonksiyon adları ve parametreleri dokümandan veya hatırdan yazılmadı; paket
kurulup `inspect.signature` ile okundu. Aşağıdaki blok bu okumanın *bu belge
hazırlanırken tekrarlanmış* hâlidir.

#kanit(
  [`ras-commander` 0.99.1'in gerçek imzaları, kurulu paketten okundu.],
  "kanit/H1-ras-commander.txt",
)

Bir adım daha atıldı: uygulamanın kullandığı her parametre adının imzada
gerçekten bulunup bulunmadığı tek tek sınandı.

#kanit(
  [Uygulamanın kullandığı parametre adları kütüphanenin imzasıyla karşılaştırıldı;
   `RAS66.HECRASController` ProgID'sinin kütüphanede desteklendiği doğrulandı.
   Altta `compute.py`'nin ilgili bölümü.],
  "kanit/H2-api-uyum.txt",
)

Kullanılan iki yol şudur:

#tablo(
  ([Yol], [Çağrı], [Ne yapar]),
  (
    ([Varsayılan], raw("RasCmdr.compute_plan()"), [HEC-RAS komut satırı çalıştırıcısı]),
    ([`--runner controller`], raw("RasControl.run_plan()"), [`RAS66.HECRASController` COM otomasyonu — arayüzün kullandığı arabirim]),
  ),
  sutunlar: (auto, auto, 1fr),
)

== Kaynak bütünlüğü: iddia değil, kanıt

Belgenin 4. maddesi orijinal proje dosyalarının değiştirilmemesini şart koşuyor.
HEC-RAS bir planı çalıştırdığında proje klasörüne yazar; bu yüzden uygulama proje
ağacını önce bir çalışma dizinine kopyalar ve hesabı orada yapar.

"Değiştirmedim" demek yetmez. Uygulama çalışma başında ve sonunda kaynak
klasörün SHA-256 parmak izini çıkarıp karşılaştırır. Peki bu kontrol gerçekten
bir şey yakalıyor mu? Aşağıdaki kontrollü deney bunu sınıyor: gerçek veri
*kopyalanıyor*, kopya üzerinde önce hiçbir şey değiştirilmiyor, sonra tek bir
bayt ekleniyor, sonra bir dosya siliniyor.

#kanit(
  [Bütünlük kontrolünün boş bir vaat olmadığının kanıtı. Deney bir kopya
   üzerinde yapıldı; orijinal `CASE_DATA` klasörüne yazılmadı.],
  "kanit/D2-butunluk.txt",
)

Tek baytlık değişiklik de, silinen dosya da yakalandı. `--integrity full` her
dosyanın SHA-256 özetini alır; `fast` yalnızca boyut ve zaman damgasına bakar.

== Teslim edilen projenin durumu

Proje neyi bildiriyor, her plan neye ihtiyaç duyuyor, diskte ne var — bu üçünün
ayrıştığı noktalar `tools/audit_project.py` ile tarandı.

#kanit(
  [Denetim aracının çıktısı: sekiz engelleyici bulgu.],
  "kanit/veri-denetimi-ciktisi.txt",
  satir: (0, 20),
)

Sekiz engelleyicinin özeti: p03 bildirilmemiş bir akış dosyası kullanıyor;
p04–p07 giriş debisi DSS'ini çözemiyor (p05 `.\\_CBS\\...` altında arıyor,
klasörün diskteki adı `2_CBS`); g01–g03 geometri dosyalarında ön işlenmiş
tablolar yok. Ayrıca dört akış dosyasının hiçbirinde hidrograf gömülü değil.
Tam liste `docs/VERI-DENETIMI.md` dosyasındadır.

Uygulama bu eksikleri yalnızca çalışma kopyasında onarır ve her onarımı çalışma
kaydına yazar. Çözülmeyen bir giriş dosyası için proje ağacında aynı adlı dosya
aranır; *tam bir tane* bulunursa modelin beklediği yola kopyalanır. Hiç ya da
birden fazla aday çıkarsa tahmin yürütülmez, anlamlı hatayla durulur — yanlış
hidrografla hesaplanmış bir taşkın haritası, hesaplanmamış olmasından kötüdür.
İlgili testler `test_references.py` içinde yedi adettir.

// ======================================================================
= Derinlik ızgarasının üretimi <derinlik>

== Temel formül ve ızgaranın çözünürlüğü

$ "derinlik"("piksel") = "pikseli kaplayan hücrenin maksimum su kotu" - "o pikseldeki arazi kotu" $

Izgara hücre çözünürlüğünde değil *arazi çözünürlüğünde* kurulur (bu veri
setinde 0,1 m), çünkü bir HEC-RAS 2D hücresi düz değildir; içinde alt-ızgara
topografya taşır. Pencere, arazi rasterinin kendi piksel ızgarasına hizalanır
(`_grid_aligned_to`), böylece arazi yeniden örneklenmeden okunur.

== Hücre çokgenleri

`Cells FacePoint Indexes` bir hücrenin köşelerini verir ama halka sırasında
vermez. Köşeler hücre merkezine göre açıya sıralanır; HEC-RAS 2D hücreleri
dışbükey olduğu için bu sıralama tam olarak çokgen sınırıdır.

== Arazi ve üzerindeki kot değişiklikleri

Geometri `merge.Clone` arazisi üzerine kuruludur. RASMapper arazi katmanı bir
*çifttir*: `.vrt` kot ızgarasını, `.hdf` ise üzerine çizilen değişiklikleri
tutar. Bu değişiklikler `.vrt`'ye gömülü değildir; RASMapper onları anlık uygular.

#kanit(
  [Arazi katmanının çözümlenmesi ve kot değişikliklerinin sayımı — 69 poligon,
   hepsi `Add` tipinde, hepsi +20 m, hepsi `buildings` katmanında.],
  "kanit/B3-arazi.txt",
)

Yalnızca `.vrt` okunursa harita binaların üstüne metrelerce su boyar. Etkisi
@carpim bölümünde ölçülüyor.

== Islanmamış hücreler <kuru>

Hiç ıslanmayan bir hücre için HEC-RAS maksimum su kotunu hücrenin kendi taban
kotu olarak raporlar. Tabanı yükseltilmiş bir bina üzerinde oturan kuru hücre,
binanın kaplamadığı şeritte metrelerce sahte derinlik üretir. Bu yüzden yalnızca

#align(center, text(font: "Menlo", size: 9pt)[maksimum su kotu > hücre taban kotu])

olan hücreler boyanır (`Mesh.wet_cells`). Filtre 5470 gerçek hücrenin 4165'ini
ıslak sayıyor.

== İki düzeltmenin ölçülmüş etkisi <carpim>

İki düzeltme de "gerekli" diye değil, *ölçülerek* konuldu. Aşağıdaki deney
dördünü birden kurar: bina kot değişikliği açık/kapalı × kuru hücre filtresi
açık/kapalı.

#kanit(
  [İki düzeltmenin tam çarpım tablosu. Son satır teslim edilen yapılandırmadır.],
  "kanit/B5-carpim-tablosu.txt",
)

Tablo, iki düzeltmenin *farklı belirtileri* iyileştirdiğini gösteriyor:

#tablo(
  ([Düzeltme], [Neyi düzeltiyor], [Ölçülen etki]),
  (
    ([Bina kot değişikliği], [ortalama derinlik], [3,391 m #sym.arrow 0,130 m]),
    ([Kuru hücre filtresi], [maksimum derinlik], [19,611 m #sym.arrow 1,625 m]),
    ([İkisi birlikte], [2 m üstü piksel sayısı], [87.012 #sym.arrow 0]),
  ),
  sutunlar: (auto, auto, 1fr),
)

Bina kot değişikliği uygulanmadığında ortalama derinlik 3,391 m çıkıyor; bu, 70
dakikalık ve tepe debisi 1,69 m³/s olan bir olay için fiziksel olarak imkânsız.
Kuru hücre filtresi olmadan ise en derin piksel 19,611 m'ye çıkıyor — bu sayı
tesadüfi değil, binalara eklenen 20 m'nin ta kendisidir.

#not-kutu[
  *Daha önceki bir sürümdeki düzeltme.* Bu raporun HTML sürümünde 3,37 m değeri
  yalnızca bina kot değişikliğine atfedilmişti. Yukarıdaki ölçüm, o değerin
  *iki düzeltme de kapalıyken* geçerli olduğunu gösteriyor; bina düzeltmesi tek
  başına ortalamayı 0,130 m'ye indiriyor. Aynı şekilde "36–54 piksel, en fazlası
  19,96 m" ifadesi yerine ölçülen değerler 36 piksel ve 19,611 m'dir. Rakamlar
  bu raporda ölçüme göre düzeltilmiştir.
]

Bu iki kuralı koruyan testler:

#block(inset: (left: 6pt))[
  #set par(justify: false)
  #set text(size: 9pt)
  - `test_building_modification_is_applied_to_the_terrain`
  - `test_without_the_dry_cell_rule_the_building_would_flood`
  - `test_dry_cell_on_a_raised_footprint_is_not_wet`
  - `test_building_inside_a_wet_cell_stays_dry`
]

== Koordinat sistemi

CRS, sonuç dosyasının kök `Projection` özniteliğindeki WKT'den okunur. Elle
`EPSG:32636` yazmak cazipti ve yanlış olurdu.

#kanit(
  [WKT'nin tamamı ve `to_epsg()` sonucu. Projeksiyon merkez meridyen 30°E ile
   Transverse Mercator, ancak ölçek faktörü 1,0; UTM 36N 0,9996 kullanır.],
  "kanit/B2-crs-ve-ortalama.txt",
)

Model UTM 36N *değildir* ve `to_epsg()` haklı olarak boş döner. Doğru kaynak,
projenin kendi WKT'sidir. Aynı kanıt bloğu, hücre bazlı 0,117 m değerinin nasıl
elde edildiğini de gösteriyor: ıslak hücrelerin ortalaması 0,1534 m, kuru
hücreler sıfır sayılarak tüm gerçek hücrelere yayıldığında 0,1168 m.

== Denenip ölçülerek kaldırılan bir yöntem

Taşkın kenarının tırtıklı görünümünü yumuşatmak için ıslak hücre merkezleri
arasında doğrusal enterpolasyonla eğimli bir su yüzeyi denendi. Sonuç fiziksel
olarak imkânsızdı: maksimum derinlik 20,4 m, 99. yüzdelik 11,4 m. Sebep, ıslak
hücrelerin kopuk kümeler hâlinde olması ve üçgenlemenin vadinin bir yamacından
diğerine uzanmasıydı. Seçenek "opsiyonel" diye teslime konmadı; kaldırıldı ve
gerekçesi README'ye yazıldı.

// ======================================================================
= Çıktının doğrulanması <dogrulama>

"p05'i seçtim" bir doğrulama değildir. Doğrulama dört ayrı koldan yapıldı:
kimlik zinciri, künye, bağımsız araç, ve girdiyle örtüşme.

== Kimlik zinciri

Uygulama çıktı yazmadan önce sekiz kontrol çalıştırır ve sonuçları çalışma
kaydına basar. Bir kontrol düşerse çıktı yazılmaz (çıkış kodu 8).

#kanit(
  [Üretim koşusunun tamamı: plan listesi, seçim, veri notları, sonuç özeti,
   sekiz doğrulama kontrolü ve bütünlük raporu.],
  "kanit/G1-son-kosu.txt",
)

== GeoTIFF künyesi ve bağımsız araç

Künye GeoTIFF'in içine gömülür, böylece dosya adına güvenmek gerekmez. Aşağıdaki
kontrol *uygulamanın kendi kütüphanesiyle değil*, GDAL'in kendi komut satırı
aracı `gdalinfo` ile yapılmıştır — yani çıktıyı üreten kodun dışından bakılmıştır.

#kanit(
  [`gdalinfo` ile bağımsız doğrulama: künye alanları ve bandın istatistikleri.
   `STATISTICS_VALID_PERCENT=3.136`, 413.858 / (4788 × 2756) oranına eşittir.],
  "kanit/F1-gdalinfo.txt",
  satir: (14, 45),
)

GDAL'in kendi hesapladığı maksimum (1,6254 m) ve ortalama (0,1295 m) değerleri,
uygulamanın raporladığı 1,625 m ve 0,130 m ile örtüşüyor.

== Girdi hidrografıyla örtüşme

Bir haritanın doğru olaya ait olduğunun en güçlü göstergesi, girdisiyle
tutarlılığıdır. Planın okuduğu DSS serisi doğrudan okundu.

#kanit(
  [`u05` akış dosyasının okuduğu DSS serisi ve ordinatların tamamı.],
  "kanit/C3-hidrograf.txt",
)

Üç bağımsız teyit birden çıkıyor:

+ *Süre.* 15 ordinat × 5 dakika = 70 dakika. Sonuç dosyasının bildirdiği
  simülasyon penceresi `02May2025 01:00:00 to 02May2025 02:10:00`, yani tam 70
  dakika.
+ *Etiket.* DSS yolunun F parçası (`.../5Minute/Q50/`) *Q50* yazıyor. Plan
  seçimi bu bilgiye bakmadan yapıldı, ama sonuç onu doğruluyor.
+ *Büyüklük.* Tepe debi 1,69 m³/s. Bu ölçekte bir olay için 1,6 m maksimum
  derinlik makul; 3,4 m ortalama derinlik (bkz. @carpim) değildir.

== Senaryoya özel davranmama

Boru hattının Q50'ye özel bir davranış barındırmadığı, aynı kodun başka
tekerrürlerle çalıştırılmasıyla sınandı.

#kanit(
  [Aynı komut, yalnızca `--scenario` değiştirilerek üç kez.],
  "kanit/F4-cok-senaryo.txt",
)

Islak alan tekerrür büyüdükçe tek yönlü artıyor (413.858 → 465.321 → 690.430
piksel) ve her senaryo kendi planına gidiyor (p05, p06, p07).

== Referans çıktı ile karşılaştırma

Toplantıda gösterilen görüntüde kanal boyunca kesintisiz, pürüzsüz bir şerit
var; üretilen haritada ise parçalı taşkın lekeleri. İlk okuma "bizim harita
eksik" yönündeydi.

Bu soru gözle değil, ölçülerek kapatıldı: projenin 1D geometrisi
(`A_A_B_INPINAR.g01`) doğrudan geometri dosyasından okunup rasterin kendi
coğrafi ölçeğine bindirildi. İşi yapan araç `tools/reference_overlay.py`
teslim paketindedir ve figürü yeniden üretir.

#kanit(
  [Bindirme aracının çıktısı. Nehir ekseni 47 noktadan oluşuyor; geometri 24
   kesit bildiriyor, bunların 12'sinin GIS kesit çizgisi var ve 12'si de
   rasterin sınırları içinde kalıyor.],
  "kanit/F2-referans-bindirme.txt",
)

#figure(
  image("../referans_karsilastirma.png", width: 100%),
  caption: [
    Üstte toplantıda gösterilen referans görüntü, altta üretilen Q50 maksimum
    derinlik haritası. Alt panele projenin 1D geometrisi bindirilmiştir: nehir
    ekseni (mavi) ve 12 kesit çizgisi (turkuaz). Üst paneldeki görüşme
    penceresi, üçüncü bir kişinin görüntüsünü içerdiği için maskelenmiştir;
    harita alanına dokunulmamıştır.
  ],
)

Nehir ekseni referanstaki şeridi birebir izliyor: aynı menderesler, aynı
başlangıç ve bitiş noktası; sağ uçtaki huni biçimi de son kesitlerin
genişlemesinden geliyor. *Yani o pürüzsüz şerit su değil, RASMapper görünümünde
derinlik katmanının altında duran 1D nehir geometrisidir.* Suyu temsil eden koyu
lekeler ise üretilen haritadaki ıslak alanlarla aynı konumdadır.

Karşılaştırmanın sınırı açıktır: toplantı görüntüsünün coğrafi referanslı bir
kopyası elde bulunmadığından karşılaştırma piksel bazında değil, biçim ve konum
düzeyindedir.

== Çıktıya bakıldı

Üretmek ile doğrulamak aynı şey değildir. Çıktı `tools/preview.py` ile çizildi
ve dağılımına bakıldı.

#kanit(
  [Önizleme aracının ölçtükleri: ızgara, kapsam, ıslak alan, yüzdelikler.],
  "kanit/F3-onizleme.txt",
)

#figure(
  image("../q50_depth_preview.png", width: 100%),
  caption: [
    Q50 maksimum su derinliği (plan p05). Sol: arazi üzerine bindirilmiş derinlik
    haritası. Sağ: derinlik dağılımı (logaritmik ölçek). Islak alan 4.139 m²,
    medyan derinlik 0,098 m, 99. yüzdelik 0,516 m. Su, arazideki dere koridorunu
    takip ediyor.
  ],
)

// ======================================================================
= Test süreci <testler>

== Ne kadar test var, neyi kapsıyor

#kanit(
  [Testlerin çalıştırılması ve modül bazında satır kapsamı.],
  "kanit/E1-kapsam.txt",
)

80 test, `q50depth` paketinin 1187 satırının %80'ini çalıştırıyor. Kapsamın en
düşük olduğu iki modül anlamlıdır ve gizlenmemelidir:

#tablo(
  ([Modül], [Kapsam], [Neden]),
  (
    (raw("compute.py"), [%56], [HEC-RAS'ı çalıştıran modül; bu makinede HEC-RAS yok, çalıştırma yolu ancak Windows'ta yürütülebiliyor]),
    (raw("cli.py"), [%59], [Uçtan uca akışın büyük kısmı gerçek veriyle sınanıyor; HEC-RAS gerektiren dallar açıkta kalıyor]),
  ),
  sutunlar: (auto, auto, 1fr),
)

Geri kalan modüllerin tamamı %77 ve üzerinde; derinlik hesabı (`depth.py`) %97,
plan seçimi (`project.py`) %93.

== Testlerin tam listesi

Test adları neyi iddia ettiklerini söyleyecek biçimde yazılmıştır; liste bu
yüzden aynı zamanda bir davranış belgesidir.

#kanit(
  [Toplanan 80 testin tamamı ve dosya başına dağılımı.],
  "kanit/E2-test-envanteri.txt",
)

== Hata yolları ve çıkış kodları <hata>

Belgenin 3. maddesi, eksik veya beklenmeyen bir proje durumunun uygulamayı
kontrolsüz kapatmamasını istiyor. Beklenebilir her hata tek satırlık bir mesaj,
çoğu zaman bir ipucu ve hata sınıfına özgü bir çıkış kodu üretir. Yığın izi
yalnızca gerçek bir yazılım hatasında görünür.

#kanit(
  [Beş hata durumu gerçekten çalıştırıldı; her birinin mesajı ve çıkış kodu.],
  "kanit/E3-hata-yollari.txt",
)

Sonuç dosyası bulunmayan bir proje için ayrı bir kontrollü deney yapıldı: proje
metin dosyaları bir kopyaya alındı, `.hdf` dosyaları bilinçli olarak dışarıda
bırakıldı.

#kanit(
  [Hesaplanmamış plan durumu; çıkış kodu 6.],
  "kanit/E4-eksik-sonuc.txt",
)

Çıkış kodu haritası `q50depth/errors.py` içinde istisna sınıflarına bağlıdır:

#tablo(
  ([Kod], [Durum], [Kod], [Durum]),
  (
    ([0], [Başarılı], [6], [Sonuç dosyası eksik ya da yarım]),
    ([2], [Argüman hatası], [7], [Arazi çözülemedi]),
    ([3], [Proje bulunamadı], [8], [Senaryo doğrulaması düştü]),
    ([4], [Senaryo sıfır/çoklu eşleşti], [70], [Beklenmeyen hata (kayda tam iz)]),
    ([5], [HEC-RAS başlatılamadı / hesap başarısız], [130], [Kullanıcı iptali]),
  ),
  hizalar: (right, left, right, left),
  sutunlar: (auto, 1fr, auto, 1fr),
)

== Tekrarlanabilirlik

Belgenin 4. maddesi, teslim edilen talimatlar izlenerek çıktının yeniden
üretilebilmesini istiyor. Bu, "çalışıyor" demekten daha kuvvetli biçimde
sınandı: aynı komut iki kez çalıştırıldı ve piksel verisinin SHA-256 özeti
karşılaştırıldı.

#kanit(
  [İki bağımsız koşunun piksel verisi ve teslim edilen dosyayla karşılaştırması.],
  "kanit/D1-tekrarlanabilirlik.txt",
)

İki koşunun özeti aynı; teslim edilen `OUTPUT/q50_depth.tif` ile de aynı.
Künyede değişen tek alan `COMPUTED_AT` — koşunun zaman damgası. Yani çıktı
bit düzeyinde belirlenimlidir.

== Testlerin teslim edilen çıktıya dokunmaması

Bu denetimde bulunan tek gerçek kusur burada ortaya çıktı ve düzeltildi.
Teslim kalemi olan `OUTPUT/run.log`, haritayı üreten koşunun değil, bir *pytest*
koşusunun yazdığı altı satırlık hata kaydıydı: `test_missing_project_exits_cleanly`
`--output` vermediği için varsayılan `OUTPUT/run.log` yoluna yazıyor ve her test
koşusu teslim kalemini eziyordu. Test kendi geçici dizinine yönlendirildi, kayıt
gerçek üretim koşusundan yeniden üretildi; @dogrulama bölümündeki kanıt bloğu
o koşunun kaydıdır.

// ======================================================================
= HEC-RAS motorunun çalışmaması <cokme>

#uyari[
  *Kanıt sınıfı (C).* Bu bölümdeki bulgular Windows 11 + HEC-RAS 6.6 üzerinde
  29 Ağustos 2026'da ölçülmüştür. HEC-RAS bir Windows programı olduğu için bu
  ölçümler bu raporun hazırlandığı makinede tekrarlanamaz. HEC-RAS'ın ham hesap
  günlüğü dosyası teslim paketinde *yoktur*; aşağıdaki hata metni o oturumdan
  aktarılmıştır. Bu bölümdeki hiçbir ifade, ölçülmüş kanıt bloklarıyla aynı
  düzeyde sunulmamaktadır.
]

Belgenin 3. maddesi haritanın HEC-RAS proje sonuçları kullanılarak üretilmesini
istiyor; uygulama bunu yapıyor. Planı yeniden hesaplama yolu da kodlanmıştır,
ancak teslim edilen veri o kurulumda hesaplanamadı.

@hecras bölümündeki onarımlardan sonra HEC-RAS geometriyi sorunsuz işliyor,
ardından unsteady motoru başlar başlamaz düşüyor:

#block(
  width: 100%, inset: (x: 9pt, y: 8pt), fill: zemin,
  stroke: (left: 2pt + rgb("#b45309")), radius: (right: 2pt),
  { set par(justify: false, leading: 0.5em)
    text(font: "Menlo", size: 7.4pt)[```
Performing Unsteady Flow Simulation  HEC-RAS 6.6 September 2024
forrtl: severe (157): Program Exception - access violation
Image              PC                Routine            Line   Source
RasUnsteady.exe    00007FF64F701486  READ_UN_HDF_STRUC  330  Read_UN_HDF_STRUC_GRP.for
RasUnsteady.exe    00007FF64F8C0CC3  SNETREAL2          179  Snetreal2.for
RasUnsteady.exe    00007FF64F9D561A  UNET_START         144  Unet_start.for
Error with program: RasUnsteady.exe  Exit Code = 157
```] },
)
#v(-3pt)
#block(width: 100%, text(size: 8.2pt, fill: soluk)[
  Windows oturumundan aktarılan hata metni — *ölçülmüş kanıt bloğu değildir.*
])

Neden, tahminle değil, tek tek değişken sabitlenerek daraltıldı:

#tablo(
  ([Deneme], [Sonuç]),
  (
    ([Teslim edildiği gibi (yalnız DSS yolu onarılmış)], text(fill: kotu)[Çöküyor]),
    ([\+ proje tek plana indirgenmiş], text(fill: kotu)[Çöküyor]),
    ([\+ hidrograf akış dosyasına gömülmüş, DSS bağımlılığı kaldırılmış], text(fill: kotu)[Çöküyor]),
    ([\+ eksik geometri tabloları geri konmuş, koşu sonrası yerinde olduğu doğrulanmış], text(fill: kotu)[Çöküyor]),
    ([\+ `RasProcess.exe CompleteGeometry` çalıştırılmış], text(fill: kotu)[Çöküyor]),
    ([\+ RASMapper kapatılmış, arazi zaman damgası hizalanmış], text(fill: kotu)[Çöküyor]),
    ([*HEC-RAS arayüzünde elle açılıp çalıştırılmış*], text(fill: kotu)[*Çöküyor*]),
  ),
  sutunlar: (1fr, auto),
)

Son satır belirleyicidir: çöküş uygulama kaynaklı değildir, aynı hata proje
HEC-RAS arayüzünde elle açılıp çalıştırıldığında da oluşmaktadır. Geriye kalan
açıklama, modelin 2D hidrolik bağlantılarında HEC-RAS'ın kendi hatası ya da
teslim paketinde henüz tespit edilememiş bir eksiktir. Doğrulanabilir bir cevap
üretilemediği için konu tahminle kapatılmamıştır.

Uygulamanın bu duruma verdiği tepki önemlidir: çalıştırıcı kütüphane hesabı
"başarılı" olarak raporladı, uygulama buna *inanmadı*, sonuç dosyasını kendisi
açtı, yarım olduğunu gördü ve HEC-RAS'ın kendi hesap günlüğünü alıntılayarak
durdu. Bu davranış üç testle sabitlenmiştir:

#block(inset: (left: 6pt))[
  #set par(justify: false)
  #set text(size: 9pt)
  - `test_verify_results_rejects_a_stub_file_and_quotes_the_hec_ras_log`
  - `test_verify_results_reports_a_run_that_wrote_nothing`
  - `test_verify_results_accepts_a_finished_run`
]

Bu nedenle teslim edilen çıktı, projenin *kendi hesaplanmış sonuçlarından*
üretilmiştir. Hazır bir raster kopyalanmamıştır; harita her çalıştırmada
HEC-RAS'ın sonuç dosyasından yeniden hesaplanır. GeoTIFF künyesindeki
`HEC_RAS_EXECUTED=False` etiketi bu durumu açıkça bildirir. Denenmemiş kalan iki
seçenek vardır ve dürüstlük gereği yazılmaktadır: `--cores 1` ve
`--runner controller`.

// ======================================================================
= Bilinen sınırlamalar ve kanıt boşlukları

Bu bölüm, raporun kendi zayıf noktalarını sayar.

#tablo(
  ([Konu], [Durum]),
  (
    ([HEC-RAS motorunun çalıştırılması], [Teslim edilen veriyle çöküyor; kanıtı (C) sınıfı, ham hesap günlüğü pakette yok. Bu boşluğu kapatmanın yolu, Windows'ta bir koşu daha yapıp `Compute Messages` dosyasını pakete eklemektir.]),
    ([Referans karşılaştırması], [Toplantı görüntüsünün coğrafi referanslı kopyası olmadığı için piksel bazında değil, biçim ve konum düzeyinde. Bindirme aracı yeniden üretilebilir (A).]),
    ([Su yüzeyi modeli], [Hücre içinde sabit kabul edilir; modelin çözdüğü büyüklük budur. Sonuç, taşkın kenarında tırtıklı bir sınırdır.]),
    ([Akış tipi], [Yalnızca 2D akış alanları işlenir. 1D kesit sonuçlarından derinlik ızgarası üretilmez; böyle bir planla çalıştırılırsa anlaşılır hata verilir.]),
    ([Arazi değişikliği tipi], [Yalnızca `Add` destekleniyor. Veri setinde yalnızca bu tip var (Kanıt 12); başka bir tiple karşılaşılırsa sessizce yanlış harita üretmek yerine durulur — `test_unsupported_modification_type_is_refused`.]),
    ([Kapsam boşluğu], [`compute.py` %56 kapsamda; HEC-RAS gerektiren dallar bu makinede yürütülemiyor.]),
  ),
  sutunlar: (auto, 1fr),
)

// ======================================================================
= Yapay zekâ kullanımı <ai>

Belgenin 7. maddesi, yapay zekâ destekli araç kullanımını serbest bırakmakta ve
hangi araçların hangi amaçlarla kullanıldığının belirtilmesini istemektedir.

Kullanılan araç: *Claude (Anthropic) — Opus 5*, Claude Code komut satırı ajanı.
Başka bir üretken yapay zekâ aracı kullanılmamıştır.

#tablo(
  ([Aşama], [Kullanım], [Doğrulama biçimi]),
  (
    ([Veri keşfi], [Sonuç dosyasındaki 439 HDF5 yolunun taranması, veri setlerinin bulunması], [Kod çalıştırılarak; şekil, birim ve değer aralıkları basıldı (Kanıt 3, 4)]),
    ([Analiz], [Bina kot değişikliği ve kuru hücre etkilerinin bulunması], [İki etki de çarpım tablosuyla ölçüldü (Kanıt 13)]),
    ([Kütüphane], [`ras-commander` API imzalarının çıkarılması], [Paket kuruldu, `inspect.signature` ile okundu (Kanıt 8, 9)]),
    ([Teşhis], [Motor çöküşünün nedeninin daraltılması], [Denetim aracı yazıldı; her hipotez ölçümle elendi]),
    ([Kod ve test], [Modüllerin ve 80 testin yazılması], [Gerçek veri üzerinde uçtan uca çalıştırıldı (Kanıt 15, 21)]),
    ([Bu rapor], [Metnin yazılması ve dizgisi], [Her sayı, rapor hazırlanırken komut çalıştırılarak yeniden ölçüldü; tutmayan üç değer düzeltildi]),
  ),
  sutunlar: (auto, 1fr, 1fr),
)

Uygulanan kurallar: doğrulanmamış hiçbir kütüphane çağrısı koda alınmadı; her
teknik iddia veriye karşı sınandı; çalışmayan bir özellik (eğimli su yüzeyi)
ölçülüp kaldırıldı; doğrulanamayan adımlar açıkça işaretlendi. Kodun tamamı
okunmuş, çalıştırılmış ve savunulabilir durumdadır.

// ======================================================================
= Kanıt dizini

Bu rapordaki her kanıt bloğunun ham çıktısı teslim paketinde
`uygulama/docs/rapor/kanit/` klasöründedir. Aşağıdaki tablo hangi dosyanın hangi
komutla üretildiğini gösterir; komutlar dosyaların ilk satırlarında da yazılıdır.

#tablo(
  ([Dosya], [Üreten komut]),
  (
    (raw("A1-ortam.txt"), raw("sw_vers; python -VV; import h5py,numpy,rasterio; git log -1")),
    (raw("A2-veri-envanteri.txt"), raw("find CASE_DATA -type f | wc -l; du -sh; uzantı sayımı")),
    (raw("A3-hdf-yollari.txt"), raw("h5py: f.visit ile 439 yolun taranması")),
    (raw("A4-maksimum-su-kotu.txt"), raw("h5py: Summary Output veri setleri ve öznitelikleri")),
    (raw("B1-mesh-ve-kimlik.txt"), raw("q50depth.results.load(); real_cells / wet_cells sayımı")),
    (raw("B2-crs-ve-ortalama.txt"), raw("q50depth.raster.crs_from_wkt(); to_epsg()")),
    (raw("B3-arazi.txt"), raw("q50depth.terrain.resolve(); modification sayımı")),
    (raw("B5-carpim-tablosu.txt"), raw("q50depth.depth.build() dört yapılandırmayla")),
    (raw("C1-plan-kaynagi.txt"), raw("grep 'Plan File=' A_A_B_INPINAR.prj; head Backup.p01")),
    (raw("C2-regex.txt"), raw("q50depth.project.scenario_pattern('Q50')")),
    (raw("C3-hidrograf.txt"), raw("q50depth.hydrograph.read_series()")),
    (raw("D1-tekrarlanabilirlik.txt"), raw("main.py iki kez; hashlib.sha256(piksel verisi)")),
    (raw("D2-butunluk.txt"), raw("q50depth.workspace.manifest/compare, kopya üzerinde")),
    (raw("E1-kapsam.txt"), raw("coverage run --source=q50depth -m pytest; coverage report")),
    (raw("E2-test-envanteri.txt"), raw("pytest --collect-only -q")),
    (raw("E3-hata-yollari.txt"), raw("main.py beş hatalı girdiyle; $? okunarak")),
    (raw("E4-eksik-sonuc.txt"), raw("main.py, .hdf içermeyen proje kopyası üzerinde")),
    (raw("F1-gdalinfo.txt"), raw("gdalinfo -stats OUTPUT/q50_depth.tif")),
    (raw("F2-referans-bindirme.txt"), raw("tools/reference_overlay.py --geometry ...g01")),
    (raw("F3-onizleme.txt"), raw("tools/preview.py OUTPUT/q50_depth.tif --terrain ...")),
    (raw("F4-cok-senaryo.txt"), raw("main.py --scenario Q50 | Q100 | Q1000")),
    (raw("G1-son-kosu.txt"), raw("pytest -q; main.py --use-existing-results --integrity full")),
    (raw("H1-ras-commander.txt"), raw("inspect.signature(rc.RasCmdr.compute_plan) vb.")),
    (raw("H2-api-uyum.txt"), raw("imza parametreleri ile compute.py kullanımının karşılaştırması")),
    (raw("veri-denetimi-ciktisi.txt"), raw("tools/audit_project.py --project CASE_DATA")),
  ),
  sutunlar: (auto, 1fr),
)

#v(8mm)
#line(length: 100%, stroke: 0.5pt + cizgi)
#v(2mm)
#text(size: 8.6pt, fill: soluk)[
  Emirhan Fırtına · 29 Ağustos 2026 · q50depth 1.0.0 · Typst ile dizilmiştir.
  Kaynak kod, çıktı, bağımlılık listesi, çalışma kaydı ve bu raporun kanıt
  dosyaları teslim klasöründeki `uygulama/` dizinindedir.
]
