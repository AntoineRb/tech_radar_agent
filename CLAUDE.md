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

- Variables d'environnement (LLM, secrets) : `cp .env.example .env` puis `uv run --env-file .env tech-radar-agent`. Détail : `docs/configuration.md`.
- Tester le LLM configuré : `uv run --env-file .env python -m tech_radar_agent.llm` (répond « pong ») ou `... --debug "ma question"` (durée + tokens). Codes : 0 OK, 1 erreur LLM, 2 réglages invalides.
- Lancer l'agent : `uv run tech-radar-agent` depuis la racine du repo (entry point `tech_radar_agent:main` dans `pyproject.toml`, défini dans `src/tech_radar_agent/__init__.py`). Lit `config/interests.yaml`, écrit dans `data/tech_radar.db`. Codes de sortie : 0 OK (même si certaines sources échouent), 1 toutes les sources en échec, 2 config invalide.
- Voir la base : `sqlite3 data/tech_radar.db "SELECT source, count(*) FROM articles GROUP BY source"`.
- Installer / synchroniser : `uv sync`.
- Ajouter une dépendance : `uv add <pkg>` (ou `uv add --dev <pkg>` pour un outil de dev).
- Toujours passer par `uv`. Jamais `pip`, jamais d'activation manuelle de venv.
- Tests : `uv run pytest` (tout, ~0,1 s), un fichier : `uv run pytest tests/test_models.py`, un test : `uv run pytest tests/test_models.py::TestArticle::test_defaults`, par nom : `uv run pytest -k xxe`. Guide : `docs/development/testing.md`. Pas de linter.

## 🧪 Tests (règle)

- **Chaque feature ajoutée ou modifiée arrive avec ses tests**, dans la même MR. Chaque bug corrigé arrive avec un test qui échoue sans le correctif.
- `uv run pytest` doit passer avant chaque MR.
- Jamais de réseau ni de vraie base dans les tests : fixture `fake_http` (faux serveur HTTP, `httpx.MockTransport`) et `tmp_path`. La fixture autouse `no_network` fait échouer toute vraie requête.
- La sécurité se teste avec des entrées hostiles, pas seulement le cas nominal.
- Quand c'est moi qui code (partie agent), Claude me guide aussi sur les tests (quoi tester, cas limites) sans les écrire à ma place.

## Stack

- macOS, **Python 3.12** géré par **uv** (je veux me faire la main avec).
- Dépendances actuelles : `httpx`, `feedparser`, `pyyaml`. Dev : `pytest`.
- Prévu : SQLite (lib standard `sqlite3`) pour la mémoire, API LLM pour scoring et résumé, GitHub Actions (cron) pour l'automatisation, sortie par mail (SMTP) ou webhook Discord.

## 🔒 Sécurité (règles non négociables)

Détail et justification : `docs/security.md` et ADR 0007. Toute nouvelle dépendance, source ou étape LLM doit respecter ces règles **avant** d'être codée.

**Dépendances : de confiance uniquement**
- Lib standard d'abord. Une dépendance tierce doit être justifiée.
- Avant chaque `uv add`, Claude vérifie et me présente : dépôt officiel, mainteneurs, date de la dernière version, nombre de téléchargements, CVE connues, nom exact sur PyPI (attention au typosquatting). J'approuve avant l'ajout.
- Uniquement depuis PyPI via `uv`, et `uv.lock` (hashes sha256) toujours commité.
- Audit avant chaque MR qui touche aux dépendances : `uv export --format requirements-txt --no-emit-project --all-groups > "$TMPDIR/req.txt" && uvx pip-audit --strict -r "$TMPDIR/req.txt"` (`--all-groups` inclut les dépendances de dev).
- GitHub Actions : uniquement des actions officielles ou très reconnues, épinglées par SHA de commit.

**Services et URLs : vérifiés**
- Uniquement des API officielles et documentées, et des flux RSS publiés par le site officiel de l'éditeur. Chaque source est documentée avec son lien de doc officiel dans `docs/architecture/collectors.md`.
- HTTPS uniquement pour les sources, avec un délai d'attente (déjà dans `http_client()`) et une taille de réponse bornée.
- Les URL collectées sont des données non fiables : on accepte seulement `http`/`https` (rejet de `javascript:`, `data:`, `file:`…). On ne les ouvre jamais automatiquement. Si ça change un jour, il faut une protection SSRF (bloquer les IP privées et locales).
- Secrets (clé API LLM, SMTP, webhook) uniquement dans les variables d'environnement (`.env` ignoré par git en local) ou les secrets GitHub. Jamais dans le code, la config, `.env.example` ou les logs.
- Endpoint LLM : HTTPS, **seule exception** : `http` vers `localhost`/`127.0.0.1`/`::1` pour un modèle local (Ollama). Contrôlé par `is_allowed_llm_url()`.
- YAML : toujours `yaml.safe_load`, jamais `yaml.load`.

