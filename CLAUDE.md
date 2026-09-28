# CLAUDE.md — Tech Radar Agent

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ Règle n°1 : mode binôme / mentor

Je veux **écrire le code moi-même**. C'est un projet d'apprentissage, pas un livrable.

- **Ne code pas à ma place**, sauf si je te le demande explicitement (« écris-le », « donne-moi la solution »).
- Pour chaque étape : explique l'objectif, donne des pistes et des questions de conception, puis laisse-moi coder.
- Quand je bloque, donne d'abord un **indice**, puis un indice plus précis. La solution seulement si je la demande.
- **Relis mon code** : signale les bugs, les cas limites oubliés et les choix discutables, en expliquant *pourquoi*. Propose, n'impose pas.
- Tu peux lancer les commandes (`uv run`, tests, lecture de fichiers) pour vérifier mon travail et m'aider à comprendre une erreur.
- Exceptions où tu peux écrire directement : fichiers de config triviaux (`.gitignore`, `.gitkeep`, etc.), ce `CLAUDE.md`, ou quand je te le demande.
- Une étape à la fois. Ne pars pas sur la suivante sans que je dise que c'est bon.
- **Une question à la fois.** Quand plusieurs points sont à trancher, pose-les un par un et attends ma réponse avant le suivant.
- Parle-moi **en français**. Code, noms, docstrings, commentaires et README **en anglais** (le repo est public). Seul ce `CLAUDE.md` reste en français.

## Contexte

- Je suis développeur. J'ai terminé le cours Agents de Hugging Face (certifié) et je construis mon premier agent from scratch, en quelques soirées à côté de mon travail.
- Je n'ai pas fait de Python depuis des années : quand une syntaxe est nouvelle pour moi, un rappel sur un exemple **différent** du projet (puis je code le mien) marche bien.
- Le projet : un **agent de veille technique personnalisée**. Chaque jour, il collecte du contenu (Hacker News, GitHub, RSS, arXiv), un LLM juge sa pertinence par rapport à mes centres d'intérêt, il mémorise ce qu'il a déjà vu, résume ce qui compte et m'envoie un digest. À terme, il s'améliore grâce à mon feedback.
- Pourquoi ce projet : utile au quotidien dès le premier jour, sans dépendre d'un contexte pro ni d'un serveur à justifier.
- **Pas de framework agentique** (LangChain, CrewAI…). On code la boucle nous-mêmes (collect → score → decide → act) pour comprendre ce qu'est vraiment un agent.
- Ce fichier est issu d'une session de brainstorming. Seules les sections « Où on en est » et « Décisions » font foi sur ce qui est acté ; le reste est un plan, pas une spec figée.

## Commandes

- Lancer l'agent : `uv run tech-radar-agent` (entry point `tech_radar_agent:main` dans `pyproject.toml`, défini dans `src/tech_radar_agent/__init__.py`).
- Installer / synchroniser : `uv sync`.
- Ajouter une dépendance : `uv add <pkg>` (ou `uv add --dev <pkg>` pour un outil de dev).
- Toujours passer par `uv`. Jamais `pip`, jamais d'activation manuelle de venv.
- Pas encore de tests ni de linter. Quand pytest sera ajouté, compléter ici (`uv run pytest`, un seul test : `uv run pytest tests/test_x.py::test_name`).

## Stack

- macOS, **Python 3.12** géré par **uv** (je veux me faire la main avec).
- Dépendances actuelles : `httpx`, `feedparser`, `pyyaml`.
- Prévu : SQLite (lib standard `sqlite3`) pour la mémoire, API LLM pour scoring et résumé, GitHub Actions (cron) pour l'automatisation, sortie par mail (SMTP) ou webhook Discord.

## Architecture (src layout, créé avec `uv init --package`)

Le rôle de chaque emplacement. L'état d'avancement n'est **pas** ici, il est dans « Où on en est ».

```
src/tech_radar_agent/
├── __init__.py      # main() : orchestre le pipeline
├── models.py        # Article : la donnée qui circule dans tout le pipeline
├── collectors/      # une source = un module ; chacun produit des Article
└── storage/         # tout ce qui touche à SQLite
config/interests.yaml  # profil d'intérêts + liste des sources
data/                  # base SQLite locale ; le dossier est suivi via .gitkeep, les *.db* sont ignorés
```

Flux prévu : `collectors/*` → `Article` → `storage/` (SQLite) → scoring LLM → résumé → digest.

## Plan global : 4 soirées (~2-3 h chacune)

Chaque soirée doit se terminer avec quelque chose qui tourne réellement.

### Soirée 1 — Squelette + collecte
Objectif : `uv run tech-radar-agent` remplit une base SQLite avec 50 à 100 articles bruts.
1. ✅ Setup du projet avec uv, arborescence, `.gitignore`, README, premier push.
2. ✅ **Le modèle `Article`** : la donnée qui circule dans tout le pipeline, avec la clé de dédup `normalized_url`.
3. Le stockage SQLite (table `articles`, insertion sans doublons).
4. Le premier collector : Hacker News (API Firebase officielle).
5. Les collectors RSS (feedparser) et GitHub.
6. Le point d'entrée qui orchestre tout (une source en panne ne doit pas bloquer les autres) + le contenu de `interests.yaml`.

### Soirée 2 — La boucle agentique (scoring + résumé)
- Prompt de scoring : mon profil + l'article → score de pertinence 0-10 + justification courte.
- Prompt de résumé : 2-3 phrases, *pourquoi c'est pertinent pour moi*.
- Boucle : pour chaque article non traité → score → si score > seuil → résumé → sauvegarde.
- Gestion des erreurs API et rate limiting basique.
- Fin : je peux requêter en SQL « les 5 meilleurs du jour ».

