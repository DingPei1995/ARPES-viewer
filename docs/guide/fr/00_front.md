# ARPES viewer — Guide de l'utilisateur

*[English version](../../USER_GUIDE_en.md) · [中文版](../../USER_GUIDE_zh.md)*

*Dernière mise à jour : 10 novembre 2026 — pour ARPES viewer v1.3.3*

La version et sa date figurent dans la barre de titre de la fenêtre principale
et sur sa dernière ligne. Rapports de bogues, questions et dernière version :
<https://github.com/DingPei1995/ARPES-viewer> (indiquez la version quand vous
signalez un bogue).

Le guide suit le programme tel qu'il apparaît à l'écran :

- la **partie 1** pour démarrer : installation, données de démonstration,
  fichiers lus, configuration d'un agent IA, organisation du code ;
- la **partie 2**, le panneau principal : la liste des jeux de données et ce
  qui l'entoure ;
- la **partie 3**, les fenêtres de visualisation : coupes, cartes, cartes kz,
  cartes k, courbes, spin et balayages résolus spatialement ;
- les **parties 4, 5 et 6**, les trois onglets du panneau d'outils
  (**Basic**, **Advanced**, **Figure**) ; la partie 6 se termine par un
  exemple allant du chargement des données à la figure finie ;
- la **partie 7**, les agents IA : comment ils pilotent le programme, comment
  en démarrer et en suivre un, et un exemple de la configuration à la figure ;
- la **partie 8**, l'entretien : sauvegarde automatique et récupération,
  enregistrement du travail, journaux d'erreurs, versions et dépannage.

Toutes les captures d'écran viennent du programme en marche, sur les données
synthétiques de `devtools/demo_data.py`, pour que vous puissiez suivre sans
temps de faisceau ([§1.3](#13-essayer-avec-des-données-de-démonstration)).
**Ce ne sont pas des données expérimentales réelles.** Le contexte technique
de chaque étape (formules, tests, choix de conception) est dans les
références à côté du code : [lecture des données](../../../arpes_viewer/loader/README.md),
[les fenêtres](../../../arpes_viewer/ui/README.md),
[l'analyse](../../../arpes_viewer/tools/README.md), et le
[CHANGELOG](../../../CHANGELOG.md).

<!-- contents -->
