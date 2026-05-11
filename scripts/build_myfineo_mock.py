import sys
from pathlib import Path
import json

# Make `src/` importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from builder.models import SiteContent
from builder.image_picker import pick_hero_image
from builder.render import render_to_disk
from builder.db import BuildsRepo

# The content I generated manually
CONTENT_JSON = """
{
  "slug": "myfineo",
  "sector": "wealth_management",
  "meta_description": "MYFINEO : Conseil en investissements financiers et gestion de patrimoine. Prenez les bonnes décisions financières et atteignez vos objectifs avec MYFINEO.",
  "branding": {
    "name": "MYFINEO",
    "subtitle": "Conseil en Investissements Financiers",
    "letter": "m",
    "professional_membership": "CIF · CNCEF PATRIMOINE",
    "phone": "01 23 45 67 89",
    "phone_tel": "+33123456789",
    "email": "contact@myfineo.fr",
    "legal_siren": "903 625 424",
    "legal_orias": "21008322"
  },
  "hero": {
    "eyebrow": "Votre partenaire en stratégie financière",
    "h1_line1": "Prenez les",
    "h1_line2": "bonnes décisions",
    "h1_line3_before": "pour votre ",
    "h1_line3_emphasis": "patrimoine.",
    "h1_line3_after": "",
    "subtitle": "Atteignez vos objectifs financiers grâce à un accompagnement personnalisé et indépendant. MYFINEO vous guide vers l'excellence financière.",
    "cta_primary": "Prendre Rendez-vous en ligne",
    "cta_secondary": "Découvrir notre approche",
    "image_caption": "Melun, Seine-et-Marne",
    "metrics": [
      {"value": "1000€", "label": "Capital social"},
      {"value": "100%", "label": "Indépendance"},
      {"value": "CIF", "label": "Conseil agréé"}
    ]
  },
  "manifesto": {
    "eyebrow": "Notre conviction",
    "quote_before": "La finance est un levier de ",
    "quote_emphasis": "liberté",
    "quote_after": " quand elle est bien maîtrisée.",
    "body": "Chez MYFINEO, nous croyons qu'un conseil de qualité repose sur une compréhension profonde de vos aspirations. Notre mission est de transformer vos actifs en projets de vie concrets, avec une éthique rigoureuse et une transparence totale.",
    "founder_name": "MYFINEO",
    "founder_role": "Conseil en Patrimoine"
  },
  "values": {
    "eyebrow": "Nos engagements",
    "h2_main": "Trois piliers de",
    "h2_emphasis": "confiance.",
    "intro": "Notre approche repose sur des principes fondamentaux pour garantir la sécurité et la performance de vos investissements.",
    "entries": [
      {"title": "Indépendance", "body": "En tant que mandataire non exclusif, nous sélectionnons les meilleures solutions du marché sans aucun conflit d'intérêt."},
      {"title": "Rigueur", "body": "Enregistré à l'ORIAS et membre de la CNCEF PATRIMOINE, nous suivons les standards les plus élevés de la profession."},
      {"title": "Accompagnement", "body": "Nous restons à vos côtés à chaque étape de votre vie financière pour adapter votre stratégie aux évolutions du marché."}
    ]
  },
  "services": {
    "eyebrow": "Nos expertises",
    "h2_main": "Des solutions",
    "h2_emphasis": "sur mesure.",
    "intro": "MYFINEO vous accompagne sur l'ensemble de vos besoins financiers et immobiliers avec une vision transversale.",
    "main_service": {
      "num": "01 — Conseil global",
      "title": "Bilan Patrimonial",
      "description": "Une analyse exhaustive de votre situation pour définir une stratégie d'investissement cohérente et performante.",
      "is_main": true
    },
    "other_services": [
      {"num": "02", "title": "Assurance", "description": "Mandataire d'intermédiaire d'assurance pour la protection de votre famille et de vos biens, sous le contrôle de l'ACPR. Nous sélectionnons les meilleurs contrats de prévoyance et d'épargne.", "is_main": false},
      {"num": "03", "title": "Immobilier", "description": "Transactions en immeubles et fonds de commerce sans manipulation de fonds, titulaire de la Carte Professionnelle Immobilière. Un accompagnement complet pour vos projets d'investissement locatif.", "is_main": false},
      {"num": "04", "title": "Banque", "description": "Mandataire non exclusif en Opérations de Banques et en Services de Paiement pour optimiser vos financements. Nous vous aidons à trouver les meilleures conditions de crédit pour vos projets.", "is_main": false},
      {"num": "05", "title": "Placements", "description": "Sélection rigoureuse de produits financiers adaptés à votre profil de risque et à votre horizon de placement. Une gestion active pour maximiser le potentiel de votre capital financier.", "is_main": false}
    ]
  },
  "approach": {
    "eyebrow": "Notre méthode",
    "h2_main": "Un parcours",
    "h2_emphasis": "structuré.",
    "body_p1": "Nous commençons par une phase d'écoute active pour identifier vos besoins réels et vos contraintes.",
    "body_p2": "Ensuite, nous élaborons une stratégie personnalisée que nous suivons rigoureusement au fil du temps.",
    "steps": [
      {"num": "01", "title": "Découverte", "body": "Entretien initial pour comprendre votre situation actuelle et vos ambitions futures."},
      {"num": "02", "title": "Stratégie", "body": "Conception d'un plan d'action détaillé incluant placements, immobilier et protection."},
      {"num": "03", "title": "Suivi", "body": "Révisions régulières de votre portefeuille pour garantir l'alignement avec vos objectifs."}
    ]
  },
  "testimonial": {
    "eyebrow": "Témoignage",
    "quote": "L'expertise de MYFINEO m'a permis de structurer mon patrimoine avec sérénité. Un conseil vraiment indépendant et à l'écoute.",
    "name": "Jean-Pierre D.",
    "initials": "JPD",
    "role": "Entrepreneur"
  },
  "contact": {
    "eyebrow": "Contact",
    "h2_main": "Parlons de vos",
    "h2_emphasis": "projets.",
    "lead": "Prenez rendez-vous en ligne ou contactez-nous par téléphone pour un premier échange sans engagement.",
    "hours": "Lun — Ven · 9h — 19h",
    "office": "Sur rendez-vous",
    "form_title": "Demande de contact",
    "form_subtitle": "Nous vous répondons sous 24h."
  },
  "footer_description": "MYFINEO est une SARL de conseil en investissements financiers et gestion de patrimoine, enregistrée à l'ORIAS et membre de la CNCEF PATRIMOINE."
}
"""

def main():
    slug = "myfineo"
    print(f"Building mock site for {slug}")
    
    # 1. Parse JSON and Create SiteContent object
    data = json.loads(CONTENT_JSON)
    content = SiteContent.model_validate(data)
    
    # 2. Pick hero image
    content.hero_image_url = pick_hero_image(content.sector, content.slug)
    
    # 3. Render to disk
    html_path = render_to_disk(content)
    print(f"✓ Rendered to {html_path}")
    
    # 4. Update DB
    repo = BuildsRepo()
    repo.upsert_pending(slug, "MYFINEO")
    repo.mark_building(slug)
    repo.mark_rendered(
        slug=slug,
        content_json=content.model_dump_json(),
        html_path=str(html_path),
        llm_cost_usd=0.0
    )
    print("✓ DB updated")

if __name__ == "__main__":
    main()
