#!/usr/bin/env bash
# cr-shop-demo dağıtımı — laptopta (Git Bash), depo kökünden: bash dagitim/deploy.sh
# Adımlar: temiz ağaç kontrolü -> git archive HEAD -> VM'de yeni release -> dagitim/uzak-yayinla.sh
# (venv + pip, pytest, yedek + geçiş, current, restart, /saglik, gerekirse geri alma, eski release temizliği)
# Geri alma şemayı geri almaz; veritabanını döndürmenin yolu dağıtım öncesi yedektir — komutlar uzak-yayinla.sh [3/6].
set -euo pipefail

HEDEF="${CR_SHOP_HEDEF:-cr-web-demo}"
KOK=/opt/cr-shop-demo

cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain)" ]; then
  echo "HATA: çalışma ağacı temiz değil; önce commit edin." >&2
  git status --short >&2
  exit 1
fi

RELEASE="$(date +%Y%m%d-%H%M)"
SURUM="$(git rev-parse --short HEAD)"
REL="$KOK/releases/$RELEASE"
echo "Release $RELEASE (commit $SURUM) -> $HEDEF:$REL"

if ! ssh "$HEDEF" "test -d $KOK/releases && test ! -e $REL && mkdir $REL"; then
  echo "HATA: $KOK/releases yok (kurulum-vm.sh çalıştı mı?) ya da $RELEASE zaten var (1 dk bekleyip tekrar deneyin)." >&2
  exit 1
fi

if ! git archive --format=tar HEAD | ssh "$HEDEF" "tar -x -C $REL && echo $SURUM > $REL/SURUM"; then
  echo "HATA: arşiv aktarılamadı; yarım release siliniyor." >&2
  ssh "$HEDEF" "rm -rf $REL"
  exit 1
fi

ssh "$HEDEF" "bash $REL/dagitim/uzak-yayinla.sh $RELEASE"
