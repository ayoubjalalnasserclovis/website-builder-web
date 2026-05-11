# Website Builder — agentic site generator pour PME françaises

Un builder Python léger qui transforme un CSV (nom + texte source) en sites HTML
prêts à déployer, avec un design éditorial type banque privée. Pensé pour
fonctionner en local sur ton laptop, scaler à des milliers de sites/mois, et
rester sous 100 € de budget mensuel.

## Architecture

```
CSV  →  ContentAgent (LLM via OpenRouter)  →  SiteContent (Pydantic, validé)
                                                      ↓
                            Image picker (Unsplash, par secteur)
                                                      ↓
                                     Jinja2 template (banque_privee)
                                                      ↓
                                  dist/<slug>/index.html  +  SQLite state
```

- **Agentic-first** mais léger : le LLM produit du JSON structuré, validé par
  Pydantic. Si la validation échoue, l'agent retry avec le détail des erreurs.
- **Solide** : idempotence par slug, reprise sur crash via état SQLite, plafond
  budget LLM en dur, fallback de modèle (Claude Haiku → GPT-4o-mini).
- **Pas de framework lourd** : openai SDK pointé vers OpenRouter, Jinja2,
  Pydantic, asyncio. C'est tout.

## Setup (5 minutes)

```bash
# 1. Crée un venv
python3 -m venv .venv
source .venv/bin/activate

# 2. Installe les dépendances
pip install -e .

# 3. Configure
cp .env.example .env
# Edite .env et mets ta clé OPENROUTER_API_KEY (https://openrouter.ai)
```

## Build un seul site

```bash
python scripts/build_one.py \
  --name "Influence Patrimoine" \
  --slug influence-patrimoine \
  --sector wealth_management \
  --phone "09 81 94 88 08" \
  --phone-tel "+33981948808" \
  --email "contact@influence-patrimoine.fr" \
  --text-file source.txt
```

Résultat : `dist/influence-patrimoine/index.html`. Ouvre dans le navigateur.

## Build en masse depuis un CSV

```bash
python scripts/build_all.py prospects.example.csv
```

