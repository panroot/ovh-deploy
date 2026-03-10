#!/usr/bin/env python3
"""Generate PDF instructions for OVH AI Deploy Model Server."""

from fpdf import FPDF

BASE_URL = "https://<APP_URL>"


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, "OVH AI Deploy - Model Server", align="R")
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
        self.set_font("Courier", "", 9)
        self.set_fill_color(240, 240, 240)
        for line in code.strip().split("\n"):
            self.cell(0, 5, f"  {line}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_font("Helvetica", "", 10)

    def model_card(self, name, typ, size, desc, endpoint, example_req, example_note=""):
        self.sub_title(f"{name}")
        self.set_font("Helvetica", "", 9)
        self.cell(50, 5, f"Typ: {typ}")
        self.cell(50, 5, f"Rozmiar: {size}")
        self.cell(0, 5, f"VRAM: ~{desc}", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_font("Helvetica", "", 10)
        self.body_text(f"Endpoint: {endpoint}")
        self.code_block(example_req)
        if example_note:
            self.set_font("Helvetica", "I", 9)
            self.cell(0, 5, example_note, new_x="LMARGIN", new_y="NEXT")
            self.ln(3)


def generate_short():
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 15, "Instrukcja Skrocona", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, "OVH AI Deploy - Serwer Modeli AI", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.section_title("1. Uruchomienie / Zatrzymanie")
    pdf.code_block(
        "./scripts/ovh-start.sh    # uruchom serwer\n"
        "./scripts/ovh-stop.sh     # zatrzymaj (0 PLN)\n"
        "./scripts/ovh-status.sh   # sprawdz status"
    )
    pdf.body_text("Koszt: ~7.24 PLN/h (L40S GPU). WYLACZAJ gdy nie uzywasz!")

    pdf.section_title("2. Zaladuj model na GPU")
    pdf.code_block(
        "# Zaladuj\n"
        "curl -X POST https://<URL>/models/qwen-2.5-14b/load\n\n"
        "# Zwolnij GPU\n"
        "curl -X POST https://<URL>/models/qwen-2.5-14b/unload"
    )

    pdf.section_title("3. Uzycie modeli")

    pdf.sub_title("Chat / LLM (Qwen, LLaVA)")
    pdf.code_block(
        'curl -X POST https://<URL>/v1/chat/completions \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"prompt":"Napisz wiersz","model":"qwen-2.5-14b"}\''
    )

    pdf.sub_title("Generowanie obrazow (FLUX, SDXL, SD)")
    pdf.code_block(
        'curl -X POST https://<URL>/v1/images/generate \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"prompt":"kot w kosmosie","model":"sdxl-base"}\''
    )

    pdf.sub_title("Usuwanie tla (BiRefNet)")
    pdf.code_block(
        'curl -X POST https://<URL>/v1/background/remove \\\n'
        '  -F "image=@zdjecie.jpg"'
    )

    pdf.section_title("4. Dostepne modele")
    models = [
        ("birefnet", "Segmentacja", "~1 GB", "Usuwanie tla z obrazow"),
        ("sd-1.5", "Diffusion", "~5 GB", "Stable Diffusion 1.5 - generowanie obrazow"),
        ("sdxl-base", "Diffusion", "~7 GB", "SDXL Base 1.0 - obrazy 1024x1024"),
        ("flux-klein-4b", "Diffusion", "~16 GB", "FLUX lite - szybkie obrazy"),
        ("flux-schnell", "Diffusion", "~34 GB", "FLUX.1 Schnell - najszybszy FLUX"),
        ("llava-13b", "VLM", "~26 GB", "LLaVA - analiza obrazow + tekst"),
        ("qwen-2.5-14b", "LLM", "~28 GB", "Qwen 2.5 14B - chat/kod"),
        ("qwen-2.5-32b", "LLM", "~64 GB", "Qwen 2.5 32B - zaawansowany chat"),
        ("qwen-2.5-72b", "LLM", "~144 GB", "Qwen 2.5 72B - najpotezniejszy (wymaga kwantyzacji)"),
    ]
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(45, 6, "Model", border=1)
    pdf.cell(25, 6, "Typ", border=1)
    pdf.cell(20, 6, "Rozmiar", border=1)
    pdf.cell(0, 6, "Opis", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for name, typ, size, desc in models:
        pdf.cell(45, 5.5, name, border=1)
        pdf.cell(25, 5.5, typ, border=1)
        pdf.cell(20, 5.5, size, border=1)
        pdf.cell(0, 5.5, desc, border=1, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, "L40S ma 45GB VRAM - laduj max 1 duzy model naraz. Zwolnij przed zaladowaniem kolejnego.")

    pdf.output("/home/zgnilec/ovh-deploy/instrukcja_skrocona.pdf")
    print("Generated: instrukcja_skrocona.pdf")


def generate_full():
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 15, "Instrukcja Pelna", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "OVH AI Deploy - Serwer Modeli AI", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Wersja 1.0 | Marzec 2026", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    # ── 1. ARCHITEKTURA ──
    pdf.section_title("1. Architektura")
    pdf.body_text(
        "Serwer modeli dziala jako kontener Docker na OVH AI Deploy z GPU NVIDIA L40S (45GB VRAM). "
        "Modele sa przechowywane w OVH Object Storage (bucket ai-models) i synchronizowane "
        "przy starcie/zatrzymaniu. API oparte na FastAPI, port 8080."
    )
    pdf.body_text(
        "Obraz Docker: ghcr.io/panroot/ovh-deploy:latest\n"
        "Repo: https://github.com/panroot/ovh-deploy\n"
        "GPU: NVIDIA L40S 45GB VRAM | CPU: 13 vCores | RAM: 80GB\n"
        "Koszt: ~7.24 PLN netto/h (~174 PLN/dzien)"
    )

    # ── 2. URUCHAMIANIE ──
    pdf.section_title("2. Uruchamianie i zatrzymywanie")
    pdf.sub_title("Szybki start (skrypty)")
    pdf.code_block(
        "./scripts/ovh-start.sh    # Tworzy instancje lub pokazuje istniejaca\n"
        "./scripts/ovh-stop.sh     # Usuwa instancje (0 kosztow)\n"
        "./scripts/ovh-status.sh   # Status + postep modeli"
    )

    pdf.sub_title("Reczne przez CLI")
    pdf.code_block(
        "ovhai app run \\\\\n"
        "  --name model-server \\\\\n"
        "  --flavor l40s-1-gpu --gpu 1 \\\\\n"
        "  --default-http-port 8080 --unsecure-http \\\\\n"
        "  --env HF_TOKEN=<twoj_token> \\\\\n"
        "  --volume ai-models@GRA:/workspace/models:rw:cache \\\\\n"
        "  ghcr.io/panroot/ovh-deploy:latest"
    )

    pdf.sub_title("Zatrzymanie")
    pdf.code_block(
        "ovhai app list                    # znajdz ID\n"
        "ovhai app delete <ID> --force     # usun"
    )
    pdf.body_text("WAZNE: Po zatrzymaniu koszty = 0 PLN. Modele sa zapisane w Object Storage i przetrwaja restart.")

    # ── 3. API ──
    pdf.section_title("3. Endpointy API")

    pdf.sub_title("Status i zarzadzanie")
    pdf.code_block(
        "GET  /health                    # healthcheck\n"
        "GET  /models                    # lista modeli + status\n"
        "GET  /models/{name}/status      # status konkretnego modelu\n"
        "POST /models/{name}/download    # pobierz model (jesli brakuje)\n"
        "POST /models/{name}/load        # zaladuj na GPU\n"
        "POST /models/{name}/unload      # zwolnij GPU"
    )

    pdf.sub_title("Inferencja")
    pdf.code_block(
        "POST /v1/chat/completions       # chat (LLM/VLM)\n"
        "POST /v1/images/generate        # generowanie obrazow\n"
        "POST /v1/background/remove      # usuwanie tla"
    )

    # ── 4. MODELE SZCZEGOLOWO ──
    pdf.add_page()
    pdf.section_title("4. Modele - szczegolowa instrukcja")

    # BiRefNet
    pdf.model_card(
        "BiRefNet - Usuwanie tla", "Segmentacja", "~1 GB", "2 GB VRAM",
        "POST /v1/background/remove",
        'curl -X POST https://<URL>/v1/background/remove \\\n'
        '  -F "image=@zdjecie.jpg"',
        "Zwraca obraz PNG z przezroczystym tlem (base64). Rozdzielczosc: 1024x1024."
    )

    # SD 1.5
    pdf.model_card(
        "Stable Diffusion 1.5", "Diffusion", "~5 GB", "4 GB VRAM",
        "POST /v1/images/generate",
        'curl -X POST https://<URL>/v1/images/generate \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"prompt":"a beautiful sunset over mountains",\n'
        '       "model":"sd-1.5","width":512,"height":512,\n'
        '       "steps":30,"guidance_scale":7.5}\'',
        "Optymalna rozdzielczosc: 512x512. Szybki, dobry do prototypowania."
    )

    # SDXL
    pdf.model_card(
        "SDXL Base 1.0", "Diffusion", "~7 GB", "7 GB VRAM",
        "POST /v1/images/generate",
        'curl -X POST https://<URL>/v1/images/generate \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"prompt":"photorealistic cat portrait",\n'
        '       "model":"sdxl-base","width":1024,"height":1024,\n'
        '       "steps":25,"guidance_scale":7.0}\'',
        "Optymalna rozdzielczosc: 1024x1024. Lepsza jakosc niz SD 1.5."
    )

    # FLUX Klein
    pdf.model_card(
        "FLUX Klein 4B (lite)", "Diffusion", "~16 GB", "12 GB VRAM",
        "POST /v1/images/generate",
        'curl -X POST https://<URL>/v1/images/generate \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"prompt":"cyberpunk city at night",\n'
        '       "model":"flux-klein-4b","width":1024,"height":1024,\n'
        '       "steps":20,"guidance_scale":3.5}\'',
        "Szybsza wersja FLUX. guidance_scale 3-4 daje najlepsze wyniki."
    )

    # FLUX Schnell
    pdf.model_card(
        "FLUX.1 Schnell", "Diffusion", "~34 GB", "20 GB VRAM",
        "POST /v1/images/generate",
        'curl -X POST https://<URL>/v1/images/generate \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"prompt":"professional photo of a dog",\n'
        '       "model":"flux-schnell","width":1024,"height":1024,\n'
        '       "steps":4,"guidance_scale":0.0}\'',
        "Bardzo szybki (4 kroki!). guidance_scale=0 (classifier-free). Wymaga HF tokenu."
    )

    pdf.add_page()

    # LLaVA
    pdf.model_card(
        "LLaVA 1.5 13B - Vision Language", "VLM", "~26 GB", "26 GB VRAM",
        "POST /v1/chat/completions",
        'curl -X POST https://<URL>/v1/chat/completions \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"prompt":"Opisz co widzisz na tym obrazku",\n'
        '       "model":"llava-13b","max_tokens":512}\'',
        "Model wizyjno-jezykowy. Analizuje obrazy i odpowiada na pytania."
    )

    # Qwen 14B
    pdf.model_card(
        "Qwen 2.5 14B Instruct", "LLM", "~28 GB", "28 GB VRAM",
        "POST /v1/chat/completions",
        'curl -X POST https://<URL>/v1/chat/completions \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"prompt":"Napisz funkcje w Python sortujaca liste",\n'
        '       "model":"qwen-2.5-14b","max_tokens":2048,\n'
        '       "temperature":0.7}\'',
        "Swietny do kodu, chata, analizy. Miesci sie na L40S z zapasem."
    )

    # Qwen 32B
    pdf.model_card(
        "Qwen 2.5 32B Instruct", "LLM", "~64 GB", "64 GB VRAM (wymaga kwantyzacji)",
        "POST /v1/chat/completions",
        'curl -X POST https://<URL>/v1/chat/completions \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"prompt":"Przeanalizuj ten kontrakt prawny...",\n'
        '       "model":"qwen-2.5-32b","max_tokens":4096}\'',
        "Potrzebuje kwantyzacji 4-bit (~18GB VRAM) na L40S. Lepsze rozumowanie niz 14B."
    )

    # Qwen 72B
    pdf.model_card(
        "Qwen 2.5 72B Instruct", "LLM", "~144 GB", "144 GB VRAM (wymaga kwantyzacji 4-bit ~40GB)",
        "POST /v1/chat/completions",
        'curl -X POST https://<URL>/v1/chat/completions \\\n'
        '  -H "Content-Type: application/json" \\\n'
        '  -d \'{"prompt":"Stworz kompleksowa strategie...",\n'
        '       "model":"qwen-2.5-72b","max_tokens":4096}\'',
        "Najpotezniejszy model. Wymaga 4-bit kwantyzacji na L40S (~40GB). Wolny ale najlepszy."
    )

    # ── 5. LIMITY VRAM ──
    pdf.add_page()
    pdf.section_title("5. Zarzadzanie VRAM (45 GB)")
    pdf.body_text(
        "L40S ma 45GB VRAM. Nie mozna zaladowac wszystkich modeli naraz. "
        "Przed zaladowaniem kolejnego duzego modelu - zwolnij poprzedni (POST /models/{name}/unload)."
    )
    pdf.sub_title("Przykladowe kombinacje ktore sie zmieszcza:")
    pdf.body_text(
        "- BiRefNet + SD 1.5 + SDXL = ~13 GB\n"
        "- BiRefNet + FLUX Klein = ~14 GB\n"
        "- Qwen 14B + BiRefNet = ~30 GB\n"
        "- FLUX Schnell sam = ~20 GB\n"
        "- Qwen 32B (4-bit) sam = ~18 GB\n"
        "- Qwen 72B (4-bit) sam = ~40 GB (na granicy!)"
    )

    # ── 6. ROZWIAZYWANIE PROBLEMOW ──
    pdf.section_title("6. Rozwiazywanie problemow")
    pdf.sub_title("Model nie laduje sie")
    pdf.body_text("Sprawdz czy jest pobrany: GET /models/{name}/status. Jesli nie - POST /models/{name}/download.")
    pdf.sub_title("CUDA out of memory")
    pdf.body_text("Za duzo modeli zaladowanych. Zwolnij niepotrzebne: POST /models/{name}/unload.")
    pdf.sub_title("Timeout przy pobieraniu")
    pdf.body_text("Serwer automatycznie retryuje do 5 razy. Sprawdz status: GET /models.")
    pdf.sub_title("401 przy FLUX Schnell")
    pdf.body_text("Upewnij sie ze HF_TOKEN jest ustawiony i masz zaakceptowana licencje na huggingface.co.")

    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 6, "Wygenerowano automatycznie przez Claude AI | Marzec 2026", align="C")

    pdf.output("/home/zgnilec/ovh-deploy/instrukcja_pelna.pdf")
    print("Generated: instrukcja_pelna.pdf")


if __name__ == "__main__":
    generate_short()
    generate_full()