### Soirée 3 — Mémoire, dédup, livraison
- Dédup entre sources (URL normalisée / hash, voire similarité de titre).
- Statuts pour ne jamais renvoyer un article déjà envoyé.
- Génération d'un digest (Markdown/HTML), envoi par mail ou webhook Discord.
- Automatisation quotidienne avec GitHub Actions (`uv sync` dans le runner).
- Fin : je reçois mon premier digest automatique.

### Soirée 4 — Feedback et adaptation (la vraie touche « agent »)
- Feedback 👍/👎 sur les articles reçus (CLI, petite page ou réaction au mail).
- Réinjection du feedback dans le scoring (few-shot avec mes préférences passées, ou critères stockés qui évoluent).
- Bonus : détection de « sujets chauds » (un thème qui revient dans la semaine → proposition de deep-dive).

## 👉 Où on en est

_Dernière session : 2026-09-28._

**Étape en cours : Soirée 1, étape 3 — stockage SQLite.** (Étape 2 terminée et mergée dans `dev`.)

- `models.py` contient la dataclass `Article` (servira de **modèle de style** pour les prochaines classes) et la fonction `normalize_url` + la propriété `normalized_url` (clé de dédup). Vérifiée sur 5 cas (tracking `utm_*`/`fbclid`, casse du domaine, `/` final, `#fragment`, ordre des paramètres, `?v=` YouTube conservé) : à transformer en tests pytest plus tard.
- Non géré volontairement : `www.` vs sans, `http` vs `https`. À revoir si de vrais doublons passent.

**Question reportée à la Soirée 2 (boucle de scoring) :**
- `score` et `summary` seront stockés en base dans tous les cas (colonnes de la table `articles`, à créer dès l'étape 3). Reste à décider s'ils sont aussi des champs de la classe `Article` (`None` par défaut) ou seulement écrits par `storage/` via un `UPDATE`. Penchant initial pour les champs dans `Article`, puis hésitation. `Article` reste inchangé d'ici là.

**Étape 3 codée (par Claude, à ma demande)**, branche `feature/sqlite-storage` : `storage/database.py` expose `connect(db_path)` (crée `data/` + la table) et `save_articles(conn, articles) -> int` (nombre réellement insérés). Vérifié : doublons ignorés, dates et `extra` bien relus. Reste : commit + MR vers `dev`, puis étape 4 (collector Hacker News).


## Décisions

Choix d'architecture validés, avec leur raison. Une ligne par décision.

- `data/` (base SQLite générée, ignorée par git) : suivi via `.gitkeep` **et** recréé par le module `storage/` s'il manque, en garde-fou. À coder à l'étape 3.
- `Article` est une `dataclass` (pas Pydantic) : lib standard, suffisant pour l'instant.
- `Article` décrit **ce que la collecte ramène**, avant tout traitement LLM. Champs obligatoires : `source`, `title`, `url`. Optionnels (`None`) : `author`, `content` (`None` = post sans texte), `published_at` (toutes les sources n'ont pas de date). Automatique : `fetched_at` (UTC, via `default_factory`).
- Dédup par **URL normalisée en clair** (pas de hash : plus simple à déboguer ; pas d'UUID : aléatoire, ne détecte pas les doublons). `url` reste l'URL originale (lien du digest) ; la clé normalisée est une **propriété calculée** de `Article` (jamais désynchronisée). En base : id technique `INTEGER PRIMARY KEY` + colonne clé `UNIQUE`.
- Infos propres à une source (points HN, étoiles GitHub…) dans `extra: dict[str, Any]`, pour ne pas polluer le modèle commun.
- Répartition du code : je code moi-même la partie « agent » (scoring, résumé, boucle, feedback). La plomberie (stockage SQLite…) peut être écrite par Claude quand je le demande ; je la relis.
- Schéma SQLite : dates en `TEXT` ISO 8601 (lisible, triable), `extra` en `TEXT` JSON, `score INTEGER` (0-10) et `summary TEXT` à `NULL` tant que le LLM n'est pas passé. Insertion via `INSERT OR IGNORE` sur `normalized_url`. Base par défaut : `data/tech_radar.db` (chemin relatif au dossier de lancement).
- Workflow git : branches `feature/<nom-kebab>` via `git flow feature start`, poussées puis mergées dans `dev` **par MR GitHub** (pas de `git flow feature finish`, qui merge en local).

## Pistes déjà évoquées (non décidées, à rediscuter le moment venu)
- Colonne de statut (envoyé / pas envoyé) : pas encore dans le schéma. À ajouter à la Soirée 3 (`ALTER TABLE ... ADD COLUMN` suffit en SQLite).
- GitHub n'a pas d'API « trending » officielle : la Search API (repos récents triés par étoiles) est plus robuste que du scraping HTML.
- Tronquer le contenu des articles pour limiter le coût en tokens au scoring.
- Paralléliser les appels à l'API Hacker News (une requête par item).
- arXiv est une source très bruyante : prévoir une limite par flux.
- Modèle LLM : Qwen ou un autre (local ou via API ?). À trancher à la Soirée 2.
- Persistance de la base en CI : chaque run GitHub Actions part d'une machine neuve, donc le `.db` de la veille (la mémoire de l'agent) disparaît. Options possibles : cache Actions, artifact, commit de la base, stockage externe. À trancher à la Soirée 3.

## Rituel de fin de session

À la fin de chaque session :
1. Mettre à jour « Où on en est » (étape terminée, étape suivante, questions ouvertes).
2. Ajouter les choix validés dans « Décisions » et retirer des « Pistes » ce qui a été tranché.
3. Me rappeler de cocher la case correspondante dans la roadmap du README et de committer.
