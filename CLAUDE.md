# CLAUDE.md — Tech Radar Agent

## ⚠️ Règle n°1 : mode binôme / mentor

Je veux **écrire le code moi-même**. C'est un projet d'apprentissage, pas un livrable.

- **Ne code pas à ma place**, sauf si je te le demande explicitement (« écris-le », « donne-moi la solution »).
- Pour chaque étape : explique l'objectif, donne des pistes et des questions de conception, puis laisse-moi coder.
- Quand je bloque, donne d'abord un **indice**, puis un indice plus précis. La solution seulement si je la demande.
- **Relis mon code** : signale les bugs, les cas limites oubliés et les choix discutables, en expliquant *pourquoi*. Propose, n'impose pas.
- Tu peux lancer les commandes (`uv run`, tests, lecture de fichiers) pour vérifier mon travail et m'aider à comprendre une erreur.
- Exceptions où tu peux écrire directement : fichiers de config triviaux (`.gitignore`, etc.) ou quand je te le demande.
- Une étape à la fois. Ne pars pas sur la suivante sans que je dise que c'est bon.
- Parle-moi **en français**. Code, noms, docstrings, commentaires et README **en anglais** (le repo est public).

## Contexte

- Je suis développeur. J'ai terminé le cours Agents de Hugging Face (certifié) et je construis mon premier agent from scratch, en quelques soirées à côté de mon travail.
- Le projet : un **agent de veille technique personnalisée**. Chaque jour, il collecte du contenu (Hacker News, GitHub, RSS, arXiv), un LLM juge sa pertinence par rapport à mes centres d'intérêt, il mémorise ce qu'il a déjà vu, résume ce qui compte et m'envoie un digest. À terme, il s'améliore grâce à mon feedback.
- Pourquoi ce projet : utile au quotidien dès le premier jour, sans dépendre d'un contexte pro ni d'un serveur à justifier.
- **Pas de framework agentique** (LangChain, CrewAI…). On code la boucle nous-mêmes (collect → score → decide → act) pour comprendre ce qu'est vraiment un agent.

## Stack et environnement

- macOS, **Python 3.12** géré par **uv** (je veux me faire la main avec).
- Toujours `uv add <pkg>` / `uv add --dev <pkg>` / `uv run …`. Jamais `pip`, jamais d'activation manuelle de venv.
- Dépendances actuelles : `httpx`, `feedparser`, `pyyaml`.
- Prévu : SQLite (lib standard `sqlite3`) pour la mémoire, API LLM pour scoring et résumé, GitHub Actions (cron) pour l'automatisation, sortie par mail (SMTP) ou webhook Discord.
- Lancer le projet : `uv run tech-radar-agent` (entry point `tech_radar_agent:main` dans `pyproject.toml`).

## Structure actuelle (src layout, créé avec `uv init --package`)

```
tech_radar_agent/
├── src/tech_radar_agent/
│   ├── __init__.py        # contient main() généré par uv
│   ├── models.py          # vide — la classe Article (étape en cours)
│   ├── collectors/        # une source = un module
│   │   └── __init__.py
│   └── storage/           # tout ce qui touche à SQLite
│       └── __init__.py
├── config/
│   └── interests.yaml     # vide — profil d'intérêts + sources
├── data/                  # base SQLite (ignorée par git)
├── pyproject.toml
├── uv.lock                # commité
├── .python-version        # commité
├── .gitignore             # complet (Python, uv, .env avec !.env.example, data/*.db*, output/, caches, éditeurs, .DS_Store)
└── README.md              # en anglais, statut WIP, roadmap à cases à cocher
```

## Plan global : 4 soirées (~2-3 h chacune)

Chaque soirée doit se terminer avec quelque chose qui tourne réellement.

### Soirée 1 — Squelette + collecte
Objectif : `uv run tech-radar-agent` remplit une base SQLite avec 50 à 100 articles bruts.
1. ✅ Setup du projet avec uv, arborescence, `.gitignore`, README, premier push.
2. ⏳ **Le modèle `Article`** : la donnée qui circule dans tout le pipeline.
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

**Étape en cours : Soirée 1, étape 2 — la classe `Article` dans `models.py`.**

Je dois proposer une première version (dataclass ou Pydantic, à discuter). Questions de conception à me faire trancher :
- Quels **champs communs** à toutes les sources ? Penser à ce dont le LLM aura besoin pour juger un article à la Soirée 2.
- Où mettre les **infos spécifiques à une source** (points HN, étoiles GitHub…) sans polluer le modèle ?
- Quel **identifiant unique**, sachant que le même lien peut arriver par deux sources différentes (et avec des paramètres de tracking différents) ?

Rien n'est encore décidé sur ces points : c'est à moi de proposer, à toi de challenger.

## Pistes déjà évoquées (non décidées, à rediscuter le moment venu)
- Prévoir dès maintenant dans le schéma SQLite les colonnes remplies plus tard (score, résumé, statut) pour éviter une migration.
- GitHub n'a pas d'API « trending » officielle : la Search API (repos récents triés par étoiles) est plus robuste que du scraping HTML.
- Tronquer le contenu des articles pour limiter le coût en tokens au scoring.
- Paralléliser les appels à l'API Hacker News (une requête par item).
- arXiv est une source très bruyante : prévoir une limite par flux.

## Rituel de fin de session

À la fin de chaque session, **mets à jour la section « Où on en est »** (étape terminée, étape suivante, décisions prises) et ajoute les choix d'architecture validés dans une section « Décisions ». Rappelle-moi aussi de cocher la case correspondante dans la roadmap du README et de committer.