# Partie 1 — Premiers pas

Ce qu'est le programme, comment l'installer et le lancer, les données de démonstration dont proviennent toutes les captures d'écran, les fichiers qu'il lit, comment connecter un agent IA, et où se trouvent les choses dans le code et sur le disque.

## 1.1 Ce qu'est ARPES viewer

ARPES viewer est un programme Python/PyQt5 pour les données de photoémission
résolue en angle. Il parcourt les mesures d'un temps de faisceau, ouvre
chacune dans sa propre fenêtre, convertit en impulsion, coupe, ajuste et
traite, compare aux calculs de structure de bandes, et met les résultats en
page comme une figure de publication. Chaque étape est aussi du Python simple
qu'un script ou un agent IA peut exécuter.

Il est gratuit pour un **usage non commercial** (recherche académique et
enseignement), sous la licence PolyForm Noncommercial 1.0.0. Si vous l'utilisez
pour un article, merci de le citer : Ding Pei, *ARPES viewer*, Zenodo,
<https://doi.org/10.5281/zenodo.23771647>.

Ce n'est pas un programme d'acquisition, et il ne modifie pas vos fichiers de
données : chaque résultat est un nouveau jeu de données dans la liste ou un
nouveau fichier que vous choisissez.

## 1.2 Installation et lancement

Il faut Python 3.9 ou plus récent, et cinq paquets :

```bash
pip install PyQt5 pyqtgraph numpy h5py scipy
```

Puis, depuis le dossier `ARPES_viewer` :

```bash
python ARPES_viewer.py
```

**Sous Windows, double-cliquez `ARPES viewer.pyw`** dans le dossier du
programme, et non `ARPES_viewer.py` : Windows lance un `.pyw` avec
`pythonw`, sans fenêtre de console noire -- la fermer par erreur fermait le
programme. (Un `.py` double-cliqué malgré tout cache désormais la console
ouverte pour lui seul ; lancé depuis une invite de commande, il la garde.)
Les messages du programme vont dans `~/.arpes_viewer/launcher.log` ; s'il
s'arrête sur une erreur, une fenêtre montre la fin de ce journal.

**Les erreurs sont gardées dans un fichier texte.** Ce que la console
afficherait en cas d'erreur -- l'erreur et sa trace -- est enregistré de
lui-même dans **`error_logs/errors_<date>_<heure>.txt` du dossier du
programme** (dans `~/.arpes_viewer/error_logs` si ce dossier n'est pas
accessible en écriture), seulement quand une erreur survient. Une fenêtre le
signale et le programme **continue** au lieu de se fermer. Avec un rapport
de bug, **téléversez ce fichier** (dans GitHub Issues : glissez-le dans la
zone de texte) **ou collez son texte** -- le pied du panneau principal offre
**Copy the newest error log** et **Open the error logs**.

**Les opérations longues montrent une barre de progression.** Tout ce qui
peut prendre du temps sur de grosses données ou un ordinateur lent — lire
une carte entière, conversion en k, correction FS, coupes arbitraires,
opérations sur les données, assemblage, enregistrement, détection de
crêtes, ajustements, et dans Calculated bands la lecture d'un calcul, les
bandes sur un plan et la surface de Fermi 3D — affiche après 0,4 s une
fenêtre de progression : une barre qui avance, les secondes écoulées, et
Cancel quand l'étape peut s'arrêter. Le programme travaille ; il n'est pas
figé.

