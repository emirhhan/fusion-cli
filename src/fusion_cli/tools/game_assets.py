"""Canvas oyununun resim yüklemesi ile çizim çağrısı kanıtını ayır."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

#: Sayfa kodundan önce kurulur; sorgu parametreleri rapora taşınmaz.
ASSET_INIT = """(() => {
  const images=new Set(), drawn=new Set();
  const path=img => {try {const url=new URL(img.currentSrc||img.src,document.baseURI);
    return ['http:','https:','file:'].includes(url.protocol)
      ? (url.origin==='null' ? '' : url.origin)+url.pathname : null;}
    catch(e) {return null;}};
  for(const name of ['src','srcset']) {
    const descriptor=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,name);
    Object.defineProperty(HTMLImageElement.prototype,name,{
      ...descriptor, set(value) {images.add(this);descriptor.set.call(this,value);}
    });
  }
  const setAttribute=HTMLImageElement.prototype.setAttribute;
  HTMLImageElement.prototype.setAttribute=function(name,value) {
    if(['src','srcset'].includes(String(name).toLowerCase())) images.add(this);
    return setAttribute.call(this,name,value);
  };
  const original=CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage=function(img,...args) {
    const result=original.call(this,img,...args);
    if(img instanceof HTMLImageElement && img.complete && img.naturalWidth>0) {
      images.add(img);const source=path(img);if(source) drawn.add(source);
    }
    return result;
  };
  window.__fusionAssetUsage=() => ({
    loaded:[...new Set([...images,...document.images]
      .filter(img=>img.complete&&img.naturalWidth>0).map(path).filter(Boolean))].sort(),
    drawn:[...drawn].sort()
  });
})();"""


@dataclass(frozen=True, slots=True)
class AssetUsage:
    """Çizim çağrısı görünürlük değildir; tetiklenmeyen sahneler ayrıca denenmeli."""

    loaded: tuple[str, ...] = ()
    drawn: tuple[str, ...] = ()

    @property
    def unobserved(self) -> tuple[str, ...]:
        return tuple(source for source in self.loaded if source not in self.drawn)

    def summary(self) -> str:
        return (
            f"VARLIK KANITI (Canvas2D, dosya kaynakları): yüklenen {len(self.loaded)}, "
            "drawImage çağrısında kullanılan "
            f"{len(self.drawn)}. Çizilen kaynaklar: {', '.join(self.drawn) or 'yok'}. "
            f"Çizimi henüz gözlemlenmeyen: {', '.join(self.unobserved) or 'yok'}. "
            "Boss/güçlendirme gibi sahneleri tetikleyip kaynak eşlemesini dene; "
            "kısa sondada çizilmemesi tek başına hata değildir. "
            "Çizim çağrısı görünürlük kanıtı değildir; kareleri de incele."
        )


async def read_asset_usage(page: Page) -> AssetUsage:
    """Tarayıcıdaki ayrı yükleme ve gerçek Canvas2D çağrı kayıtlarını oku."""
    snapshot = await page.evaluate("window.__fusionAssetUsage()")
    return AssetUsage(tuple(snapshot["loaded"]), tuple(snapshot["drawn"]))
