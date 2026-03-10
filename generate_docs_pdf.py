#!/usr/bin/env python3
"""Generate implementation documentation PDF for OVH AI Deploy."""

from fpdf import FPDF


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, "OVH AI Deploy - Dokumentacja Implementacji", align="R")
        self.ln(12)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Strona {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 14)
        self.set_fill_color(41, 128, 185)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(41, 128, 185)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def code_block(self, code):
        self.set_font("Courier", "", 8)
        self.set_fill_color(240, 240, 240)
        for line in code.strip().split("\n"):
            self.cell(0, 4.5, f"  {line}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_font("Helvetica", "", 10)

    def warning_box(self, text):
        self.set_fill_color(255, 243, 205)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, f"  UWAGA: {text}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_font("Helvetica", "", 10)


def generate():
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 15, "Dokumentacja Implementacji", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "OVH AI Deploy - Serwer Modeli AI", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Wersja 1.0 | Marzec 2026", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    # ── 1. ARCHITEKTURA ──
    pdf.section_title("1. Architektura systemu")
    pdf.body_text(
        "System sklada sie z nastepujacych komponentow:\n\n"
        "1. Kontener Docker (ghcr.io/panroot/ovh-deploy:latest)\n"
        "   - FastAPI server na porcie 8080\n"
        "   - 10 modeli AI (LLM, diffusion, segmentacja, VLM)\n"
        "   - Auto-shutdown przy bezczynnosci i max uptime\n\n"
        "2. OVH Object Storage (bucket: ai-models, region: GRA)\n"
        "   - Persistent storage na modele (~330 GB)\n"
        "   - Mount z flaga cache = lokalna kopia na SSD\n"
        "   - Koszt: ~10 PLN/mies\n\n"
        "3. Watchdog zewnetrzny (VPS + lokalny cron)\n"
        "   - Sprawdza co 5 min czas pracy i koszty\n"
        "   - Kill przy przekroczeniu limitu\n\n"
        "4. GitHub CI/CD (GitHub Actions)\n"
        "   - Auto-build Docker image przy push do main\n"
        "   - Publikacja na ghcr.io"
    )

    # ── 2. URUCHAMIANIE ──
    pdf.section_title("2. Uruchamianie serwera")
    pdf.sub_title("Szybki start (zalecany)")
    pdf.code_block(
        "cd /home/zgnilec/ovh-deploy\n"
        "./scripts/ovh-start.sh              # domyslnie: 30min idle, 8h max\n"
        "./scripts/ovh-start.sh 60 240       # custom: 60min idle, 4h max"
    )
    pdf.body_text(
        "Skrypt sprawdza czy instancja juz dziala. Jesli tak - pokazuje URL.\n"
        "Jesli nie - tworzy nowa z GPU L40S + Object Storage.\n"
        "Czas startu: ~15 sekund (modele juz na Object Storage)."
    )

    pdf.sub_title("Parametry uruchomienia")
    pdf.code_block(
        "ovh-start.sh [IDLE_TIMEOUT_MIN] [MAX_UPTIME_MIN]\n\n"
        "IDLE_TIMEOUT  - minuty bez requestow do auto-wylaczenia (domyslnie: 30)\n"
        "MAX_UPTIME    - max minuty pracy niezaleznie od aktywnosci (domyslnie: 480=8h)"
    )

    pdf.sub_title("Reczne przez CLI (zaawansowane)")
    pdf.code_block(
        "ovhai app run \\\n"
        "  --name model-server \\\n"
        "  --flavor l40s-1-gpu --gpu 1 \\\n"
        "  --default-http-port 8080 --unsecure-http \\\n"
        "  --env HF_TOKEN=<token> \\\n"
        "  --env IDLE_TIMEOUT=30 \\\n"
        "  --env MAX_UPTIME=480 \\\n"
        "  --volume ai-models@GRA:/workspace/models:rw:cache \\\n"
        "  ghcr.io/panroot/ovh-deploy:latest"
    )

    # ── 3. ZATRZYMYWANIE ──
    pdf.section_title("3. Zatrzymywanie serwera")
    pdf.sub_title("Reczne zatrzymanie")
    pdf.code_block(
        "./scripts/ovh-stop.sh               # zatrzymaj wszystkie instancje\n"
        "# lub recznie:\n"
        "ovhai app list                       # znajdz ID\n"
        "ovhai app delete <ID> --force        # usun"
    )
    pdf.warning_box("Po zatrzymaniu koszty GPU = 0 PLN. Object Storage = ~10 PLN/mies.")

    pdf.sub_title("Automatyczne zatrzymanie (3 poziomy)")
    pdf.body_text(
        "Poziom 1: Auto-shutdown w aplikacji\n"
        "  - Idle timeout: wylacza po 30 min bez requestow\n"
        "  - Max uptime: wylacza po 8h niezaleznie od aktywnosci\n"
        "  - Mechanizm: os._exit(0) -> OVH moze restartowac kontener\n\n"
        "Poziom 2: Watchdog na VPS (146.59.86.3)\n"
        "  - Cron co 5 minut\n"
        "  - Kill przy koszcie > 50 PLN lub czasie > 10h\n"
        "  - Alert email przy 80% limitu\n"
        "  - Mechanizm: ovhai app delete --force\n\n"
        "Poziom 3: Watchdog lokalny (ten serwer)\n"
        "  - Cron co 5 minut (identyczny skrypt)\n"
        "  - Redundancja - dziala nawet gdy VPS jest niedostepny"
    )

    # ── 4. SPRAWDZANIE STATUSU ──
    pdf.add_page()
    pdf.section_title("4. Sprawdzanie statusu")
    pdf.code_block(
        "./scripts/ovh-status.sh             # status + modele\n\n"
        "# Lub przez API:\n"
        "curl https://<URL>/status            # uptime, idle, koszty\n"
        "curl https://<URL>/models            # lista modeli + status\n"
        "curl https://<URL>/health            # healthcheck"
    )

    pdf.sub_title("Przyklad odpowiedzi /status")
    pdf.code_block(
        '{\n'
        '  "uptime_min": 15.2,\n'
        '  "idle_min": 3.1,\n'
        '  "idle_shutdown_at_min": 30,\n'
        '  "max_uptime_shutdown_at_min": 480,\n'
        '  "idle_remaining_min": 26.9,\n'
        '  "uptime_remaining_min": 464.8,\n'
        '  "estimated_cost_pln": 1.84\n'
        '}'
    )

    # ── 5. ZABEZPIECZENIA KOSZTOWE ──
    pdf.section_title("5. Zabezpieczenia kosztowe")

    pdf.sub_title("A) Auto-shutdown (wbudowany w aplikacje)")
    pdf.body_text(
        "Plik: app/main.py - funkcja idle_watchdog()\n"
        "Sprawdza co 60 sekund:\n"
        "  - Czas od ostatniego requesta (idle) vs IDLE_TIMEOUT\n"
        "  - Calkowity czas pracy vs MAX_UPTIME\n"
        "Konfiguracja przez zmienne srodowiskowe przy starcie."
    )

    pdf.sub_title("B) Watchdog zewnetrzny")
    pdf.body_text(
        "Plik: scripts/ovh-watchdog.sh\n"
        "Zainstalowany na:"
    )
    pdf.code_block(
        "1. VPS (146.59.86.3) - /root/ovh-watchdog.sh\n"
        "   Cron: */5 * * * * /root/ovh-watchdog.sh\n\n"
        "2. Lokalny serwer - /home/zgnilec/ovh-deploy/scripts/ovh-watchdog.sh\n"
        "   Cron: */5 * * * * /home/zgnilec/ovh-deploy/scripts/ovh-watchdog.sh"
    )
    pdf.body_text(
        "Konfiguracja (w skrypcie):\n"
        "  MAX_COST_PLN=50    - max koszt na sesje\n"
        "  MAX_HOURS=10       - max godzin pracy\n"
        "  COST_PER_HOUR=8.90 - stawka L40S brutto/h\n"
        "  ALERT_EMAIL=lukasz@orzechowski.eu"
    )

    pdf.sub_title("C) Alerty OVH")
    pdf.body_text(
        "OVH wysyla alerty przy przekroczeniu progu (ustawiony na 200 PLN).\n"
        "UWAGA: OVH ekstrapoluje zuzycie na caly miesiac zakladajac ciagla prace.\n"
        "Prognoza 25000 PLN nie oznacza realnego kosztu - to projekcja 24/7."
    )

    # ── 6. KOSZTY ──
    pdf.section_title("6. Zestawienie kosztow")

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(60, 6, "Usluga", border=1)
    pdf.cell(50, 6, "Cena", border=1)
    pdf.cell(0, 6, "Uwagi", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)

    costs = [
        ("GPU L40S (AI Deploy)", "~8.90 PLN brutto/h", "Tylko gdy instancja RUNNING"),
        ("Object Storage (330 GB)", "~10 PLN/mies", "Staly koszt, nawet na postoju"),
        ("Ruch wewn. (GPU<->Storage)", "0 PLN", "Darmowy w ramach regionu GRA"),
        ("Ruch wychodzacy publiczny", "~0.04 PLN/GB", "Minimalny"),
        ("1h pracy", "~8.90 PLN", ""),
        ("8h pracy (1 sesja)", "~71 PLN", ""),
        ("20 dni x 8h/dzien", "~1 424 PLN", ""),
        ("Postoj (tylko storage)", "~10 PLN/mies", "GPU = 0 PLN"),
    ]
    for name, cost, note in costs:
        pdf.cell(60, 5.5, name, border=1)
        pdf.cell(50, 5.5, cost, border=1)
        pdf.cell(0, 5.5, note, border=1, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)
    pdf.warning_box("Zawsze wylaczaj GPU po pracy! Koszt 24/7: ~6400 PLN/mies.")

    # ── 7. STRUKTURA PLIKOW ──
    pdf.add_page()
    pdf.section_title("7. Struktura projektu")
    pdf.code_block(
        "ovh-deploy/\n"
        "  app/\n"
        "    main.py              # Glowna aplikacja FastAPI\n"
        "    requirements.txt     # Zaleaznosci Python\n"
        "  scripts/\n"
        "    start.sh             # Entrypoint kontenera\n"
        "    ovh-start.sh         # Uruchom instancje OVH\n"
        "    ovh-stop.sh          # Zatrzymaj instancje\n"
        "    ovh-status.sh        # Sprawdz status\n"
        "    ovh-watchdog.sh      # Watchdog kosztowy (cron)\n"
        "  Dockerfile             # Obraz Docker (CUDA 12.4)\n"
        "  .github/workflows/\n"
        "    docker-build.yml     # CI/CD - auto-build na push"
    )

    pdf.section_title("8. Aktualizacja obrazu Docker")
    pdf.body_text(
        "Obraz buduje sie automatycznie przez GitHub Actions przy kazdym push do main."
    )
    pdf.code_block(
        "# 1. Zmien kod\n"
        "git add . && git commit -m 'opis zmian'\n"
        "git push origin main\n\n"
        "# 2. Poczekaj na build (~5 min)\n"
        "# GitHub Actions zbuduje i opublikuje na ghcr.io\n\n"
        "# 3. Restart instancji z nowym obrazem\n"
        "./scripts/ovh-stop.sh\n"
        "./scripts/ovh-start.sh"
    )

    pdf.section_title("9. Dostep i dane logowania")
    pdf.body_text(
        "OVH AI Deploy:\n"
        "  Panel: https://www.ovhcloud.com/en/public-cloud/ai-deploy/\n"
        "  CLI: ovhai (zainstalowane na tym serwerze i VPS)\n"
        "  Login: ovhai login (OpenStack credentials)\n\n"
        "GitHub:\n"
        "  Repo: https://github.com/panroot/ovh-deploy\n"
        "  Docker image: ghcr.io/panroot/ovh-deploy:latest\n\n"
        "VPS Watchdog:\n"
        "  IP: 146.59.86.3\n"
        "  Dostep: tmux attach -t vps (z tego serwera)\n"
        "  Skrypt: /root/ovh-watchdog.sh\n"
        "  Log: /var/log/ovh-watchdog.log"
    )

    # ── 10. TROUBLESHOOTING ──
    pdf.section_title("10. Rozwiazywanie problemow")

    pdf.sub_title("Instancja nie startuje")
    pdf.code_block(
        "ovhai app list                       # sprawdz stan\n"
        "ovhai app logs <ID>                  # logi kontenera"
    )

    pdf.sub_title("Model nie laduje sie (CUDA OOM)")
    pdf.body_text("L40S ma 45 GB VRAM. Zwolnij inne modele przed zaladowaniem duzego:")
    pdf.code_block(
        "curl -X POST https://<URL>/models/<model>/unload\n"
        "curl -X POST https://<URL>/models/<nowy_model>/load"
    )

    pdf.sub_title("Model nie laduje sie (pliki uszkodzone)")
    pdf.body_text("Uzyj endpointu redownload - usuwa i pobiera od nowa:")
    pdf.code_block("curl -X POST https://<URL>/models/<model>/redownload")

    pdf.sub_title("Watchdog nie dziala")
    pdf.code_block(
        "# Sprawdz cron\n"
        "crontab -l | grep watchdog\n\n"
        "# Sprawdz log\n"
        "tail -20 /var/log/ovh-watchdog.log\n\n"
        "# Test reczny\n"
        "/home/zgnilec/ovh-deploy/scripts/ovh-watchdog.sh"
    )

    pdf.sub_title("Alert kosztowy z OVH (np. 25000 PLN)")
    pdf.body_text(
        "To ekstrapolacja - OVH zaklada ciagla prace 24/7.\n"
        "Sprawdz realne koszty w panelu OVH -> Billing -> Current usage.\n"
        "Watchdog pilnuje limitu 50 PLN/sesje."
    )

    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 6, "Wygenerowano automatycznie | Marzec 2026", align="C")

    pdf.output("/home/zgnilec/ovh-deploy/dokumentacja_implementacji.pdf")
    print("Generated: dokumentacja_implementacji.pdf")


if __name__ == "__main__":
    generate()
