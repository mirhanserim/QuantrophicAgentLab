# Quantrophic Agent Lab

Bir web uygulamasını milestone milestone büyüten, tarayıcıda doğrulanan otonom bir kodlama agent'ı. Tamamen yerelde çalışır: Ollama üzerinden yerel bir model (varsayılan `qwen3:8b`) ve Playwright/Chromium kullanır.

*A browser-gated autonomous coding agent. A local LLM extends a small web IDE one milestone at a time. Every patch is checked in headless Chromium and rolled back automatically if it breaks something.*

## Nasıl çalışır?

```
            ┌──────────── runtime (Python) ─────────────┐
 milestone ─►  baseline Chromium checks                  │
  (JSON)    │      │                                     │
            │      ▼                                     │
            │  LLM ── one small patch ──► snapshot       │
            │   ▲                           │            │
            │   │                     Chromium verify    │
            │   │                           │            │
            │   └── report ◄── regression? ─┴─ yes → rollback
            │                               │ no         │
            │                    all pass → git commit   │
            └────────────────────────────────────────────┘
```

Model hiçbir şeyin sahibi değil; sadece **küçük, birebir metin eşleşmeli yamalar** önerebiliyor. Doğrulama, geri alma, git ve "bitti" kararı runtime'da.

| Güvenlik katmanı | Ne yapar |
| --- | --- |
| Sandbox yolları | Araçlar yalnızca `workspace/` içinde çalışır, `..` ve `.git` engellenir |
| Tam metin yamaları | `replace_text` / `insert_before` / `insert_after` / `append_text`; işaretçi dosyada **tam bir kez** geçmeli. Dosyanın tamamını yeniden yazmak mümkün değil |
| Regresyon kapısı | Her yamadan önce snapshot alınır. Daha önce geçen **herhangi bir** kontrol bozulursa yama otomatik geri alınır |
| Tekrar engeli | Aynı yama art arda denenirse bloklanır |
| Tur başına tek yama | Modelin aynı turda birden çok değişiklik yığması engellenir |
| Kapsamlı git | Status ve commit sadece `workspace/` yolunu görür |
| Çalıştırma kaydı | Her adım `agent/artifacts/runs/*.json` dosyasına yazılır |

## Kurulum

```bash
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

ollama serve &            # ayrı terminalde de olabilir
ollama pull qwen3:8b
```

## Kullanım

```bash
python agent.py --verify-only          # sadece tarayıcı kontrollerini çalıştır
python agent.py                        # en son milestone'u tamamla
python agent.py -m m05_terminal.json --max-steps 30 --no-commit
QUANTROPHIC_MODEL=qwen3:4b python agent.py # farklı model
```

| Ortam değişkeni | Varsayılan | Açıklama |
| --- | --- | --- |
| `QUANTROPHIC_MODEL` | `qwen3:8b` | Ollama modeli |
| `QUANTROPHIC_NUM_CTX` | `16384` | Bağlam penceresi (Ollama'nın küçük varsayılanı yerine) |
| `QUANTROPHIC_MAX_STEPS` | `60` | En fazla onarım adımı |
| `QUANTROPHIC_WORKSPACE` | `./workspace` | Agent'ın düzenleyeceği proje |

## Yeni milestone eklemek

Kod değiştirmek gerekmez. `agent/milestones/` içine bir JSON dosyası eklemek yeterli. Önceki milestone'ların kontrolleri otomatik olarak regresyon testi olarak devralınır.

```json
{
  "title": "Milestone 6 — Command palette",
  "goal": "Add a Ctrl+K command palette.",
  "requirements": ["command-palette", "palette-input"],
  "preserve": ["terminal", "editor", "preview"],
  "commit_message": "Milestone 6: browser-verified command palette",
  "checks": [
    {"id": "palette", "type": "visible", "selector": ".command-palette", "label": "Palette visible"}
  ]
}
```

Kontrol türleri: `visible`, `text_any`, `css_in`, `click_class`, `click_changes`, `click_text`, `min_numbers` (bkz. `agent/browser_verify.py`).

## Testler

Ollama gerekmez. Sahte bir model; önce regresyon yapan bir yama dener (geri alınması beklenir), sonra milestone'u tamamlayan yamayı uygular.

```bash
cd agent && .venv/bin/python -m unittest discover tests -v
```

## Proje yapısı

```
agent/
  agent.py           CLI + agent döngüsü
  browser_verify.py  bildirimsel Chromium kontrolleri, regresyon karşılaştırması
  safe_tools.py      sandbox'lı dosya/yama/snapshot/git araçları
  config.py          yollar, ayarlar, milestone yükleme
  milestones/        m00 … m05 JSON tanımları
  tests/             offline testler + Ollama smoke test
workspace/           agent'ın geliştirdiği "Quantrophic CodeSpace" web IDE'si
```

## Milestone geçmişi

| # | Özellik |
| --- | --- |
| 0 | Sayaç + durum düğmesi |
| 1 | CodeSpace düzeni |
| 2 | Dosya gezgini + seçim |
| 3 | Sekmeli kod editörü, satır numaraları, aktif dosya |
| 4 | Önizleme paneli |
| 5 | Terminal paneli |

---
Mirhan Serim · [quantrophic.com.tr](https://quantrophic.com.tr)
