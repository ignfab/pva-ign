# pva-ign

Script basique de téléchargement des PVAs disponibles sur [remonterletemps.ign.fr](https://remonterletemps.ign.fr)

La zone de recherche est à définir au début du script `main.py`.
L'option `intersects_only`, également présente en début de fichier, permet de ne télécharger que les PVAs intersectant la zone de recherche. Avec la valeur `False`, cette option provoque le téléchargement des missions dans leur intégralité.

## Usage

```
pip3 install -r requirements.txt
python3 main.py
```

Une interface en ligne de commande (utilisant [pick](https://github.com/wong2/pick)) permet de choisir la mission de son choix et de la télécharger. Sous Windows, télécharger en plus : `pip3 install windows-curses`

## TODO

- [ ] Gérer les erreurs éventuelles
- [ ] Améliorer/Revoir l'interface
