# tools/

Geliştirici betikleri; paketin parçası değildir, kurulumla dağıtılmaz.
Developer scripts; not part of the package and not shipped with it.
Her betik depo kökünden çalıştırılır / every script runs from the repository root.

| Klasör / Folder | İçerik / Contents |
|---|---|
| `bench/`   | Ölçüm ve grafikler — `bench_pipeline.py`, `bench_protocol.py`, `bench_chart.py`, `make_bench_chart.py` |
| `site/`    | README / site görselleri — banner, karşılaştırma görseli ve sayfası, ekran görüntüleri, demo, mockup ikonları |
| `samples/` | Örnek/fixture belge üreticileri — `make_academic_paper.py`, `make_sample_document.py`, `make_sample_docx_report.py` |
| `audit/`   | Tek seferlik denetim ve uçtan uca doğrulama betikleri (bkz. `audit/README.md`) |
| kök / root | `coherence_check.py`, `run_checks.ps1` (testler + lint + demo), `story_site.py` (hikâyeyi Pages sayfası olarak yayınlar / publishes the story as a Pages page), `fetch_*.bat` / `run_*.bat` (kampanya kaynaklarını indirir ve koşar / fetch and run campaign sources) |
