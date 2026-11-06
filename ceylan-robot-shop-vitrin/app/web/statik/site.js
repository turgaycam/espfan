/* Ceylan Robot demo mağaza — tek JS dosyası. Satır içi script yok (CSP: script-src 'self'). */
(function () {
  'use strict';

  function hazir(fn) {
    if (document.readyState !== 'loading') { fn(); } else { document.addEventListener('DOMContentLoaded', fn); }
  }

  function herBiri(liste, fn) { Array.prototype.forEach.call(liste, fn); }

  /* Dil/ülke seçici: değişince formu gönder (JS yoksa "Uygula" düğmesi görünür). */
  function tercihFormu() {
    herBiri(document.querySelectorAll('form[data-otomatik]'), function (form) {
      herBiri(form.querySelectorAll('select'), function (secim) {
        secim.addEventListener('change', function () {
          if (typeof form.requestSubmit === 'function') { form.requestSubmit(); } else { form.submit(); }
        });
      });
    });
  }

  /* Çerez bandı: kabul çerezle saklanır, sunucu bir sonraki sayfada bandı hiç basmaz. */
  function cerezBandi() {
    var bant = document.getElementById('cerez-bandi');
    var dugme = document.getElementById('cerez-kabul');
    if (!bant || !dugme) { return; }
    dugme.addEventListener('click', function (olay) {
      olay.preventDefault();   /* JS'siz yedek: aynı düğme POST /cerez-onay formunu gönderir */
      document.cookie = 'cerez_onay=1; path=/; max-age=31536000; SameSite=Lax';
      bant.parentNode.removeChild(bant);
    });
  }

  /* Geri bildirim penceresi: POST /geri-bildirim (FormData, csrf dahil), yanıt JSON {"tamam": true}. */
  function geriBildirim() {
    var dugme = document.getElementById('gb-dugme');
    var pencere = document.getElementById('gb-pencere');
    var form = document.getElementById('gb-form');
    if (!dugme || !pencere || !form) { return; }
    var durum = form.querySelector('.gb-durum');
    var sayfa = form.querySelector('input[name="sayfa"]');
    var metin = form.querySelector('textarea[name="metin"]');
    var gonder = form.querySelector('button[type="submit"]');

    function goster(mesaj, sinif) {
      durum.textContent = mesaj;
      durum.className = 'gb-durum ' + sinif;
      if (sinif === 'basarili') { durum.setAttribute('data-e2e', 'gb-tamam'); } else { durum.removeAttribute('data-e2e'); }
      durum.hidden = false;
    }
    function ac() {
      if (sayfa) { sayfa.value = window.location.pathname + window.location.search; }
      durum.hidden = true;
      if (typeof pencere.showModal === 'function') { pencere.showModal(); } else { pencere.setAttribute('open', ''); }
      metin.focus();
    }
    function kapat() {
      if (typeof pencere.close === 'function') { pencere.close(); } else { pencere.removeAttribute('open'); }
      dugme.focus();
    }

    dugme.addEventListener('click', ac);
    herBiri(pencere.querySelectorAll('[data-kapat]'), function (b) { b.addEventListener('click', kapat); });
    form.addEventListener('submit', function (olay) {
      olay.preventDefault();
      if (!metin.value.trim()) { metin.focus(); return; }
      gonder.disabled = true;
      fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
      })
        .then(function (yanit) {
          if (!yanit.ok) { throw new Error(String(yanit.status)); }
          return yanit.json();
        })
        .then(function (veri) {
          if (!veri || veri.tamam !== true) { throw new Error('yanit'); }
          metin.value = '';
          goster(form.getAttribute('data-tamam'), 'basarili');
        })
        .catch(function () { goster(form.getAttribute('data-hata'), 'hatali'); })
        .then(function () { gonder.disabled = false; });
    });
  }

  /* Kayıt formu ve G3g ödemedeki "Hesabınız": seçilen müşteri tipine ait olmayan alanları gizle (JS yoksa hepsi görünür). */
  function kayitTipi() {
    var secici = 'input[name="tip"], input[name="hesap_tip"]';
    var radyolar = document.querySelectorAll(secici);
    if (!radyolar.length) { return; }
    var alanlar = document.querySelectorAll('[data-tipler]');
    function uygula() {
      var secili = document.querySelector('input[name="tip"]:checked, input[name="hesap_tip"]:checked');
      herBiri(alanlar, function (alan) {
        var tipler = alan.getAttribute('data-tipler').split(' ');
        alan.hidden = !!secili && tipler.indexOf(secili.value) === -1;
      });
    }
    herBiri(radyolar, function (r) { r.addEventListener('change', uygula); });
    uygula();
  }

  /* Görsel yüklenemezse kategori yer tutucusuna düş. */
  function gorselYedegi() {
    herBiri(document.querySelectorAll('img[data-yedek]'), function (img) {
      function yedege() {
        var yedek = img.getAttribute('data-yedek');
        if (yedek && img.getAttribute('src') !== yedek) {
          img.src = yedek;
          /* G3b: yer tutucuya düşülünce "Temsili görsel" ibaresi açılır (aynı kapsayıcıdaki [data-temsili]) */
          var ibare = img.parentNode && img.parentNode.querySelector('[data-temsili]');
          if (ibare) { ibare.hidden = false; }
        }
      }
      img.addEventListener('error', yedege);
      if (img.complete && img.naturalWidth === 0) { yedege(); }
    });
  }

  /* Parça no kopyala (K22): <button type="button" class="kopyala" data-kopyala="METİN"
     data-kopyalandi="Kopyalandı" hidden>…</button>. JS yoksa ya da pano erişimi yoksa düğme gizli kalır.
     Demo düz HTTP'de çalıştığı için navigator.clipboard yoksa execCommand('copy') yedeği kullanılır. */
  function kopyala() {
    var dugmeler = document.querySelectorAll('[data-kopyala]');
    if (!dugmeler.length) { return; }
    var modern = !!(navigator.clipboard && window.isSecureContext);
    var eski = typeof document.queryCommandSupported === 'function' && document.queryCommandSupported('copy');
    if (!modern && !eski) { return; }
    var duyuru = document.createElement('p');
    duyuru.className = 'gizli';
    duyuru.setAttribute('role', 'status');
    duyuru.setAttribute('aria-live', 'polite');
    document.body.appendChild(duyuru);

    function eskiYontem(metin) {
      var alan = document.createElement('textarea');
      alan.value = metin;
      alan.setAttribute('readonly', '');
      alan.className = 'gizli';
      document.body.appendChild(alan);
      alan.select();
      var tamam = false;
      try { tamam = document.execCommand('copy'); } catch (e) { tamam = false; }
      document.body.removeChild(alan);
      return tamam ? Promise.resolve() : Promise.reject(new Error('kopyalanamadi'));
    }

    herBiri(dugmeler, function (dugme) {
      var zamanlayici = null;
      var etiket = dugme.querySelector('.kopyala-etiket');
      var ilkMetin = etiket ? etiket.textContent : '';
      dugme.hidden = false;
      dugme.addEventListener('click', function () {
        var metin = dugme.getAttribute('data-kopyala') || '';
        var is = modern ? navigator.clipboard.writeText(metin).catch(function () { return eskiYontem(metin); }) : eskiYontem(metin);
        is.then(function () {
          var mesaj = dugme.getAttribute('data-kopyalandi') || '';
          dugme.classList.add('kopyalandi');
          if (etiket && mesaj) { etiket.textContent = mesaj; }
          duyuru.textContent = mesaj ? mesaj + ': ' + metin : metin;
          if (zamanlayici) { window.clearTimeout(zamanlayici); }
          zamanlayici = window.setTimeout(function () {
            dugme.classList.remove('kopyalandi');
            if (etiket) { etiket.textContent = ilkMetin; }
            duyuru.textContent = '';
          }, 2000);
        }, function () { /* sessizce geç: metin sayfada görünür ve elle seçilebilir */ });
      });
    });
  }

  /* G3a: masaüstünde faset onay kutusu değişince filtre formu hemen uygulanır (JS yoksa ya da dar ekranda
     "Uygula" düğmesiyle; mobil çekmecede her dokunuşta sayfa yenilenmesin diye). */
  function fasetOtomatik() {
    if (!window.matchMedia || !window.matchMedia('(min-width: 1024px)').matches) { return; }
    herBiri(document.querySelectorAll('form[data-otomatik-kutu]'), function (form) {
      form.addEventListener('change', function (olay) {
        var hedef = olay.target;
        if (!hedef || hedef.type !== 'checkbox') { return; }
        if (typeof form.requestSubmit === 'function') { form.requestSubmit(); } else { form.submit(); }
      });
    });
  }

  /* Liste filtre çekmecesi (K22): masaüstünde (≥1024 px) açık. CSS ::details-content destekleniyorsa
     JS'siz zaten açık görünür; desteklenmiyorsa burada açılır. Dar ekranda JS'siz <details> çekmecesidir. */
  function filtreCekmecesi() {
    if (!window.matchMedia || !window.matchMedia('(min-width: 1024px)').matches) { return; }
    herBiri(document.querySelectorAll('details.cekmece'), function (d) { d.open = true; });
  }

  /* G3e madde 15: proforma "Yazdır" düğmesi (JS yoksa gizli kalır; tarayıcının yazdır komutu yeterli). */
  function yazdir() {
    herBiri(document.querySelectorAll('[data-yazdir]'), function (dugme) {
      dugme.hidden = false;
      dugme.addEventListener('click', function () { window.print(); });
    });
  }

  /* Hata özeti: sayfa açıldığında odağı özete taşı (ekran okuyucu ve klavye için). */
  function hataOzeti() {
    var ozet = document.querySelector('[data-hata-ozet]');
    if (ozet) { ozet.focus(); }
  }

  hazir(function () {
    document.documentElement.classList.add('js');
    tercihFormu();
    cerezBandi();
    geriBildirim();
    kayitTipi();
    hataOzeti();
    gorselYedegi();
    kopyala();
    yazdir();
    filtreCekmecesi();
    fasetOtomatik();
  });
}());

