"""Demonstrate dynamic Brand DNA — render 3 different companies with 3 different
visual identities to prove the template adapts (palette, typography, mood).

What this proves:
  - Same template skeleton (editorial_classic.html.j2)
  - Three completely different visual results: navy/cream/gold + Fraunces vs
    deep green/butter/walnut + Cormorant vs terracotta/concrete + Bricolage
  - No template duplication, all driven by the BrandDNA model

This script bakes the content + brand DNA inline so it can run without an
OpenRouter API key — useful for testing visual fidelity end-to-end. In
production, the BrandAgent + ContentAgent generate everything from CSV input.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rich.console import Console

from builder.image_picker import pick_hero_image
from builder.models import (
    ApproachContent,
    BrandDNA,
    Branding,
    ContactContent,
    HeroContent,
    HeroMetric,
    ManifestoContent,
    Palette,
    Service,
    ServicesContent,
    SiteContent,
    Step,
    TestimonialContent,
    Typography,
    Value,
    ValuesContent,
)
from builder.render import render_to_disk

console = Console()


# =============================================================================
# Influence Patrimoine — refined wealth management, navy / cream / gold
# =============================================================================

INFLUENCE_PATRIMOINE = SiteContent(
    slug="influence-patrimoine",
    sector="wealth_management",
    meta_description=(
        "Cabinet de conseil en gestion de patrimoine indépendant. Stratégies sur mesure "
        "pour créer, développer et transmettre votre patrimoine. Confiance, transparence, écoute."
    ),
    branding=Branding(
        name="Influence Patrimoine", subtitle="Conseil indépendant", letter="i",
        professional_membership="CIF · ANACOFI",
        phone="09 81 94 88 08", phone_tel="+33981948808",
        email="contact@influence-patrimoine.fr",
    ),
    hero=HeroContent(
        eyebrow="Conseiller en gestion de patrimoine",
        h1_line1="Rêvons", h1_line2="ensemble",
        h1_line3_before="votre ", h1_line3_emphasis="patrimoine.", h1_line3_after="",
        subtitle=(
            "Cabinet indépendant à vos côtés pour créer, développer et transmettre votre "
            "patrimoine. Une approche humaine, sur le long terme, sans conflit d'intérêts."
        ),
        cta_primary="Premier rendez-vous offert", cta_secondary="Découvrir notre approche",
        image_caption="Paris, VIIIᵉ",
        metrics=[
            HeroMetric(value="15+", label="années d'expérience"),
            HeroMetric(value="100%", label="indépendance & transparence"),
            HeroMetric(value="5", label="expertises patrimoniales"),
        ],
    ),
    manifesto=ManifestoContent(
        eyebrow="Notre conviction",
        quote_before="Le métier de conseiller en gestion de patrimoine est un métier ",
        quote_emphasis="humain", quote_after=" avant tout.",
        body=(
            "Nous mettons nos qualités d'écoute et notre savoir-faire au service de vos "
            "projets de vie. Pas de produit standardisé, pas de discours pré-écrit. Une "
            "stratégie pensée pour vous, ajustée dans le temps, expliquée simplement."
        ),
        founder_name="Jérémie", founder_role="Fondateur & conseiller patrimonial",
    ),
    values=ValuesContent(
        eyebrow="Nos engagements", h2_main="Trois principes", h2_emphasis="non négociables.",
        intro=(
            "Avant les performances, avant les rendements, avant les opportunités, il y a la "
            "relation que nous construisons avec vous."
        ),
        entries=[
            Value(title="Confiance", body=(
                "La confiance se gagne au fil des années. Nous nous engageons à être vos "
                "compagnons de route sur la durée — disponibles, accessibles, présents.")),
            Value(title="Transparence", body=(
                "Nos honoraires, partenariats, rémunérations : tout est expliqué clairement "
                "dès le premier échange. Aucune zone d'ombre, aucun produit imposé.")),
            Value(title="Honnêteté", body=(
                "Nous vous disons ce que nous pensons, même quand cela contredit vos "
                "intuitions. Une stratégie patrimoniale solide se construit sur la lucidité.")),
        ],
    ),
    services=ServicesContent(
        eyebrow="Nos expertises", h2_main="Cinq domaines,", h2_emphasis="une stratégie globale.",
        intro=(
            "Votre patrimoine est un tout. Nous l'abordons avec une vision d'ensemble — "
            "fiscale, immobilière, financière, successorale."
        ),
        main_service=Service(num="01 — Approche globale", title="Bilan patrimonial complet",
            description=(
                "Audit approfondi : liquidités, placements, immobilier, retraite, fiscalité, "
                "succession. Une cartographie précise pour identifier les leviers."
            ), is_main=True),
        other_services=[
            Service(num="02", title="Immobilier", description=(
                "Constitution et valorisation de votre patrimoine immobilier. Pinel, Malraux, "
                "LMNP, SCPI, monuments historiques.")),
            Service(num="03", title="Épargne & placements", description=(
                "Assurance-vie, PEA, PER, contrats de capitalisation. Allocation alignée sur "
                "votre profil et votre horizon, pilotée dans la durée.")),
            Service(num="04", title="Retraite & prévoyance", description=(
                "Anticiper votre retraite, c'est protéger votre niveau de vie. Madelin, PER, "
                "contrats sur mesure pour structurer vos revenus futurs.")),
            Service(num="05", title="Défiscalisation", description=(
                "La défiscalisation ne s'improvise pas. Nous l'inscrivons dans une stratégie "
                "de long terme, pour réduire vos impôts sans dégrader le patrimoine.")),
        ],
    ),
    approach=ApproachContent(
        eyebrow="Notre méthode", h2_main="Une démarche", h2_emphasis="en trois temps.",
        body_p1=(
            "Le rôle d'un conseiller en gestion de patrimoine ne se résume pas à recommander "
            "des placements. C'est une démarche structurée — comprendre, analyser, construire."
        ),
        body_p2=(
            "Nous prenons le temps. Un premier rendez-vous offert, sans engagement. Puis un "
            "travail approfondi, des recommandations claires, et un suivi régulier."
        ),
        steps=[
            Step(num="01", title="Écouter & comprendre", body=(
                "Premier rendez-vous offert. Nous explorons votre situation actuelle, vos "
                "projets de vie, votre appétence au risque, vos contraintes.")),
            Step(num="02", title="Auditer & recommander", body=(
                "Bilan patrimonial complet remis sous forme écrite, accompagné de "
                "recommandations chiffrées. Vous décidez en toute conscience.")),
            Step(num="03", title="Accompagner dans la durée", body=(
                "Mise en œuvre des solutions retenues, point annuel, ajustements à chaque "
                "évolution de votre vie ou de la fiscalité.")),
        ],
    ),
    testimonial=TestimonialContent(
        eyebrow="Ils nous font confiance",
        quote=(
            "Jérémie m'a fait découvrir des choses que je ne connaissais pas. Quelques "
            "chiffres clefs et il m'a orienté vers les bonnes opportunités. Nous avons revu "
            "toute la structure de ma société, je lui fais entièrement confiance."
        ),
        name="Franck Verrechia", initials="FV", role="Chef d'entreprise",
    ),
    contact=ContactContent(
        eyebrow="Prenons rendez-vous", h2_main="Parlons de votre", h2_emphasis="patrimoine.",
        lead=(
            "Premier rendez-vous offert, sans engagement. En cabinet, en visioconférence ou "
            "chez vous — c'est vous qui choisissez."
        ),
        hours="Lun — Ven · 9h — 19h", office="Sur rendez-vous",
        form_title="Demande de rendez-vous", form_subtitle="Réponse personnelle sous 24 heures ouvrées.",
    ),
    footer_description=(
        "Cabinet de conseil en gestion de patrimoine indépendant. Membre de l'ANACOFI, "
        "conformité CIF & IAS."
    ),
    hero_image_url=pick_hero_image("wealth_management", "influence-patrimoine"),
    brand=BrandDNA(
        palette=Palette(
            bg="#F4EFE5", surface="#EAE3D2", text="#1B1B1F",
            primary="#14213D", secondary="#B89968",
        ),
        typography=Typography(display_font="Fraunces", body_font="Inter"),
        mood="refined",
        layout_variant="editorial_classic",
        rationale=(
            "Palette navy / parchemin / or assumée pour évoquer la banque privée parisienne. "
            "Fraunces apporte la voix éditoriale moderne, Inter la lisibilité du corps de texte."
        ),
    ),
)


# =============================================================================
# Maison Laurent — restaurant gastronomique étoilé, vert sapin / butter / walnut
# =============================================================================

MAISON_LAURENT = SiteContent(
    slug="maison-laurent",
    sector="restaurant",
    meta_description=(
        "Restaurant gastronomique à Lyon. Cuisine française moderne par le chef Antoine "
        "Laurent, étoilé Michelin. 24 couverts, cave de 800 références, menu dégustation."
    ),
    branding=Branding(
        name="Maison Laurent", subtitle="Restaurant gastronomique", letter="L",
        professional_membership="",
        phone="04 78 27 19 83", phone_tel="+33478271983",
        email="reservation@maison-laurent.fr",
    ),
    hero=HeroContent(
        eyebrow="Cuisine d'auteur, Lyon",
        h1_line1="Une table", h1_line2="qui prend",
        h1_line3_before="son ", h1_line3_emphasis="temps.", h1_line3_after="",
        subtitle=(
            "Vingt-quatre couverts, une cuisine ouverte, le marché du matin sur l'assiette. "
            "Antoine Laurent compose chaque jour un menu unique, ancré dans le terroir."
        ),
        cta_primary="Réserver une table", cta_secondary="Voir le menu du jour",
        image_caption="Lyon, IIᵉ",
        metrics=[
            HeroMetric(value="24", label="couverts"),
            HeroMetric(value="800", label="références cave"),
            HeroMetric(value="1*", label="étoile Michelin"),
        ],
    ),
    manifesto=ManifestoContent(
        eyebrow="Notre maison",
        quote_before="Cuisiner, c'est ",
        quote_emphasis="recevoir", quote_after=", pas servir.",
        body=(
            "Antoine Laurent compose chaque service comme on accueille un ami. Un menu unique "
            "construit le matin avec les producteurs, sept séquences pensées pour s'enchaîner. "
            "Pas de carte fixe : la saison, le marché, l'envie du jour."
        ),
        founder_name="Antoine Laurent", founder_role="Chef & propriétaire",
    ),
    values=ValuesContent(
        eyebrow="Notre cuisine", h2_main="Trois obsessions,", h2_emphasis="une seule table.",
        intro=(
            "Notre proposition tient en trois mots : produit, geste, attention. Tout part "
            "de là, et tout y revient."
        ),
        entries=[
            Value(title="Produit", body=(
                "Soixante-dix pour cent de nos produits viennent de moins de cent kilomètres. "
                "Nous travaillons avec quinze producteurs, par leur prénom, depuis dix ans.")),
            Value(title="Geste", body=(
                "Nous cuisinons devant vous. Le feu, le couteau, la main. Aucun artifice. "
                "Chaque plat se construit en cinq à sept gestes maximum.")),
            Value(title="Attention", body=(
                "Vingt-quatre couverts, une équipe de huit, un service à six mains par "
                "table. Nous nous souvenons de votre nom, de votre verre, de vos allergies.")),
        ],
    ),
    services=ServicesContent(
        eyebrow="Nos formules", h2_main="Un menu", h2_emphasis="pour chaque envie.",
        intro=(
            "Quatre formules, du déjeuner court au menu dégustation en sept séquences. "
            "Toutes accessibles à la réservation, accord mets-vins en option."
        ),
        main_service=Service(num="01 — Pièce maîtresse", title="Menu Dégustation 7 séquences",
            description=(
                "Sept temps composés le matin avec ce que les producteurs ont apporté. "
                "Optionnel : accord mets-vins en sept verres, ou option au verre à la commande."
            ), is_main=True),
        other_services=[
            Service(num="02", title="Déjeuner du marché", description=(
                "Trois temps à l'ardoise, formule du midi. Le rapport qualité-prix qui nous "
                "tient à cœur, sans concession sur le produit.")),
            Service(num="03", title="Carte sur mesure", description=(
                "Le soir uniquement. Vous choisissez 4 à 6 plats parmi notre suggestion "
                "quotidienne, à la composition libre. Sur réservation 48h à l'avance.")),
            Service(num="04", title="Privatisation", description=(
                "Restaurant complet pour vingt-quatre convives. Menu défini avec vous à la "
                "carte, accompagnement sommelier dédié, service en six mains.")),
            Service(num="05", title="Cave", description=(
                "Huit cents références dont deux cents en biodynamie. Notre sommelier propose "
                "des accords au verre, à la bouteille ou à la carte sans accord imposé.")),
        ],
    ),
    approach=ApproachContent(
        eyebrow="Le service", h2_main="Comment se passe", h2_emphasis="un dîner ici.",
        body_p1=(
            "Nous ouvrons à 19 heures, le service commence ensemble. Dès l'arrivée, un verre "
            "vous est servi pendant que vous découvrez la salle ouverte sur la cuisine."
        ),
        body_p2=(
            "Comptez deux heures trente pour le menu dégustation, deux heures pour la carte. "
            "Notre rythme est lent par construction — chaque plat appelle une conversation."
        ),
        steps=[
            Step(num="01", title="Accueil & apéritif", body=(
                "Verre offert à votre arrivée. Présentation du menu du jour, choix de la "
                "formule. Pour les habitués, on va droit aux gestes signature.")),
            Step(num="02", title="Service en cuisine ouverte", body=(
                "Vous voyez chaque plat se composer. Antoine et son équipe travaillent à six "
                "mètres de votre table. Les questions sont les bienvenues.")),
            Step(num="03", title="Mignardises & café", body=(
                "Trois pièces sucrées choisies dans la matinée. Café de torréfacteur lyonnais, "
                "infusions du jardin partagé du quartier.")),
        ],
    ),
    testimonial=TestimonialContent(
        eyebrow="Ils en ont parlé",
        quote=(
            "Antoine Laurent fait partie de cette nouvelle génération qui réinvente le geste "
            "lyonnais sans le trahir. Le menu dégustation est l'un des plus émouvants que "
            "j'aie mangés cette année — précis, généreux, profondément attaché au terroir."
        ),
        name="Camille Roumegas", initials="CR", role="Le Figaro Magazine",
    ),
    contact=ContactContent(
        eyebrow="Réserver", h2_main="Une table", h2_emphasis="pour vous.",
        lead=(
            "Vingt-quatre couverts, deux services par soir. Nous prenons les réservations "
            "jusqu'à six semaines à l'avance, et tenons une liste d'annulations active."
        ),
        hours="Mar — Sam · 19h & 21h30", office="14 rue Mercière, 69002 Lyon",
        form_title="Demande de réservation",
        form_subtitle="Confirmation par téléphone sous 12 heures.",
    ),
    footer_description=(
        "Restaurant gastronomique étoilé Michelin, ouvert depuis 2012. Cuisine d'auteur "
        "ancrée dans le terroir lyonnais, par Antoine Laurent."
    ),
    hero_image_url=pick_hero_image("restaurant", "maison-laurent"),
    brand=BrandDNA(
        palette=Palette(
            bg="#F2E8D0",      # butter cream
            surface="#E8DCC0",  # warmer butter
            text="#1F2517",     # ink-dark green
            primary="#2A4F3A",  # vert sapin
            secondary="#8B5A3C",  # walnut
        ),
        typography=Typography(display_font="Cormorant Garamond", body_font="Inter"),
        mood="warm",
        layout_variant="editorial_classic",
        rationale=(
            "Palette inspirée du terroir : vert sapin de la salle à manger, butter de la "
            "nappe, walnut du bois des tables. Cormorant Garamond apporte la rondeur "
            "italienne d'une carte de bistrot soigné, Inter garde la lisibilité moderne."
        ),
    ),
)


# =============================================================================
# Atelier Mercier — menuisier ébéniste d'art, terracotta / concrete / charcoal
# =============================================================================

ATELIER_MERCIER = SiteContent(
    slug="atelier-mercier",
    sector="construction",
    meta_description=(
        "Menuisier ébéniste d'art à Bordeaux. Mobilier sur mesure, agencement intérieur, "
        "restauration de pièces anciennes. Atelier Mercier, depuis 1987."
    ),
    branding=Branding(
        name="Atelier Mercier", subtitle="Menuisier ébéniste · 1987", letter="M",
        professional_membership="Maître Artisan d'Art",
        phone="05 56 81 04 27", phone_tel="+33556810427",
        email="atelier@mercier-bois.fr",
    ),
    hero=HeroContent(
        eyebrow="Ébénisterie d'art, Bordeaux",
        h1_line1="Le bois,", h1_line2="le geste,",
        h1_line3_before="le ", h1_line3_emphasis="temps.", h1_line3_after="",
        subtitle=(
            "Trente-sept ans d'atelier. Mobilier sur mesure, agencement, restauration de "
            "pièces anciennes. Chaque projet est unique, conçu avec vous, fabriqué chez nous."
        ),
        cta_primary="Étudier votre projet", cta_secondary="Visiter l'atelier",
        image_caption="Bordeaux Bastide",
        metrics=[
            HeroMetric(value="37", label="ans d'atelier"),
            HeroMetric(value="100%", label="fabrication France"),
            HeroMetric(value="14", label="essences sourcées"),
        ],
    ),
    manifesto=ManifestoContent(
        eyebrow="Notre métier",
        quote_before="Un meuble, c'est un usage qui dure ",
        quote_emphasis="cinquante ans", quote_after=" — pas une saison.",
        body=(
            "Nous travaillons avec des essences locales de moins de trois cents kilomètres. "
            "Chaque pièce est dessinée à la main avant la première coupe, pensée pour vivre "
            "trois générations. La main et le bois — pas de placage, pas de raccourci."
        ),
        founder_name="Henri Mercier", founder_role="Maître ébéniste",
    ),
    values=ValuesContent(
        eyebrow="Notre engagement", h2_main="Trois exigences,", h2_emphasis="zéro compromis.",
        intro=(
            "Notre atelier ne fait pas tout. Mais ce qu'il fait, il le fait avec rigueur "
            "depuis trente-sept ans."
        ),
        entries=[
            Value(title="Matière", body=(
                "Bois massifs uniquement, chêne français, noyer européen, fruitiers locaux. "
                "Nous refusons les panneaux dérivés et les placages, sans exception.")),
            Value(title="Geste", body=(
                "Chaque assemblage est tracé à la main, scié à la lame, ajusté à la varlope. "
                "Le tour électrique est un outil, pas une méthode.")),
            Value(title="Durée", body=(
                "Garantie trente ans sur l'assemblage, à vie sur le suivi. Un meuble que "
                "nous avons fait reste notre responsabilité — réparation, restauration.")),
        ],
    ),
    services=ServicesContent(
        eyebrow="Nos savoir-faire", h2_main="Quatre métiers,", h2_emphasis="une seule main.",
        intro=(
            "Mobilier, agencement, restauration, marqueterie. Quatre disciplines distinctes "
            "qui partagent un atelier, une exigence et un nom."
        ),
        main_service=Service(num="01 — Cœur de métier", title="Mobilier sur mesure",
            description=(
                "Tables, bibliothèques, lits, bureaux. Conception sur plan ou esquisse, "
                "validation en maquette 1:5, fabrication en atelier sur trois à six mois."
            ), is_main=True),
        other_services=[
            Service(num="02", title="Agencement intérieur", description=(
                "Cuisines bois, dressings, escaliers, parquets et bibliothèques pleine "
                "hauteur. Pose et finition par notre équipe, pas de sous-traitance.")),
            Service(num="03", title="Restauration", description=(
                "Pièces anciennes XVIIIᵉ et XIXᵉ, mobilier de famille, instruments de "
                "musique en bois. Démontage, traitement, ré-assemblage à l'identique.")),
            Service(num="04", title="Marqueterie", description=(
                "Marqueterie de paille, de bois précieux, et restauration de marqueteries "
                "d'époque. Travail à la table, technique transmise de Patrice Lemaire.")),
            Service(num="05", title="Atelier ouvert", description=(
                "Visite de l'atelier sur rendez-vous. Stages de découverte d'une journée "
                "pour particuliers, accompagnement de projet sur trois soirées.")),
        ],
    ),
    approach=ApproachContent(
        eyebrow="Comment on travaille", h2_main="Du croquis", h2_emphasis="à la livraison.",
        body_p1=(
            "Trois à six mois de l'idée à la livraison, selon la pièce. Nous prenons trois à "
            "cinq projets en parallèle maximum — le bois ne se brusque pas, l'attention non "
            "plus."
        ),
        body_p2=(
            "Chaque projet commence par un dessin à main levée. Si le geste est juste, on "
            "passe à la maquette. Si la maquette tient debout, on coupe."
        ),
        steps=[
            Step(num="01", title="Croquis & dessin", body=(
                "Visite à votre domicile, prise de mesures. Dessin à la main du projet en "
                "deux à trois variantes, validation ensemble.")),
            Step(num="02", title="Maquette 1:5", body=(
                "Reproduction réduite en bois clair pour valider proportions, assemblages, "
                "matière. Vous repartez avec, vous décidez chez vous, sans pression.")),
            Step(num="03", title="Fabrication & livraison", body=(
                "Trois à six mois en atelier. Photos hebdomadaires sur le projet. Livraison "
                "et installation par nos soins, garantie trente ans signée le jour J.")),
        ],
    ),
    testimonial=TestimonialContent(
        eyebrow="Ils nous ont confié leur bois",
        quote=(
            "Henri a refait toute la bibliothèque de la propriété — sept mètres linéaires, "
            "chêne massif, marqueterie d'angle. Quatre mois d'atelier, trois visites pour "
            "voir avancer. Quinze ans plus tard, c'est encore notre plus belle pièce."
        ),
        name="Émilie Bastide-Charron", initials="EB", role="Particulier — Saint-Émilion",
    ),
    contact=ContactContent(
        eyebrow="Étudier votre projet", h2_main="Parlons", h2_emphasis="bois.",
        lead=(
            "Visite à votre domicile gratuite en Gironde. Ailleurs, devis sur plan ou photos. "
            "Premier dessin offert si le projet va au bout."
        ),
        hours="Mar — Sam · 9h — 18h", office="Atelier · 24 quai des Queyries, Bordeaux",
        form_title="Demande d'étude",
        form_subtitle="Réponse sous 48 heures, devis sous 15 jours après visite.",
    ),
    footer_description=(
        "Atelier de menuiserie ébénisterie d'art, fondé à Bordeaux en 1987. Mobilier sur "
        "mesure, agencement, restauration. Maître Artisan d'Art."
    ),
    hero_image_url=pick_hero_image("construction", "atelier-mercier"),
    brand=BrandDNA(
        palette=Palette(
            bg="#E8DDC9",        # raw plaster
            surface="#D4C4A8",    # darker plaster
            text="#1A1612",        # bois brûlé
            primary="#A04C2D",     # terracotta
            secondary="#3F3D3A",   # ardoise
        ),
        typography=Typography(display_font="Bricolage Grotesque", body_font="Inter"),
        mood="grounded",
        layout_variant="editorial_classic",
        rationale=(
            "Palette terracotta / plâtre / ardoise inspirée des matériaux de l'atelier — "
            "brique de Bordeaux, copeau de chêne, taille de pierre. Bricolage Grotesque "
            "porte le geste, sans sérif lisse — le métier doit se voir."
        ),
    ),
)


def main():
    sites = [INFLUENCE_PATRIMOINE, MAISON_LAURENT, ATELIER_MERCIER]
    console.print(f"[bold]Building {len(sites)} sites with distinct Brand DNAs...[/]\n")

    for site in sites:
        out = render_to_disk(site)
        b = site.brand
        console.print(
            f"[green]✓[/] {site.slug:30s} "
            f"palette[{b.palette.bg} · {b.palette.primary} · {b.palette.secondary}] "
            f"fonts[{b.typography.display_font} + {b.typography.body_font}] "
            f"mood[{b.mood}]"
        )
        console.print(f"  → {out}\n")


if __name__ == "__main__":
    main()
