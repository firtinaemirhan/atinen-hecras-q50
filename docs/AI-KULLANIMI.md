# Yapay Zekâ Kullanım Beyanı

Case study belgesi AI destekli araç kullanımını serbest bırakıyor ve teslimatta
hangi araçların hangi amaçla kullanıldığının belirtilmesini istiyor. Beyan:

## Kullanılan araç

**Claude (Anthropic) — Opus 5, Claude Code komut satırı ajanı.** Başka bir
üretken yapay zekâ aracı kullanılmadı.

## Nerede kullanıldı

| Aşama | Kullanım | Doğrulama biçimi |
| --- | --- | --- |
| Veri keşfi | `p05.hdf` içindeki 439 HDF5 yolunun taranması, `Maximum Water Surface` veri setinin ve öznitelik yapısının bulunması | Kod çalıştırılarak; şekiller, birimler ve değer aralıkları basıldı |
| Veri keşfi | `A_A_B_INPINAR.prj`, plan dosyaları, `.rasmap`, `merge.Clone.vrt/hdf` içeriğinin çözülmesi | Dosyalar okundu, yedi planın başlıkları tek tek listelendi |
| Analiz | Bina kot değişikliği (69 poligon, +20 m) ve kuru hücre etkilerinin bulunması | Her iki etki de sayısal olarak ölçüldü (ortalama derinlik 3.37 m → 0.13 m; artık 54 → 0 piksel) |
| Kütüphane | `ras-commander` API imzalarının çıkarılması | Paket kuruldu, `inspect.signature` ile gerçek imzalar okundu — belgeden veya hatırdan yazılmadı |
| Kod | Tüm Python modüllerinin yazılması | Uçtan uca gerçek veri üzerinde çalıştırıldı |
| Test | 44 testin ve sentetik veri üreticilerinin yazılması | `pytest` ile çalıştırıldı |
| Teşhis | Windows'ta HEC-RAS'ın düşme nedeninin bulunması | Proje sistematik olarak denetlendi (`tools/audit_project.py`); yedi planın beşinin yüklenemediği dosya dosya gösterildi |
| Belge | README ve bu dosya | İçerdiği her sayı çalıştırma çıktısından alındı |

## Uygulanan kurallar

1. **Doğrulanmamış API çağrısı koda girmedi.** `ras-commander` fonksiyon adları
   ve parametreleri, kurulu paket üzerinde `inspect` ile okundu.
2. **Her teknik iddia veriye karşı sınandı.** Örneğin "Q1000 da Q50 ile eşleşir"
   varsayımı plan dosyaları taranarak yanlışlandı; asıl tuzağın `Backup.p01`
   olduğu böyle bulundu.
3. **Çalışmayan bir özellik teslim edilmedi.** Eğimli su yüzeyi enterpolasyonu
   denendi, fiziksel olarak imkânsız sonuç verdiği ölçülünce kaldırıldı ve
   gerekçesi README'ye yazıldı.
4. **Bir hata iki kez teşhis edildi.** İlk teşhis (yalnız p05'in DSS yolu)
   eksikti; Windows'ta hata tekrarlayınca varsayıma dönülmedi, proje baştan
   denetlendi ve asıl neden bulundu: HEC-RAS bütün planları yüklüyor, beşi
   bozuk. Bu ders `docs/VERI-DENETIMI.md`'ye yazıldı.
5. **Doğrulanamayan tek adım işaretlendi.** HEC-RAS çalıştırma kodu macOS'ta
   sınanamadı; README'nin sınırlamalar bölümünde açıkça belirtildi.

## Sorumluluk

Kodun tamamı okundu, çalıştırıldı ve anlaşıldı. Canlı değerlendirmede her
fonksiyonun ne yaptığı, neden öyle yazıldığı ve alternatiflerinin neden
elendiği açıklanabilir; küçük değişiklikler yerinde yapılabilir.