/* --- Görev 14: ödeme formu --- */
(function () {
  'use strict';
  function faturaGuncelle() {
    var kutu = document.getElementById('fatura_ayni');
    var alan = document.querySelector('.fatura-adresi');
    if (kutu && alan) { alan.hidden = kutu.checked; }
  }
  document.addEventListener('change', function (olay) {
    var hedef = olay.target;
    if (!hedef) { return; }
    if (hedef.id === 'fatura_ayni') { faturaGuncelle(); }
    var odemeFormu = hedef.form && hedef.form.classList.contains('odeme-formu');
    /* G3g madde 1: müşteri tipi fiyat bağlamını değiştirir (₺ KDV dahil / € KDV hariç): tutar yeniden hesaplanır */
    /* G3g: aynı değer yeniden seçilince sayfa yeniden hesaplanmaz (girilen parola sayfaya geri basılmadığı için kaybolmasın) */
    if (hedef.tagName === 'SELECT') {
      var ilk = hedef.querySelector('option[selected]') || hedef.options[0];
      if (ilk && ilk.value === hedef.value) { return; }
    }
    if (hedef.id === 'teslimat_ulke' || (odemeFormu && (hedef.name === 'teslim' || hedef.name === 'hesap_tip'))) {
      var dugme = document.querySelector('button[name="islem"][value="hesapla"]');
      if (dugme) { dugme.click(); }
    }
  });
  /* Tek gönderim (çift sipariş/çift tahsil önlemi; sunucu kuralı ayrıca var): ikinci gönderim engellenir.
     Düğmeler olay sonrasında kilitlenir ki tıklanan düğmenin name/value'su (islem) gönderime girsin. */
  document.addEventListener('submit', function (olay) {
    var form = olay.target;
    if (!form || !form.hasAttribute || !form.hasAttribute('data-tek-gonderim')) { return; }
    if (form.hasAttribute('data-gonderiliyor')) { olay.preventDefault(); return; }
    form.setAttribute('data-gonderiliyor', '');
    window.setTimeout(function () {
      Array.prototype.forEach.call(form.querySelectorAll('button[type="submit"]'), function (b) {
        b.disabled = true; b.setAttribute('aria-disabled', 'true');
      });
    }, 0);
  });
  /* Geri tuşuyla önbellekten dönülürse kilidi aç */
  window.addEventListener('pageshow', function () {
    Array.prototype.forEach.call(document.querySelectorAll('form[data-gonderiliyor]'), function (form) {
      form.removeAttribute('data-gonderiliyor');
      Array.prototype.forEach.call(form.querySelectorAll('button[type="submit"]'), function (b) {
        b.disabled = false; b.removeAttribute('aria-disabled');
      });
    });
  });
  if (document.readyState !== 'loading') { faturaGuncelle(); } else { document.addEventListener('DOMContentLoaded', faturaGuncelle); }
}());
