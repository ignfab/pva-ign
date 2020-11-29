#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import requests
import configparser
import xml.etree.ElementTree as ET
import json
from pick import pick # nécessaire sous windows pour pick : pip install windows-curses
from pathlib import Path
import tqdm
import time
#from xml.dom import minidom
from shapely.geometry import box, Polygon

# Définition de la zone d'intérêt sous la forme d'une boundingbox
min_lon=3.2558998675537105
min_lat=47.36254089577267
max_lon=3.301390132446289
max_lat=47.37163871192848
bbox = box(min_lon,min_lat,max_lon,max_lat)

# Récupération uniquement des PVA intersectant la zone d'intérêt
# Avec la valeur False, les missions sont récupérées dans leur intégralité
intersects_only=True

# Récupération de la configuration
config = configparser.ConfigParser()
config.read('properties.ini')

def make_bbox_polygon(): # Pour inclusion dans les requêtes
	b = [min_lat, min_lon, min_lat, max_lon, max_lat, max_lon, max_lat, min_lon, min_lat, min_lon]
	b = [str(f) for f in b]
	return ','.join([ '+'.join([ s for s in b[2*i:2*(i+1)] ]) for i in range(len(b)//2) ])

def get_missions_count(p): # Récupération du nombre de missions sur la zone
	r = requests.get(config['WFS']['CountUrl'].replace('#BBOX',p))
	root = ET.fromstring(r.text)
	return root.attrib['numberOfFeatures']

def get_missions(p): # Récupération du détail des missions sur la zone
	missions_details = []
	r = requests.get(config['WFS']['MissionsUrl'].replace('#BBOX',p))
	d = json.loads(r.text)
	for row in d['features']:
		if row['properties']['jp2']:
			missions_details.append([ row['properties']['pv_date'], row['properties']['kml_layer_id']])
	return missions_details

def show_menu(m): # L'utilisateur sélectionne une mission dans la liste
        title = 'Choisir une mission pour en récupérer les PVA : '
        options = [i[1] +'(' + i[0].split('-')[0] + ')' for i in m]
        option, index = pick(options, title)
        return index

def intersects(poly_coords): # True si le polygone correspondant a la PVA intersecte la zone d'intérêt
	p = poly_coords.split(" ")
	pt = [ tuple([float(j) for j in i.split(',')]) for i in p]
	pg = Polygon(pt)
	return bbox.intersects(pg)

def kml_walk(kml_id): # Parcours de l'arbre des KMLs
        leaves = [kml_id+'.kml']
        jp2s_ids = []
        while leaves:
                l,j = get_leaves_and_jp2s(leaves)
                jp2s_ids += j
                leaves=l
        return jp2s_ids

def get_leaves_and_jp2s(leaves_list): # Parcours d'un niveau de l'arbre
	leaves, jp2s = ([] for i in range(2))
	for l in leaves_list:
		context = l.rpartition('/')[0]+'/' if ('/' in l) else ''
		r = requests.get(config['KML']['UrlStub'] + l, headers={'referer': config['KML']['Referer']})
		# Décommenter l'import de minidom et les lignes suivantes pour 
		# télécharger les kmls intermédiaires pour mieux comprendre ou débuguer
		#file = open(l.replace('/','_')+'.xml','w')
		#xmlstr = minidom.parseString(r.text).toprettyxml(indent="   ")
		#file.write(xmlstr)
		#file.close()
		root = ET.fromstring(r.text)
		xleaves = root.findall(".//{http://www.opengis.net/kml/2.2}href")
		leaves += [context + i.text for i in xleaves]
		for p in root.iter('{http://www.opengis.net/kml/2.2}Placemark'):
			poly = p.find('{http://www.opengis.net/kml/2.2}Polygon/{http://www.opengis.net/kml/2.2}outerBoundaryIs/{http://www.opengis.net/kml/2.2}LinearRing/{http://www.opengis.net/kml/2.2}coordinates')
			if not intersects_only or intersects(poly.text):
				xjp2 = p.find("{http://www.opengis.net/kml/2.2}ExtendedData/{http://www.opengis.net/kml/2.2}Data[{http://www.opengis.net/kml/2.2}displayName='JP2']/{http://www.opengis.net/kml/2.2}value")
				jp2s.append(xjp2.text)
	return leaves,jp2s

def check_and_make_dirs(mission_id): # Création du répertoire de téléchargement
	Path(os.path.join("downloads",mission_id)).mkdir(parents=True, exist_ok=True)

def download(jp2s,mission_id): # Téléchargement des clichés
	check_and_make_dirs(mission_id)
	for j in tqdm.tqdm(jp2s):
		url = config['KML']['DlStub'] + mission_id + '/' + j + '.jp2'
		r = requests.get(url, headers={'referer': config['KML']['Referer']})
		with open('downloads/'+mission_id+'/'+j+'.jp2' , 'wb') as f:
			f.write(r.content)
		time.sleep(1) # soyons sympa avec le service de téléchargement des PVA 

def main():
	p = make_bbox_polygon()
	c = get_missions_count(p)
	#print(str(c) + " missions trouvées sur la zone d'intérêt.")
	if(int(c)>100):
		print("Plus de 100 missions trouvées. Merci de restreindre la taille de la zone d'intérêt.")
		sys.exit(0)
	m = get_missions(p)
	i = show_menu(m)
	print("Chargement de la liste des clichés à télécharger")
	jp2s = kml_walk(m[i][1])
	print(str(len(jp2s)) + " clichés à charger pour la mission " + str(m[i][1]))
	download(jp2s,m[i][1])

if __name__ == "__main__":
    main()