Options :
- `--concurrency 10` : nombre de prospects buildés en parallèle (défaut 5)
- `--budget 5` : plafond LLM en USD (le run s'arrête net si dépassé)
- `--dry-run` : aucun appel API, juste validation du CSV

L'orchestrateur :
- Pre-load tous les prospects en `pending` dans SQLite
- Skip ceux déjà rendus (idempotence)
- Build avec `asyncio.Semaphore` pour la concurrence bornée
- Reprend les builds crashés (timeout 5 min sur `building` stale)
- Affiche un résumé final + table des statuts

## Format CSV

Colonnes acceptées (toutes optionnelles sauf `company_name`) :

| Colonne | Obligatoire | Description |
|---|---|---|
| `company_name` | oui | Nom de l'entreprise |
| `slug` | non | Auto-généré si absent (slugify du nom) |
| `source_text` | non | Texte brut du site existant ou notes |
| `sector_hint` | non | Indice de secteur (cf. liste dans `models.py`) |
| `phone` | non | Téléphone format affichage |
| `phone_tel` | non | Téléphone format `tel:` (avec préfixe pays) |
| `email` | non | Email de contact |
| `hero_image_url` | non | Override de l'image hero |

Voir `prospects.example.csv` pour un exemple.

## Test local sans API key

```bash
python tests/test_template_renders.py
```

Génère `dist/influence-patrimoine/index.html` à partir d'un contenu hardcodé.
Permet de vérifier que le template fonctionne sans dépendre d'OpenRouter.

Avec pytest :
```bash
pip install pytest
pytest tests/
```

## Coûts

À budget par défaut (`MAX_BUDGET_USD=10`) avec Claude Haiku :
- ~$0.005 par site (1 appel LLM ~3000 tokens entrée, ~1500 tokens sortie)
- 10 USD = ~2 000 sites
- Pour 10k sites/mois : ~50 USD de LLM

## Structure du repo

```
src/builder/
├── models.py          Pydantic schémas — contrat strict du contenu
├── config.py          .env loader
├── llm.py             Wrapper OpenRouter + tracking coût + retry
├── content_agent.py   L'agent qui produit du SiteContent depuis du raw input
├── image_picker.py    Mapping secteur → URL Unsplash curée
├── render.py          Jinja2 → HTML
├── db.py              SQLite (BuildsRepo)
├── builder.py         build_one() — pipeline single prospect
└── batch.py           build_all() — orchestrateur asyncio + CSV

templates/
└── banque_privee.html.j2   Template unique pour l'instant

scripts/
├── build_one.py
└── build_all.py

tests/
└── test_template_renders.py
```

## Phase 3 — Déploiement Cloudflare Pages

Les sites buildés dans `dist/` sont publiés en ligne en une seule commande,
chaque slug accessible à `https://<base>/<slug>/`.

### Pré-requis (one-time, ~5 minutes)

1. **Node.js + Wrangler** (Wrangler est un outil CLI Cloudflare officiel) :
   ```bash
   npm install -g wrangler
   ```
   Pas besoin de `wrangler login` — on passe par token API.

2. **Token API Cloudflare** :
   - Va sur https://dash.cloudflare.com/profile/api-tokens
   - "Create Token" → template "Cloudflare Pages : Edit"
   - Copie le token

3. **Account ID** : visible en sidebar droite du dashboard Cloudflare.

4. **Remplis `.env`** :
   ```env
   CLOUDFLARE_API_TOKEN=<ton-token>
   CLOUDFLARE_ACCOUNT_ID=<ton-account-id>
   CLOUDFLARE_PAGES_PROJECT=demos
   PUBLIC_BASE_URL=https://demos.tondomaine.fr   # optionnel, sinon *.pages.dev
   ```

5. **(Optionnel)** Domaine custom : dans le dashboard Pages > settings > domains,
   ajoute ton domaine et configure le DNS comme indiqué. Sinon, les sites seront
   accessibles à `https://<project>.pages.dev/<slug>/`.

### Vérifier la config sans déployer

```bash
python scripts/deploy.py --check
```

### Déployer

```bash
python scripts/deploy.py
```

- Détecte automatiquement si le projet Pages existe ; le crée sinon.
- Upload le contenu de `dist/` en une seule passe (un seul deploy = un seul
  compteur sur le free tier 500 deploys/mois).
- Met à jour `deployed_url` en DB pour chaque slug publié.
- Affiche une table récap des URLs publiques.

### Re-déploiement incrémental

Cloudflare Pages remplace tout le contenu du projet à chaque deploy. Workflow
recommandé :

1. `python scripts/build_all.py prospects.csv` → ajoute les nouveaux slugs à `dist/`
2. `python scripts/deploy.py` → publie tout `dist/` (anciens + nouveaux)

Tant que tu ne supprimes pas `dist/<slug>/`, les anciens sites restent en ligne.

## Phase 4 — QA visuel automatique

Avant de déployer, on valide chaque site via un agent QA qui prend un screenshot
Chromium puis demande à un LLM vision de noter sur 10. Sites < 7 ou avec un
finding `critical` ne sont pas déployés.

### Setup (one-time)

```bash
pip install -e .[qa]
playwright install chromium

# Linux uniquement — installe les libs système nécessaires
sudo playwright install-deps
# ou en manuel sur Debian/Ubuntu :
# sudo apt-get install -y libatk1.0-0 libatk-bridge2.0-0 libnss3 \
#   libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libxfixes3 \
#   libgbm1 libxss1 libasound2 libpangocairo-1.0-0 libpango-1.0-0
```

### Lancer le QA

```bash
# QA tous les sites en statut 'rendered' ou 'qa_rejected'
python scripts/qa.py

# QA un seul site
python scripts/qa.py --slug influence-patrimoine

# Afficher la liste des sites rejetés (sans relancer)
python scripts/qa.py --list-rejected
```

### Pipeline complet avec QA

```bash
python scripts/build_all.py prospects.csv   # build → status='rendered'
python scripts/qa.py                         # QA   → status='qa_passed' ou 'qa_rejected'
python scripts/deploy.py                     # deploy uniquement les passés
```

### Coût QA

Avec Gemini 2.5 Flash (défaut) : ~$0.001 par site QA. 1000 sites = $1. Le score
est plus important que le prix — on peut switcher vers Claude 3.5 Sonnet (plus
cher mais meilleur jugement esthétique) en changeant `LLM_MODEL_QA` dans `.env`.

### Règle métier (verdict)

```
final_verdict = "pass"  ⟺  score >= QA_SCORE_THRESHOLD  ET  aucun finding 'critical'
```

Le verdict du LLM est *advisory* — la règle ci-dessus est appliquée par-dessus,
côté code Python. Si le LLM dit "pass" mais qu'on a un `critical`, c'est rejeté.
Et inversement.

### Bypass QA (déconseillé)

```bash
python scripts/deploy.py --no-qa-strict
```

Publie tout `dist/`, ignore le statut QA. À utiliser uniquement quand tu sais
ce que tu fais.

## Phase 5 — Brand DNA dynamique (palette + typo + ambiance par site)

**Le builder ne produit plus le même site pour tout le monde.** Chaque entreprise
reçoit son ADN visuel propre, généré par un agent design qui suit un playbook
détaillé (`skills/design_director.md`).

### Ce qui change

| Avant Phase 5 | Après Phase 5 |
|---|---|
| 1 palette navy/crème/or | Palette dérivée du métier (terroir, matière, mood) |
| 1 paire typo Fraunces+Inter | 12 paires Google Fonts approuvées, choisies par l'agent |
| 1 template `banque_privee` | 1 template skeleton + tokens CSS variables |
| Site identique pour 1000 entreprises | Site visuellement unique par entreprise |

### Architecture

```
Prospect (CSV) → BrandAgent (lit skills/design_director.md) → BrandDNA
                                                                ↓
                              ContentAgent → SiteContent (incluant brand)
                                                                ↓
                              render_html() → CSS variables + Google Fonts URL
                                                                ↓
                                            HTML final (visuellement unique)
```

### Le skill, c'est le cœur

`skills/design_director.md` définit comment l'agent prend ses décisions :
- 6 principes non-négociables (sobriété, spécificité, accessibilité…)
- Une grille de couleur par secteur (12 secteurs × 3 exemples de palette)
- 12 paires typographiques approuvées
- 5 moods, 3 layout variants
- Une checklist mentale de self-verification

Le skill est en markdown, donc itérable sans toucher au code Python. Pour
améliorer la qualité visuelle moyenne, tu édites le skill — tout le reste suit.

### Démo de variété visuelle

```bash
python scripts/demo_variety.py
```

Construit 3 sites totalement différents avec 3 BrandDNA contrastés :
- `influence-patrimoine` : navy/parchemin/or, Fraunces, refined
- `maison-laurent` : vert sapin/butter/walnut, Cormorant Garamond, warm
- `atelier-mercier` : terracotta/plâtre/ardoise, Bricolage Grotesque, grounded

Tous rendus via le même template `editorial_classic.html.j2`. Aucune duplication.

## Phase 6 — Cold email via Instantly (RGPD-compliant)

Pour chaque prospect en `status=deployed` (la démo est en ligne), un email
personnalisé est généré en français + poussé vers une campagne Instantly.

### Mécanisme

```
Prospect (deployed) ─────────┐
   ├─ filtre RGPD : email pro uniquement (pas gmail/orange/free…)
   ├─ EmailAgent (skills/cold_email_writer.md) → ColdEmail (subject, body_html, body_text)
   └─ InstantlyClient.add_lead_to_campaign() → lead poussé dans la campagne
                                                ↓
                       Instantly envoie selon sa séquence + warm-up + opt-out auto
```

Le `body_html` contient OBLIGATOIREMENT (validation Pydantic) le placeholder
`{{unsubscribe_link}}` qu'Instantly remplace par un lien fonctionnel — sans
quoi le code refuse d'envoyer (conformité RGPD non négociable).

### Setup côté Instantly (one-time)

1. Crée un compte Instantly + connecte tes inboxes (avec warm-up déjà fait).
2. Crée une **campagne** vide. Dans la séquence (étape 1) :
   - Subject : `{{personalization.subject}}`
   - Body :    `{{personalization.body_html}}`
3. Active "Auto-warm-up" + définis daily limit ≤ 50/inbox/jour.
4. Récupère le **campaign ID** dans l'URL Instantly.
5. Génère une **API key** dans Settings > Integrations.

### Setup .env

```env
INSTANTLY_API_KEY=instkey_xxx
INSTANTLY_CAMPAIGN_ID=clk....

# Identité expéditeur — RGPD obligatoire
SENDER_NAME=Alex Dubois
SENDER_ROLE=Cofondateur
SENDER_COMPANY=Mon Agence Web SAS
SENDER_SIREN=903456789
SENDER_ADDRESS=12 rue de la République, 75011 Paris
SENDER_PHONE=+33612345678
SENDER_REPLY_TO=alex@monagenceweb.fr
```

### Workflow

```bash
# Pre-flight (vérifie config + identité expéditeur)
python scripts/send_emails.py --check

# Voir les prospects à contacter (incl. statut RGPD de chaque email)
python scripts/send_emails.py --list-pending

# Dry-run : génère les emails sans pousser à Instantly
python scripts/send_emails.py --dry-run --limit 3

# Envoi réel (par batch, le code marque idempotemment chaque envoi en DB)
python scripts/send_emails.py --limit 50

# Pour relancer après échec, rien à faire : les rows en email_error sont skippées,
# tu corriges la cause (ex: créer la campagne, scope du token), puis tu reset
# l'erreur côté DB :  UPDATE builds SET email_error = NULL WHERE slug = 'xxx';
```

### Conformité RGPD — ce que le code garantit

| Règle CNIL | Garantie côté code |
|---|---|
| Cible exclusivement B2B | `is_business_email()` filtre 30 domaines persos (gmail, orange.fr, free.fr…) avant l'appel LLM |
| Mentions légales identifiant l'expéditeur | `SenderIdentity` Pydantic exige nom, société, SIREN, adresse — l'agent les injecte dans chaque body |
| Lien d'opt-out fonctionnel | `ColdEmail.body_html` valide que `{{unsubscribe_link}}` est présent — sans quoi Pydantic rejette |
| Base légale documentée | Le skill instruit l'agent à mentionner "intérêt légitime art. 6.1.f" en mentions |
| Suppression sur demande | Instantly gère la suppression list automatiquement (côté plateforme) |
| Idempotence (pas de spam) | `email_sent_at` + `email_error` en DB = jamais d'envoi en double |

### Coûts Phase 6

- LLM : ~$0.001 par email (Claude Haiku, ~1500 tokens). 1000 emails = $1.
- Instantly : ~$37/mois plan Growth (illimités contacts, 5k emails/jour).
- Domaines alternatifs : ~10 €/an chacun (3-5 recommandés pour distribuer la charge).

## Ce qui reste à faire (prochaines phases)

- **Phase 5.5 — Plus de squelettes** : `editorial_asymmetric` et `gallery_minimal`
  (le `BrandDNA.layout_variant` est déjà prêt, juste à écrire les templates)
- **Phase 7 — Image picker dynamique** : keywords par entreprise (vs sector mapping)
- **Phase 8 — Reply detection** : webhook Instantly → classification réponses
  (intéressé / pas maintenant / négatif / opt-out) → routage automatique

## Gestion des erreurs

Chaque build peut échouer à 4 endroits :
1. CSV mal formé → ligne ignorée avec warning
2. LLM produit du JSON invalide → 2 retries avec feedback d'erreur, puis `failed`
3. Pydantic rejette le contenu → idem, retry avec détail des erreurs
4. Jinja crash → marqué `failed` avec stack trace dans `error`

Pour relancer les `failed` : il suffit de relancer `build_all.py` — la repo
remet automatiquement les `failed` en `pending`.