**Injection de prompt : tout contenu collecté est une donnée, jamais une instruction**
- Au parsing (collectors) : conversion en texte brut, suppression des caractères invisibles ou de contrôle (zero-width, bidi, etc.), longueur tronquée, URL validée.
- Au prompt (Soirée 2) : le contenu est isolé dans un bloc clairement délimité. Le prompt système dit explicitement que ce bloc est une donnée à évaluer et que ses consignes éventuelles doivent être ignorées.
- Sortie LLM structurée (JSON) et validée : score entier borné 0-10, résumé de longueur bornée. Si la sortie est invalide, l'article est rejeté, pas deviné.
- Le LLM de scoring et de résumé n'a **aucun outil ni aucune action**. Il ne fait que produire du texte.
- La sortie du LLM est elle aussi non fiable : elle est échappée dans le digest HTML ou Markdown (pas de lien ni de HTML injecté).
- Une détection heuristique (« ignore previous instructions »…) peut signaler les cas suspects dans les logs, mais on ne s'y fie jamais seule.

## Architecture (src layout, créé avec `uv init --package`)

Le rôle de chaque emplacement. L'état d'avancement n'est **pas** ici, il est dans « Où on en est ».

```
src/tech_radar_agent/
├── __init__.py      # main() : orchestre le pipeline
├── models.py        # Article : la donnée qui circule dans tout le pipeline
├── sanitize.py      # nettoyage et validation des données collectées (non fiables)
├── llm/             # settings.py (plomberie, Claude) ; client, scoring, résumé (moi)
├── collectors/      # une source = une classe Collector ; registre type -> classe dans __init__.py
└── storage/         # tout ce qui touche à SQLite
config/interests.yaml  # profil d'intérêts + liste des sources
data/                  # base SQLite locale ; le dossier est suivi via .gitkeep, les *.db* sont ignorés
docs/                  # doc technique en anglais : architecture/, decisions/ (ADR), development/
tests/                 # pytest, même arborescence que src/ ; conftest.py = fixtures partagées
```

Tenir `docs/` à jour à chaque étape terminée : page d'architecture concernée + un ADR par nouvelle décision (`docs/decisions/NNNN-titre.md`, et ligne dans `docs/decisions/README.md`).

Flux prévu : `collectors/*` → `Article` → `storage/` (SQLite) → scoring LLM → résumé → digest.

## Plan global : 4 soirées (~2-3 h chacune)

Chaque soirée doit se terminer avec quelque chose qui tourne réellement.

### Soirée 1 — Squelette + collecte
Objectif : `uv run tech-radar-agent` remplit une base SQLite avec 50 à 100 articles bruts.
1. ✅ Setup du projet avec uv, arborescence, `.gitignore`, README, premier push.
2. ✅ **Le modèle `Article`** : la donnée qui circule dans tout le pipeline, avec la clé de dédup `normalized_url`.
3. ✅ Le stockage SQLite (table `articles`, insertion sans doublons).
4. ✅ Le premier collector : Hacker News (API Firebase officielle).
5. ✅ Les collectors RSS (feedparser) et GitHub.
6. ✅ Le point d'entrée qui orchestre tout (une source en panne ne doit pas bloquer les autres) + le contenu de `interests.yaml`.

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

_Dernière session : 2026-09-30._

