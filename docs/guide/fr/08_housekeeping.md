# Partie 8 — Entretien

Sauvegarde automatique et récupération, enregistrement du travail, journaux d'erreurs, versions, et que faire quand quelque chose ne va pas.

## 8.1 Sauvegarde automatique, mémoire et récupération

- **Sauvegarde automatique.** Chaque jeu de données calculé (une carte k, une
  coupe traitée, un résultat d'ajustement…) est écrit, sans compression, dans
  le dossier de la session sous `~/.arpes_viewer/sessions/` dès qu'il existe.
  Les balayages en espace réel ne le sont pas (ce sont les mesures
  elles-mêmes, et elles sont volumineuses).
- **Une fermeture normale supprime les copies automatiques.** Quand vous
  fermez la fenêtre principale et confirmez (tout ce que vous voulez garder
  est enregistré, ou *Close anyway*), les fenêtres ouvertes sont fermées et le
  dossier de la session est supprimé immédiatement. La copie d'un jeu de
  données disparaît aussi dès que vous l'enregistrez dans un fichier à vous.
- **Récupération après un plantage.** Ce n'est que si le programme ne s'est
  pas fermé normalement (plantage, arrêt forcé) que le dossier de la session
  est conservé : au démarrage suivant, ses jeux de données vous sont
  proposés, et il est supprimé au bout de trois jours.
- **Journal des opérations.** `~/.arpes_viewer/sessions/operations.log`, une
  ligne par écriture / enregistrement / suppression — pour retrouver ce qui
  était où.
- **Cadre Memory** (en bas du panneau d'outils). La mémoire du programme et celle du système, le nombre de
  fenêtres et de fichiers HDF5 ouverts, et la quantité de données calculées
  conservées. **Free RAM** abandonne les copies en cache des données
  calculées (elles sont relues depuis leur fichier de sauvegarde au besoin) ;
  **Close all** ferme toutes les fenêtres puis libère la mémoire.
- **Autosaves** (dans le cadre Memory) ouvre le dossier des
  sessions dans l'explorateur de fichiers, pour supprimer à la main les
  anciennes copies de travail. Le dossier de la session en cours (nommé dans
  la barre d'état) est utilisé : n'y touchez pas.
- **Les opérations longues** (lecture d'une grande carte, conversion,
  dégrillage, assemblage d'un dossier) tournent hors du fil de l'interface,
  avec une barre de progression et un bouton Cancel qui fonctionne.
- **La fermeture** avec des données calculées non enregistrées demande
  d'abord confirmation, en nommant les jeux de données : **Save to a
  file...**, **Close anyway** (les copies automatiques sont supprimées) ou
  **Cancel** (rien ne se passe).

## 8.2 Enregistrer et rouvrir son travail

- **Jeux de données.** Sélectionnez des lignes → boîte Datasets → **Save** :
  un fichier `.nxs` au format du programme (plusieurs jeux de données par
  fichier, avec leurs métadonnées et leur historique de traitement), que
  **Load data...** rouvre ; ou du texte Igor Pro (`.itx`). Un panneau de
  visualisation exporte ce qu'il montre ([§3.8](#38-exporter-un-panneau-et-enregistrer-des-données)).
- **Figures.** Dans le composeur, **Save** écrit un fichier `.afig` qui se
  rouvre pour être modifié, avec les données de chaque panneau à côté
  (« data for <nom> »), de sorte qu'il s'ouvre même là où les fichiers
  d'origine ne sont pas. Ne joignez pas ce dossier à ce que vous partagez.
  **Export** écrit du PNG, PDF, SVG ou TIFF.
- **Le journal d'expérience** et le **journal de session** gardent la trace de
  ce qui a été mesuré et fait ([§2.3](#23-le-journal-dexpérience)).
- Rien n'est écrasé sans demander : enregistrer sur un fichier existant pose
  d'abord la question.

## 8.3 Journaux d'erreurs et rapports de bogue

Quand quelque chose se passe mal, le programme **continue de tourner** et
enregistre l'erreur et sa trace dans
**`error_logs/errors_<date>_<heure>.txt` dans le dossier du programme** (dans
`~/.arpes_viewer/error_logs/` si ce dossier n'est pas accessible en
écriture), un fichier par session où une erreur s'est produite. Un message
l'indique.

Pour signaler un bogue, ouvrez une issue sur
<https://github.com/DingPei1995/ARPES-viewer/issues> avec :

- le journal d'erreurs : **téléversez le fichier** (glissez-le dans la zone de
  texte) **ou collez son texte**. La dernière ligne du panneau principal a
  **Copy the newest error log** et **Open the error logs** ;
- la version, lue dans la barre de titre ;
- ce que vous faisiez juste avant et, si possible, le type de fichier (ligne,
  coupe ou carte).

Si le programme ne démarre pas du tout, le journal du lanceur
`~/.arpes_viewer/launcher.log` en donne la raison.

## 8.4 Versions et mises à jour

La barre de titre et la dernière ligne du panneau principal montrent la
version et sa date (`ARPES viewer v1.3.4 (updated 2026-11-13)`). Ce qui a
changé à chaque version, et pourquoi, est dans le
[CHANGELOG](../../../CHANGELOG.md).

Pour mettre à jour une installation pip :

```bash
pip install --upgrade arpes-viewer
```

Pour la dernière version non publiée, `pip install
git+https://github.com/DingPei1995/ARPES-viewer` ; une copie téléchargée se met
à jour en la téléchargeant de nouveau. Les données et figures enregistrées
par une version antérieure s'ouvrent dans les suivantes.

## 8.5 Conseils et dépannage

- **Un bouton d'outil grisé** — survolez-le : l'infobulle dit pourquoi (par
  ex. l'ajustement MDC exige une coupe déjà en Å⁻¹, l'arithmétique de coupes
  deux coupes). Sélectionnez les bonnes lignes dans la liste et il s'allume.
- **Un outil manque au menu Functions d'une fenêtre** — il est dans le
  panneau d'outils (voir *Où se trouvent les choses maintenant* au
  [§2.1](#21-la-fenêtre-principale-en-un-coup-dœil)) ; regardez les trois onglets (Basic,
  Advanced, Figure).
- **Une fenêtre est plus haute que l'écran** — elle s'ouvre au plus à la
  hauteur de l'écran et son contenu défile ; les boutons Apply / Close
  restent en bas. Toutes les fenêtres se redimensionnent.
- **Aucune conversion en k n'est proposée** — le premier axe de la carte
  n'est pas un angle (énergie de photon, température…). Vérifiez *First axis
  of a map is* dans la fenêtre de chargement.
- **Conversion en k d'une coupe en E − E_F** — le décalage en énergie est
  rempli pour vous à partir de l'ajustement de Fermi ; si vous avez décalé
  l'axe autrement, saisissez dans *Energy offset* l'énergie cinétique de E_F
  (énergie de photon − travail de sortie).
- **Un fichier est mal lu** — choisissez explicitement le lecteur dans la
  fenêtre de chargement, et voyez *Assumptions worth knowing about* dans la
  [référence technique de la lecture](../../../arpes_viewer/loader/README.md#assumptions-worth-knowing-about)
  (ordre des axes dans les fichiers SOLEIL).
- **Le curseur est lent sur une grande carte** — une carte lue à la demande
  dans son fichier se recoupe en environ 0,1 s par fenêtre, si bien que les
  autres fenêtres attendent que la souris s'arrête. Une fois la carte lue en
  mémoire, elle suit en direct.
- **Saisie des nombres** — toutes les cases numériques prennent un point
  décimal (`0.05`), quelle que soit la langue du système ; la virgule n'est
  pas acceptée.
- **La machine utilise la mémoire d'échange** — surveillez la barre Memory
  (ambre au-delà d'un tiers de la RAM, rouge au-delà de la moitié) ; utilisez
  **Free RAM** ou **Close all**.
