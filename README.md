# NosTrip — YouTube → TikTok automatique (n8n)

Un workflow **n8n** qui prend une vidéo YouTube, la **découpe en parties de même durée et au même format
vertical** (1080×1920, « PARTIE 1/N », « PARTIE 2/N »…, sous-titres en option), puis **publie chaque partie
sur TikTok** l'une après l'autre.

```
 n8n                                                  worker (Python, Docker)
┌──────────────────────────────────────────┐        ┌───────────────────────────────────────┐
│ Formulaire  ─┐                           │  POST  │ /split                                 │
│ (ou RSS de   ├─► Paramètres ─► Découper ─┼───────►│  yt-dlp → Whisper → ffmpeg 9:16        │
│  la chaîne) ─┘                    │      │        │                                        │
│          ┌──── Pour chaque partie ◄┘     │  POST  │ /tiktok/publish                        │
│          │     └─► Publier sur TikTok ───┼───────►│  Content Posting API (Direct Post)     │
│          └──────── Pause (x min) ◄───┘   │        │                                        │
└──────────────────────────────────────────┘        └───────────────────────────────────────┘
```

Pourquoi un worker à côté de n8n ? Le découpage vidéo (ffmpeg, Whisper) ne tourne pas dans n8n, et
TikTok utilise un paramètre OAuth `client_key` non standard que le module OAuth2 générique de n8n ne sait
pas envoyer. Le worker gère donc la connexion TikTok et le rafraîchissement automatique des jetons.

## 1. Créer l'app TikTok (une seule fois)

1. Sur [developers.tiktok.com](https://developers.tiktok.com/), créez une app et ajoutez les produits
   **Login Kit** et **Content Posting API** (option *Direct Post* activée), avec les scopes
   `user.info.basic` et `video.publish`.
2. Déclarez l'URL de redirection `https://<votre-domaine>/tiktok/callback` (le worker, port 8000).
3. Récupérez le **Client key** et le **Client secret**.

> ⚠️ **Tant que l'app n'a pas passé l'audit TikTok, toutes les vidéos publiées sont privées (`SELF_ONLY`)**
> et le compte TikTok utilisé doit être en mode privé. Pour publier en public, soumettez l'app à l'audit
> depuis le portail développeur.

## 2. Lancer n8n + le worker

```bash
cp .env.example .env      # renseigner WORKER_TOKEN, TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REDIRECT_URI
docker compose up -d --build
```

- n8n : http://localhost:5678
- worker : http://localhost:8000 (doc de l'API : http://localhost:8000/docs)

Le worker doit être joignable par TikTok à l'adresse de `TIKTOK_REDIRECT_URI` pour l'étape suivante
(reverse proxy HTTPS, ou un tunnel type Cloudflare Tunnel / ngrok pendant les tests).

## 3. Connecter le compte TikTok (une seule fois)

Ouvrez `https://<votre-domaine>/tiktok/login`, autorisez l'app : la page « Compte TikTok connecté ✅ »
s'affiche. Les jetons sont stockés dans le volume du worker et renouvelés automatiquement (valables 1 an
sans nouvelle connexion).

## 4. Importer et lancer le workflow

1. Dans n8n : **Workflows → Import from file** → `n8n/youtube-to-tiktok.json`.
2. Activez le workflow, ouvrez l'URL du nœud **Formulaire** et remplissez :

| Champ | Effet |
|---|---|
| URL YouTube | la vidéo à découper |
| Durée maximale d'une partie (s) | ex. `60` : une vidéo de 4 min 10 donne 5 parties identiques de 50 s |
| Confidentialité TikTok | `SELF_ONLY` obligatoire tant que l'app n'est pas auditée |
| Sous-titres | sous-titres incrustés mot à mot (transcription Whisper) |
| Mise en page | `blur` : vidéo entière sur fond flouté · `crop` : recadrage plein écran |
| Pause entre deux publications | 10 min par défaut, pour ne pas dépasser les limites TikTok |

Les parties sont publiées **dans l'ordre**, avec en légende « *Titre de la vidéo* – Partie X/N ».

**Mode 100 % automatique :** activez le nœud **Nouvelle vidéo de la chaîne** (désactivé par défaut) et
remplacez `REMPLACER_PAR_ID_CHAINE` par l'ID de votre chaîne YouTube : chaque nouvelle vidéo publiée sur
la chaîne est découpée puis postée sur TikTok sans intervention.

## Utilisation en ligne de commande (sans n8n)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Parties égales de 60 s max (mode par défaut)
yt2tiktok "https://www.youtube.com/watch?v=..." --part-seconds 60

# Ou : les 5 meilleurs moments choisis par Claude (ANTHROPIC_API_KEY requis)
yt2tiktok "https://youtu.be/..." --mode highlights --selector llm -n 5 --min 20 --max 60
```

Les fichiers sont écrits dans `output/<id_video>/` : `clip_XX.mp4`, `clip_XX.txt` (légende), `clips.json`.

## API du worker

Toutes les routes sauf `/health`, `/tiktok/login` et `/tiktok/callback` exigent l'en-tête `X-Worker-Token`.

| Route | Rôle |
|---|---|
| `POST /split` | `{url, part_seconds, subtitles, layout, part_label, mode…}` → liste des parties (`file`, `caption`, `index`, `total`…) |
| `POST /tiktok/publish` | `{file, title, privacy_level}` → envoie la vidéo (par morceaux si > 64 Mo) et attend la fin du traitement TikTok |
| `GET /tiktok/status` | compte connecté et options de confidentialité autorisées |
| `GET /files/{video_id}/{nom}` | télécharger une partie pour vérification |

## Code

| Fichier | Rôle |
|---|---|
| `src/yt2tiktok/download.py` | téléchargement YouTube (yt-dlp, ≤ 1080p) |
| `src/yt2tiktok/transcribe.py` | transcription mot à mot (faster-whisper), mise en cache |
| `src/yt2tiktok/highlights.py` | `equal_split` (parties égales, coupures recalées entre deux phrases) et sélection des moments forts |
| `src/yt2tiktok/subtitles.py` | sous-titres ASS « style TikTok » + bandeau « PARTIE x/N » |
| `src/yt2tiktok/render.py` | ffmpeg : découpe, format 9:16, incrustation |
| `src/yt2tiktok/tiktok.py` | OAuth TikTok, envoi par morceaux, suivi de publication |
| `src/yt2tiktok/server.py` | API HTTP appelée par n8n |
| `n8n/youtube-to-tiktok.json` | le workflow n8n |

## Tests

```bash
pytest
```

## Limites à connaître

- **App TikTok non auditée** : publications forcément privées (voir plus haut).
- **Quotas TikTok** : 6 requêtes/min par compte et un nombre de publications par jour limité ; d'où la
  pause entre deux parties. Pour une longue vidéo (beaucoup de parties), augmentez la pause.
- **Durée** : TikTok refuse les vidéos plus longues que la limite du compte (`max_video_post_duration_sec`,
  visible via `GET /tiktok/status`).
- Ne publiez que des vidéos dont vous détenez les droits.
