-- G2: ürün açıklamaları (LLM taslağı ya da kaynak metin) ve bal küpüyle engellenen istemciler.
-- Eşitleme bu tablolara YAZMAZ/SİLMEZ.
CREATE TABLE urun_aciklama (
  urun_id INTEGER NOT NULL REFERENCES urun(id),
  dil TEXT NOT NULL CHECK (dil IN ('tr','en')),
  metin TEXT NOT NULL,
  kaynak TEXT NOT NULL CHECK (kaynak IN ('llm-taslak','kaynak')),
  model TEXT,                       -- llm-taslak ise üreten model
  uretildi TEXT NOT NULL,           -- ISO zaman
  PRIMARY KEY (urun_id, dil)
);

CREATE TABLE engelli_ip (
  ip TEXT PRIMARY KEY,
  neden TEXT NOT NULL,
  yol TEXT,
  engellendi TEXT NOT NULL,         -- ISO zaman (UTC)
  bitis TEXT NOT NULL               -- ISO zaman (UTC): bundan sonra engel kalkar
);
