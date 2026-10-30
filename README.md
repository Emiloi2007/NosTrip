# NosTrip — yt2tiktok

Automatisation qui transforme **une vidéo YouTube en plusieurs clips TikTok** :
verticaux (1080×1920), sous-titrés mot à mot, avec titre, description et hashtags prêts à publier.

```
URL YouTube ──► yt-dlp ──► faster-whisper ──► sélection des moments forts ──► ffmpeg ──► clip_01.mp4 …
               (téléchargement) (transcription        (Claude ou heuristique)    (9:16 + sous-titres)
                                 mot à mot)
```

## Installation

Prérequis : Python ≥ 3.10 et [ffmpeg](https://ffmpeg.org/) (avec libass, c'est le cas des builds standards).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # puis renseigner ANTHROPIC_API_KEY
```

## Utilisation

```bash
# 5 clips de 20 à 60 s choisis par Claude, fond flouté, sous-titres
export ANTHROPIC_API_KEY=sk-ant-...
yt2tiktok "https://www.youtube.com/watch?v=XXXXXXXXXXX"

# Sans IA, recadrage plein écran, 3 clips de 15 à 45 s, vidéo en français
yt2tiktok "https://youtu.be/XXXXXXXXXXX" --selector heuristic --layout crop -n 3 --min 15 --max 45 --language fr

# Fonctionne aussi avec un fichier local
yt2tiktok ma_video.mp4 -o sorties/
```

| Option | Défaut | Rôle |
|---|---|---|
| `-n, --max-clips` | 5 | nombre maximum de clips |
| `--min` / `--max` | 20 / 60 | durée d'un clip en secondes |
| `--selector` | `llm` | `llm` : Claude choisit les passages et rédige titre/description/hashtags ; `heuristic` : sans IA ni clé API |
| `--layout` | `blur` | `blur` : vidéo entière sur fond flouté ; `crop` : recadrage centré plein écran |
| `--no-subtitles` | — | désactive l'incrustation des sous-titres |
| `--whisper-model` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3` (plus gros = plus précis mais plus lent) |
| `--language` | auto | code langue de la vidéo (`fr`, `en`…) |

## Résultat

```
output/<id_video>/
├── clip_01.mp4    # vidéo verticale prête pour TikTok
├── clip_01.txt    # légende : titre + description + hashtags
├── clip_01.ass    # sous-titres (modifiables puis re-rendus)
├── …
└── clips.json     # récapitulatif : horodatages, titres, scores
```

Le téléchargement et la transcription sont mis en cache dans `output/_work/` : relancer avec
d'autres options (layout, durées, sélecteur) ne retélécharge ni ne retranscrit la vidéo.

## Fonctionnement

- **`download.py`** — télécharge la vidéo en MP4 ≤ 1080p via yt-dlp.
- **`transcribe.py`** — transcription faster-whisper avec horodatage de chaque mot.
- **`highlights.py`** — sélection des passages :
  - `llm` : la transcription horodatée est envoyée à Claude (`claude-opus-5-5`, sortie JSON structurée),
    qui choisit les passages avec la meilleure accroche ; les bornes sont ensuite recalées sur les phrases
    et contraintes à la durée demandée.
  - `heuristic` : fenêtres de phrases consécutives notées sur le débit de parole et les questions/exclamations.
- **`subtitles.py`** — sous-titres ASS « style TikTok » : 3 mots max à l'écran, mot prononcé surligné en jaune.
- **`render.py`** — ffmpeg : découpe, passage en 9:16, incrustation des sous-titres, H.264/AAC.

## Tests

```bash
pytest
```

Les tests de rendu génèrent une mire avec ffmpeg et vérifient que la sortie fait bien 1080×1920.

## Pistes d'évolution

- Publication automatique via l'API TikTok Content Posting (nécessite une app TikTok validée).
- Recadrage intelligent qui suit le visage du locuteur (OpenCV / MediaPipe).
- Traitement par lot d'une playlist ou d'une chaîne, planifié (cron / GitHub Actions).

> ⚠️ Ne republiez que des vidéos dont vous détenez les droits ou pour lesquelles vous avez l'autorisation.
