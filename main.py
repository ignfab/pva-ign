#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import configparser
import xml.etree.ElementTree as ET
import json
from pick import pick
from pathlib import Path
import tqdm
import time
from shapely.geometry import box, Polygon

# Define retry behaviour for requests
retry_strategy = Retry(
    total=5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    backoff_factor=1
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http = requests.Session()
http.mount("https://", adapter)
http.mount("http://", adapter)

# URL stubs for kml and jp2 access
kml_stub = "https://wxs.ign.fr/2ne3yvigrf4y78kmd5o2gp9v/dematkml/DEMAT.PVA/"
jp2_stub = "https://wxs.ign.fr/2ne3yvigrf4y78kmd5o2gp9v/jp2/DEMAT.PVA/"
referer = "ignfab.ign.fr"

# Get parameters from configuration
config = configparser.ConfigParser()
config.read('properties.ini')
min_lon = config.getfloat('AREA OF INTEREST', 'minimum_longitude')
min_lat = config.getfloat('AREA OF INTEREST', 'minimum_latitude')
max_lon = config.getfloat('AREA OF INTEREST', 'maximum_longitude')
max_lat = config.getfloat('AREA OF INTEREST', 'maximum_latitude')
bbox = box(min_lon, min_lat, max_lon, max_lat)
intersects_only = config.getboolean(
    'AREA OF INTEREST', 'only_intersecting_aerial_shots')


def make_bbox_polygon():
    """Bouding box to polygon coordinates"""
    b = [min_lat, min_lon, min_lat, max_lon, max_lat,
         max_lon, max_lat, min_lon, min_lat, min_lon]
    b = [str(f) for f in b]
    return ','.join(['+'.join([s for s in b[2*i:2*(i+1)]]) for i in range(len(b)//2)])


def get_missions_count(p):
    """Get aerial survey count"""
    count_url = (
        "https://wxs.ign.fr/search/layers?"
        f"&cql_filter=demat_layer_id+=+'DEMAT.PVA$GEOPORTAIL:DEMAT;PHOTOS'+and+INTERSECTS(the_geom,POLYGON(({p})))"
        "&outputFormat=json"
        "&request=GetFeature"
        "&resultType=hits"
        "&typeName=ign:missions"
        "&version=1.1.0"
    )
    r = http.get(count_url)
    root = ET.fromstring(r.text)
    return root.attrib['numberOfFeatures']


def get_missions(p):
    """Get survey metadata"""
    missions_details = []
    missions_url = (
        "https://wxs.ign.fr/search/layers?"
        f"&cql_filter=demat_layer_id+=+'DEMAT.PVA$GEOPORTAIL:DEMAT;PHOTOS'+and+INTERSECTS(the_geom,POLYGON(({p})))"
        "&outputFormat=json"
        "&propertyName=jp2,kml_layer_id,pv_date,title"
        "&request=GetFeature"
        "&sortBy=pv_date,kml_layer_id"
        "&typeName=ign:missions"
        "&version=1.1.0"
    )
    r = http.get(missions_url)
    d = json.loads(r.text)
    for row in d['features']:
        if row['properties']['jp2']:
            missions_details.append(
                [row['properties']['pv_date'], row['properties']['kml_layer_id']])
    return missions_details


def show_menu(m):
    """Select survey"""
    title = 'Choose an aerial survey to download its aerial shots:'
    options = [i[1] + '(' + i[0].split('-')[0] + ')' for i in m]
    option, index = pick(options, title, indicator="=>")
    return index


def intersects(poly_coords):
    """True if aerial shot intersects bounding box"""
    p = poly_coords.split(" ")
    pt = [tuple([float(j) for j in i.split(',')]) for i in p]
    pg = Polygon(pt)
    return bbox.intersects(pg)


def kml_walk(kml_id):
    """Scan kml tree"""
    leaves = [kml_id+'.kml']
    jp2s_ids = []
    while leaves:
        l, j = get_leaves_and_jp2s(leaves)
        jp2s_ids += j
        leaves = l
    return jp2s_ids


def get_leaves_and_jp2s(leaves_list):
    """Scan kml leaves"""
    leaves, jp2s = ([] for i in range(2))
    for l in leaves_list:
        context = l.rpartition('/')[0]+'/' if ('/' in l) else ''
        r = http.get(kml_stub + l, headers={'referer': referer})
        root = ET.fromstring(r.text)
        xleaves = root.findall(".//{http://www.opengis.net/kml/2.2}href")
        leaves += [context + i.text for i in xleaves]
        for p in root.iter('{http://www.opengis.net/kml/2.2}Placemark'):
            poly = p.find(
                '{http://www.opengis.net/kml/2.2}Polygon/{http://www.opengis.net/kml/2.2}outerBoundaryIs/{http://www.opengis.net/kml/2.2}LinearRing/{http://www.opengis.net/kml/2.2}coordinates')
            if not intersects_only or intersects(poly.text):
                xjp2 = p.find(
                    "{http://www.opengis.net/kml/2.2}ExtendedData/{http://www.opengis.net/kml/2.2}Data[{http://www.opengis.net/kml/2.2}displayName='JP2']/{http://www.opengis.net/kml/2.2}value")
                jp2s.append(xjp2.text)
    return leaves, jp2s


def check_and_make_dirs(mission_id):
    """Create download directory"""
    Path(os.path.join("downloads", mission_id)).mkdir(
        parents=True, exist_ok=True)


def download(jp2s, mission_id):
    """Download aerial shots for a given survey"""
    check_and_make_dirs(mission_id)
    for j in tqdm.tqdm(jp2s):
        url = jp2_stub + mission_id + '/' + j + '.jp2'
        with http.get(url, headers={'referer': referer}, stream=True) as r:
            with open('downloads/'+mission_id+'/'+j+'.jp2', 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        time.sleep(1)  # let's be gentle with the download service


def main():
    p = make_bbox_polygon()
    c = get_missions_count(p)
    if (int(c) > 100):
        print("More than 100 survey found. Please reduce bounding box.")
        sys.exit(0)
    m = get_missions(p)
    i = show_menu(m)
    print("Parsing KML files to get aerial shots download URLs. This could take some time.")
    jp2s = kml_walk(m[i][1])
    print(str(len(jp2s)) +
          " aerial shots will be downloaded for IGNF survey " + str(m[i][1]))
    download(jp2s, m[i][1])

if __name__ == "__main__":
    main()