**Sur Mac, pas besoin du Terminal :** double-cliquez **`ARPES viewer.app`**
dans le dossier du programme (glissez-la dans le Dock pour l'y garder). Elle
trouve le Python qui a les paquets ci-dessus -- le même que `python3` dans le
Terminal, environnements conda compris -- et le retient. Si aucun ne les a,
une fenêtre donne la commande `pip install` (déjà copiée dans le
presse-papiers : collez-la une fois dans le Terminal), ou permet de choisir
un Python.

- Si macOS dit que l'app *provient d'un développeur non identifié* (le
  programme a été téléchargé en ZIP) : **Réglages Système → Confidentialité
  et sécurité → Ouvrir quand même** (macOS plus ancien : clic droit sur
  l'app → **Ouvrir**). Seulement la première fois.
- Une copie de l'app placée hors du dossier du programme (dans Applications,
  par exemple) demande une fois où il se trouve.
- Si le programme s'arrête sur une erreur, la fenêtre montre la fin de
  `~/.arpes_viewer/launcher.log` ; joignez ce fichier à un rapport de bogue.

Les fichiers lus sont listés au [§1.4](#14-installations-et-formats-de-fichiers).

## 1.3 Essayer avec des données de démonstration

```bash
python devtools/demo_data.py            # écrit ./demo_data/
```

Ce script écrit des données synthétiques qui s'ouvrent exactement comme des
données mesurées :

- le jeu d'origine — une carte de surface de Fermi, une paire de coupes en
  polarisation LH et LV, un balayage en énergie de photon, une EDC résolue en
  spin, un petit balayage spatial et une carte où est imprimée la grille du
  détecteur — issu d'une structure de bandes simple (une poche d'électrons
  hexagonale et une bande de trous en Γ, des poches de trous en K) ;
- **un cristal lamellaire en trois dimensions** (`demo_bulk_bands.nxs`) : des
  cartes aux énergies de photon du plan Γ (59,3 eV) et du haut de la zone
  (77 eV), des coupes selon Γ-M (LH et LV) et Γ-K, et un balayage en énergie
  de photon selon Γ-M couvrant une période entière de k_z. Deux de ses bandes
  se croisent le long d'une ligne qui traverse la zone, dont l'énergie varie
  avec k_z ;
- **un calcul de ce cristal**, tel qu'un groupe de théorie l'enverrait : un
  hamiltonien Wannier90 (`demo_calc_hr.dat` avec `demo_calc.win`) et les
  mêmes bandes sur une grille (`demo_calc.bxsf`). C'est le cristal avant
  renormalisation — ses bandes 1/0,8 fois plus larges et 50 meV plus haut —
  ce que l'ajustement aux données retrouve ([§6.5](#65-bandes-calculées)) ;
- deux structures cristallines en fichiers CIF (`demo_crystal.cif`, un cristal
  hexagonal lamellaire 1T ; `demo_tetragonal_crystal.cif`, un cristal de type
  ZrSiS) et un spectre EDS (`demo_eds.nxs`).

Toutes ont une coupure de Fermi, la résolution de l'analyseur et un bruit de
Poisson.

Pour refaire toutes les captures d'écran de ce guide après avoir modifié une
fenêtre :

```bash
python devtools/guide_screenshots.py    # écrit docs/images/*.png
```

Les deux figures d'exemple du
[§6.7](#67-exemple-complet--deux-figures-dans-le-composeur) sont reconstruites,
à partir des données de démonstration et avec les fenêtres du programme, par

```bash
python devtools/figure_tests.py docs/images [dossier des fichiers .afig]
```

## 1.4 Installations et formats de fichiers

Le lecteur d'un fichier est détecté automatiquement ([§2.2](#22-charger-des-données)).

| Installation / ligne | Fichiers | Données |
|---|---|---|
| SOLEIL **ANTARES** | NeXus `*.nxs` | coupes, cartes en déflecteur, balayages en énergie de photon (PhD), balayages spatiaux |
| SOLEIL **CASSIOPEE** | texte Scienta `*.txt` | spectres seuls ; dossiers numérotés assemblés en carte ou en balayage en énergie de photon |
| CASSIOPEE **station spin** (MBS A-1) | `*.krx`, `*.txt` | coupes, cartes en déflecteur, EDC résolues en spin |
| ALS **MAESTRO** | `*.h5`, `*.hdf5` | coupes, cartes, balayages en énergie de photon et spatiaux |
| ALBA **LOREA** | `*.nxs` | coupes, cartes |
| Diamond **I05** (HR-ARPES) et **I05-1** (nano-ARPES) | `*.nxs` | coupes, cartes, balayages en énergie de photon, balayages spatiaux |
| MAX IV **Bloch** (et tout fichier Scienta SES qu'aucun autre lecteur ne prend) | `*.ibw`, `*.zip`, `*.txt` | coupes, cartes en déflecteur, balayages en énergie de photon et du manipulateur |
| Elettra **APE**, BESSY **One Cube / One Square**, SOLARIS **URANOS** | `*.ibw`, `*.zip`, `*.txt` | tels que SES les écrit |
| ASTRID2 **SGM4** | `*.h5`, `*.hdf5` | coupes, cartes, balayages au couteau |
| Ce programme | son propre `*.nxs` | tout ce qu'il a enregistré, plusieurs jeux de données par fichier |

Les jeux de données s'enregistrent dans le format `.nxs` du programme (qu'il
rouvre) ou en texte Igor Pro (`.itx`). La façon dont les fichiers de chaque
installation sont lus, et les hypothèses qu'imposent leurs formats, sont dans
[la référence des lecteurs](../../../arpes_viewer/loader/README.md), qui
explique aussi comment ajouter une ligne de lumière.

**Une carte dont le balayage a été arrêté avant la fin** -- à la main, par
une perte du faisceau, un plantage du contrôle-commande -- s'ouvre jusqu'où
elle est allée, quelle que soit l'installation. Les pas jamais mesurés
(aucun coup, ou aucune valeur de l'axe balayé) et un dernier pas nettement
plus faible que ceux d'avant (moins de la moitié : arrêté en cours
d'acquisition) sont laissés de côté ; la barre d'état et le panneau
Information (`incomplete.note`) disent combien et pourquoi. Les pas faibles
au milieu d'un balayage viennent de l'échantillon et ne sont jamais touchés.

## 1.5 Types de données

| Type | Axes | Ce que c'est |
|---|---|---|
| `cut` | angle (ou k) × E | un spectre |
| `map` | angle × angle × E | un balayage au déflecteur ou en angle polaire |
| `k_map` | kx × ky × E | une carte convertie en impulsion |
| `kz_map` | hν × angle × E | un balayage en énergie de photon |
| `kz_map_k` | k_z × k∥ × E | ce balayage converti en impulsion |
| `spem_4d`, `spem_1d` | x (× y) × angle × E | balayages en espace réel |
| `edc`, `mdc`, `spin_edc` | E (ou k) × canaux | courbes, avec canaux σ facultatifs |

### Noms des données traitées

Chaque résultat est une nouvelle ligne nommée d'après sa source, avec une
étiquette entre crochets ajoutée par étape, la plus ancienne d'abord :
`Map80eV [norm] [E-E_F] [k]` est Map80eV normalisée, rapportée à E_F, puis
convertie en impulsion. Les étiquettes, dans l'ordre habituel d'un
traitement (`arpes_viewer/tools/runtime/naming.py`) :

| Étiquette | Faite par | Ce qui a été fait |
|---|---|---|
| `[combined …]` | Combine…, somme de balayages répétés | jeux joints, empilés ou sommés |
| `[degrid] / [grid]` | Remove detector grid… | grille du détecteur retirée / la grille elle-même |
| `[det]` | Correction du détecteur | trapèze et régions corrigés |
| `[crop]` | Truncate…, `L.crop` | réduit à une plage de ses axes |
| `[bin]` | Compress…, `L.bin` | points sommés par blocs |
| `[despike]` | Smooth… (pics) | pics retirés |
| `[norm]` | Self-normalise…, `L.normalise` | chaque spectre ou plan divisé par son total ou son maximum |
| `[bg]` | Background subtraction… | fond soustrait |
| `[E-E_F]` | Ajustement du niveau de Fermi (décalage), `L.shift_energy` | énergie rapportée au niveau de Fermi |
| `[dFD]` | Ajustement du niveau de Fermi (division) | divisé par la fonction de Fermi–Dirac |
| `[FS corr]` | Straighten bands (FS correction) | bandes redressées le long de la fente |
| `[sm]` | Smooth… | lissé |
| `[symm]` | Symmetrise… | symétrisé |
| `[k]` | Conversion en k (coupe / carte) | converti en impulsion |
| `[kz]` | Conversion en kz | balayage en hν converti en k_z |
| `[d2] / [grad] / [cur]` | Second derivative… / Minimum gradient… / Curvature… | dérivée seconde, gradient minimum, courbure |
| `[ridge]` | Détection des crêtes | positions des bandes |
| `[arb cut]` | Coupe arbitraire dans une carte | coupe le long d'une ligne choisie |
| `[slice …]` | Save slice to list (visualiseur) | plan ou coupe sorti d'un visualiseur |
| `[EDC …] / [MDC …]` | EDC / MDC d'un visualiseur vers la liste | courbe extraite, avec sa position |
| `[shifted] / [sigma]` | visualiseur de courbes | courbe décalée / son incertitude de Poisson |
| `[fit]` | ajustement de courbe | résultat d'ajustement |
| `[LD] [CD] [diff] [asym] [ratio] [sum]` | Cut arithmetic… | deux coupes combinées |
| `[calc]` | Bandes calculées | un calcul, pas une mesure |

**Tri.** Clic droit sur la liste → **Sort by data type** regroupe les lignes
par leur **dernière** étiquette -- la dernière opération faite -- dans
l'ordre de ce tableau : les mesures telles que lues d'abord, puis `[crop]`,
`[norm]`, `[E-E_F]`, `[k]`… ; une étiquette absente du tableau vient
ensuite. Dans un groupe, les lignes sont classées par type (coupe,
carte…), puis par nom, les nombres comparés comme des nombres. **Sort by
name** ignore l'ordre des étiquettes. Les noms des versions précédentes
sont lus de la même façon : `_s_nor` vaut `[norm]`, `_tk` `[crop]`,
`_comb` `[bin]`, `_sm`, `_d2`, `_cur` `[sm]`, `[d2]`, `[cur]`, et `[E-Ef]`
`[E-E_F]`. Une ligne renommée à la main ne garde sa place que si elle
garde ses étiquettes. Un agent IA suit la même règle, aussi pour les noms
qu'il choisit ([§7.6](#76-les-règles-de-travail-de-lagent)) ; `L.naming()` lui
donne le tableau.

## 1.6 Configurer un agent IA

Un agent IA peut piloter le programme pour vous ([partie 7](#partie-7--agents-ia)). La voie
habituelle ne demande rien à installer :

1. Ayez une application IA capable de lire et d'écrire des fichiers sur votre
   ordinateur : l'application de bureau Claude, Claude Code ou un agent
   semblable.
2. Dans ARPES viewer, cliquez sur **AI assistant...** en haut du panneau
   d'outils, choisissez le dossier des données et celui des résultats, et
   cliquez sur **Copy the prompt and start** ([§7.3](#73-démarrer-depuis-le-panneau-ai-assistant)).
3. Collez le prompt dans l'application IA et autorisez-la à lire le dossier
   des données et à lire et écrire celui des résultats.

Une application qui utilise des outils MCP doit d'abord ajouter une fois le
serveur MCP du programme ; le prompt indique comment ([§7.5](#75-autres-façons-de-démarrer)). Avant de
commencer, lisez ce qui quitte votre ordinateur ([§7.1](#71-principe-et-ce-qui-quitte-votre-ordinateur)).

## 1.7 Organisation du code

| Dossier | Contenu |
|---|---|
| `arpes_viewer/loader/` | les lecteurs : un par installation (`beamlines/`), les formats communs (`formats/`), le `.nxs` du programme, la sauvegarde automatique de la session |
| `arpes_viewer/tools/` | les calculs, sans fenêtre : spectres (front de Fermi, ajustements, niveaux de cœur, spin), impulsion (conversions k et kz), traitement (lissage, dérivées, arithmétique de coupes ...), cristal (réseaux, zones de Brillouin, bandes calculées), sorties (figures, export) |
| `arpes_viewer/ui/` | les fenêtres : panneau principal (`launcher/`), visualisation (`viewers/`), outils (`panels/`), parties communes (`common/`), dont les opérations de l'agent `L` (`common/live.py`) |
| `arpes_viewer/agent/` | le serveur MCP, le pont agent (agent bridge) et `API.md`, la référence de l'agent générée à partir du programme |
| `agentic/` | exemples et recettes pour agents et scripts |
| `devtools/` | les données de démonstration, les captures d'écran, les tests de figures, la construction de ce guide |
| `test/` | les tests (`python -m pytest`) |

Comme les calculs de `tools/` n'ont besoin d'aucune fenêtre, un script peut les
appeler directement, par exemple
`arpes_viewer.tools.momentum.kspace.convert_map(...)`. Chaque dossier a un
README avec les formules et les tests ; l'organisation et les conventions sont
dans [les notes pour développeurs](../../DEVELOPER.md).

## 1.8 Où le programme range ses fichiers

| Où | Quoi |
|---|---|
| `~/.arpes_viewer/` | les réglages mémorisés d'une session à l'autre, le journal du lanceur, le jeton du pont agent pendant qu'il tourne, les derniers dossiers de l'AI assistant |
| `~/.arpes_viewer/sessions/` | les copies sauvegardées automatiquement des données calculées, un dossier par session, et `operations.log` ([§8.1](#81-sauvegarde-automatique-mémoire-et-récupération)) |
| `error_logs/` dans le dossier du programme (sinon `~/.arpes_viewer/error_logs/`) | un fichier texte par session où une erreur s'est produite ([§8.3](#83-journaux-derreurs-et-rapports-de-bogue)) |
| `<résultats>/_agent/` | les fichiers de commandes d'un agent, leur sortie et leurs images, lorsqu'il est démarré depuis l'AI assistant ([§7.3](#73-démarrer-depuis-le-panneau-ai-assistant)) |

Vos dossiers de données sont seulement lus ; le programme n'y écrit que si vous
y enregistrez vous-même un fichier.