**Étape en cours : Soirée 2 — boucle agentique (c'est moi qui code, Claude guide).**

- ✅ Choix du LLM (question 1) : API au format OpenAI chat completions, appelée directement avec `httpx`, pour un modèle local (Ollama + Qwen) ou distant. Réglé par `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (ADR 0008).
- ✅ Plomberie codée par Claude, branche `feature/llm-settings` : `llm/settings.py` (`load_llm_settings()`, `LlmSettings` avec `is_local`, clé cachée du `repr`), exception http localhost, `.env.example`, 25 tests. Reste : commit + MR. `main()` ne lit pas encore ces réglages : ce sera à moi de les brancher avec la boucle.
- Modèle local : `qwen3.6:latest` (36B MoE, Q4, 23 Go ; Mac M5 32 Go), à mettre dans `.env` (`LLM_MODEL=qwen3.6:latest`). Mesures : 1er appel ~20 s (chargement) ; à chaud ~18 s par défaut (phase de réflexion, ~800 tokens) contre **~0,3 s avec `"reasoning_effort": "none"`** (~1 h contre ~1 min pour 200 articles). Ce champ n'est peut-être pas accepté par un fournisseur distant.
- Décisions de conception du client (validées) : une **classe** `LlmClient`, **pas de singleton** (une instance créée dans `main()` et passée en paramètre, comme `conn`) ; **deux couches** : client générique (`chat(messages, **options) -> str`, HTTP + erreurs → `LlmError`) d'un côté, scoring/résumé (prompts, validation JSON) de l'autre, qui reçoivent le client. Options par tâche (temperature, max_tokens…) = arguments optionnels de `chat()`.
- 🧑‍💻 **Exercice en cours (moi)** : implémenter `src/tech_radar_agent/llm/client.py` (squelette avec TODO créé par Claude) et les 11 tests de `tests/llm/test_client.py` (noms + consignes, marqués `@TODO` = skip ; retirer le marqueur en écrivant chaque test). ✅ Tranché : `reasoning_effort` **et** le délai d'attente viennent des settings (ajoutés par Claude) : `LLM_REASONING_EFFORT` (optionnel, absent = champ non envoyé ; `none` dans `.env.example`) et `LLM_REQUEST_TIMEOUT` (défaut 30 s, nombre > 0). Le client lit `settings.reasoning_effort` / `settings.request_timeout`. Ma constante `REQUEST_TIMEOUT = 30` dans la classe devient inutile : à supprimer. 13 tests à écrire (2 ajoutés : reasoning_effort, timeout). ⚠️ Commentaires de `client.py` traduits en français à ma demande : **les repasser en anglais à la fin de l'exercice** (repo public).
- Avancement de l'exercice : `__init__` ✅ et `chat()`/`_build_body()` ✅ (écrits par moi, corrigés et commentés par Claude à ma demande : `["message"]`, `import re`, durée via `perf_counter`, `TypeError` pour les options réservées, `finish_reason == "length"` et `<think>` non fermé → `LlmError`, options à `None` non envoyées, détail HTTP passé par `clean_text`). `close`/`__enter__`/`__exit__` ✅ (écrits par moi, justes, commentés par Claude). Tests du client ✅ (45 tests écrits par Claude à ma demande, fixture `FakeLlm`) ; suite complète : 259 tests. Essai réel ✅ : qwen3.6 répond via le client (« pong » en 0,3 s ; une phrase en 1,2 s). Commande de vérification `python -m tech_radar_agent.llm` ajoutée par Claude (+ 5 tests, `tests/llm/test_cli.py`) ; suite : 264 tests. Reste avant la MR : repasser les commentaires de `client.py` en anglais.
- ⏳ **À traiter au point 5 (erreurs et limites de requêtes)** : `LlmError` ne distingue pas les erreurs **fatales** (401, 404, 400, serveur éteint → arrêter le lancement), **temporaires** (429, 503, délai dépassé → réessayer) et **propres à un article** (réponse vide ou mal formée → passer l'article). Piste : sous-classes ou attribut sur `LlmError`.
- Git à faire avant l'exercice : committer la plomberie sans les squelettes (`git add -A -- . ':!src/tech_radar_agent/llm/client.py' ':!tests/llm/test_client.py'`), MR + merge, puis `git flow feature start llm-client` (les squelettes non commités suivent).
- Prochaines questions, une à la fois : (2) forme des prompts et du JSON renvoyé ; (3) `score`/`summary` dans `Article` ou seulement en base ; (4) seuil et gestion du premier run (211 articles) ; (5) erreurs API et rate limiting.
- Pour tester en local : installer Ollama et récupérer un modèle Qwen (le tag exact sur la page du modèle Ollama).

**Tests en place et mergés (MR #8)** :

- 179 tests, ~0,1 s, sans réseau : `sanitize`, `models`, `storage`, `config` (dont validation du vrai `interests.yaml`), `main()` (faux collector enregistré dans `COLLECTOR_TYPES`), `collectors/` (base, registre, HN, RSS, GitHub).
- Seul changement de code « pour les tests » : `http_client(transport=None)`.
- 2 bugs trouvés et corrigés dans le collector RSS : une page HTML bien formée donnait 0 article en silence (maintenant `ValueError` « not an RSS or Atom feed ») ; une réponse vide plantait avec `AttributeError`.
- Audit `pip-audit` avec pytest : aucune vulnérabilité.

**Soirée 1 terminée et mergée (MR #7).** Rappel de l'étape 6 :
- `main()` : charge la config (`config.py`), construit tous les collectors (erreur de config → arrêt avant tout appel réseau, code 2), les lance un par un (source en panne → loggée et ignorée), sauvegarde par source, résumé final. Code 1 si toutes les sources échouent. Logger `httpx` passé en WARNING.
- `interests.yaml` : profil (`about`, `interests.high/medium/low`, `not_interested`) + 17 sources vérifiées le 2026-09-28 (HN, Lobsters, 2 recherches GitHub, 13 flux officiels : IA, Python, JS/TS, Apple, Nvidia, Microsoft/GitHub). Écartés : blog V8 (inactif depuis 2025), ancien Blogspot Python Insider (a déménagé).
- Premier vrai run : 215 articles, 211 nouveaux en ~7 s ; second run : 0 nouveau. Pannes testées : source HS, DNS inconnu, toutes les sources HS, nom en double, type inconnu, option mal orthographiée, config vide ou absente, tag YAML malveillant (refusé, rien d'exécuté).

**Prochaine étape : Soirée 2 — la boucle agentique (c'est moi qui code).** Premier point à trancher : le modèle LLM (local ou API, lequel), voir « Pistes ».

- `models.py` contient la dataclass `Article` (servira de **modèle de style** pour les prochaines classes) et la fonction `normalize_url` + la propriété `normalized_url` (clé de dédup), couverte par `tests/test_models.py`.
- Non géré volontairement : `www.` vs sans, `http` vs `https` (un test documente cette limite, à modifier si on la lève). À revoir si de vrais doublons passent.

**Question reportée à la Soirée 2 (boucle de scoring) :**
- `score` et `summary` seront stockés en base dans tous les cas (colonnes de la table `articles`, à créer dès l'étape 3). Reste à décider s'ils sont aussi des champs de la classe `Article` (`None` par défaut) ou seulement écrits par `storage/` via un `UPDATE`. Penchant initial pour les champs dans `Article`, puis hésitation. `Article` reste inchangé d'ici là.


## Décisions

Choix d'architecture validés, avec leur raison. Une ligne par décision.

- `data/` (base SQLite générée, ignorée par git) : suivi via `.gitkeep` **et** recréé par le module `storage/` s'il manque, en garde-fou. À coder à l'étape 3.
- `Article` est une `dataclass` (pas Pydantic) : lib standard, suffisant pour l'instant.
- `Article` décrit **ce que la collecte ramène**, avant tout traitement LLM. Champs obligatoires : `source`, `title`, `url`. Optionnels (`None`) : `author`, `content` (`None` = post sans texte), `published_at` (toutes les sources n'ont pas de date). Automatique : `fetched_at` (UTC, via `default_factory`).
- Dédup par **URL normalisée en clair** (pas de hash : plus simple à déboguer ; pas d'UUID : aléatoire, ne détecte pas les doublons). `url` reste l'URL originale (lien du digest) ; la clé normalisée est une **propriété calculée** de `Article` (jamais désynchronisée). En base : id technique `INTEGER PRIMARY KEY` + colonne clé `UNIQUE`.
- Infos propres à une source (points HN, étoiles GitHub…) dans `extra: dict[str, Any]`, pour ne pas polluer le modèle commun.
- Répartition du code : je code moi-même la partie « agent » (scoring, résumé, boucle, feedback). La plomberie (stockage SQLite…) peut être écrite par Claude quand je le demande ; je la relis.
- Schéma SQLite : dates en `TEXT` ISO 8601 (lisible, triable), `extra` en `TEXT` JSON, `score INTEGER` (0-10) et `summary TEXT` à `NULL` tant que le LLM n'est pas passé. Insertion via `INSERT OR IGNORE` sur `normalized_url`. Base par défaut : `data/tech_radar.db` (chemin relatif au dossier de lancement).
- Collectors génériques et pilotés par la config (l'agent pourra servir à autre chose que la veille tech) : classe abstraite `Collector` (`collect() -> list[Article]`), registre `COLLECTOR_TYPES`, `build_collector(dict)` passe les options au constructeur. `name` d'instance = `Article.source`. Source injoignable → exception ; item en échec → loggé et ignoré. Voir ADR 0006.
- Sécurité imposée par construction : `Article.__post_init__` nettoie `title`/`author`/`content` (NFKC, caractères cachés supprimés, troncature 300/100/3000) et rejette les URL non `http(s)` (`ValueError`, l'item est ignoré). Les collectors téléchargent uniquement via `fetch()`/`fetch_json()` (HTTPS, 5 Mo max), jamais `client.get`. `extra` n'est pas nettoyé : passer par `clean_text()` avant de le mettre dans un prompt.
- GitHub : Search API officielle (repos créés récemment, triés par étoiles) plutôt que du scraping de la page trending. RSS : une entrée de config par flux, chacune avec son `name` et sa `limit` (utile pour arXiv, très bruyant).
- Orchestration : config validée en entier avant tout appel réseau (fail fast) ; ensuite chaque source est isolée (`except Exception` uniquement à ce niveau) ; sauvegarde après chaque source. Sources lancées séquentiellement (~7 s pour 17, suffisant). Chemins relatifs au dossier de lancement.
- LLM : un seul client au format OpenAI chat completions (`POST {LLM_BASE_URL}/chat/completions`) via `httpx`, sans SDK. Local (Ollama) ou distant selon `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY`, pas de variable « mode » ni de `if local`. Réglages dépendant de l'environnement aussi en variables : `LLM_REASONING_EFFORT` (optionnel), `LLM_REQUEST_TIMEOUT` (défaut 30). Critère : une valeur qui change selon l'endroit où tourne l'agent va dans l'env, sinon c'est une constante du code. `.env` chargé par `uv run --env-file .env` (pas de python-dotenv). Voir ADR 0008.
- Répartition Soirée 2 : Claude fait la plomberie (réglages, sécurité, `.env`), je code le client LLM, le scoring, le résumé et la boucle.
- Tests : pytest (dev uniquement), aucune autre dépendance de test. Réseau simulé par `httpx.MockTransport` (fixture `fake_http`, qui garde les vrais réglages de `http_client()` et les vrais contrôles de `fetch()`), vrai réseau bloqué par la fixture autouse `no_network`. `main()` testé avec un faux type de collector enregistré dans `COLLECTOR_TYPES`.
- Workflow git : branches `feature/<nom-kebab>` via `git flow feature start`, poussées puis mergées dans `dev` **par MR GitHub** (pas de `git flow feature finish`, qui merge en local).

## Pistes déjà évoquées (non décidées, à rediscuter le moment venu)
- Colonne de statut (envoyé / pas envoyé) : pas encore dans le schéma. À ajouter à la Soirée 3 (`ALTER TABLE ... ADD COLUMN` suffit en SQLite).
- Couverture de code (`pytest-cov`) et linter (`ruff`) : utiles plus tard, chaque ajout passe par la validation des dépendances.
- CI : lancer `uv run pytest` sur chaque MR via GitHub Actions (à faire avec l'automatisation de la Soirée 3).
- Premier run : 211 articles d'un coup (les flux renvoient leur historique). Les runs suivants n'apportent que les nouveautés. À surveiller à la Soirée 2 pour le coût du scoring du premier run (limiter aux articles récents ?).
- Persistance de la base en CI : chaque run GitHub Actions part d'une machine neuve, donc le `.db` de la veille (la mémoire de l'agent) disparaît. Options possibles : cache Actions, artifact, commit de la base, stockage externe. À trancher à la Soirée 3.

## Rituel de fin de session

À la fin de chaque session :
1. Mettre à jour « Où on en est » (étape terminée, étape suivante, questions ouvertes).
2. Ajouter les choix validés dans « Décisions » et retirer des « Pistes » ce qui a été tranché. Mettre à jour `docs/` en conséquence.
3. Vérifier que `uv run pytest` passe et que les features du jour ont leurs tests.
4. Me rappeler de cocher la case correspondante dans la roadmap du README et de committer.
