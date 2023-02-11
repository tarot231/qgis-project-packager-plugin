# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Project Packager
                                 A QGIS plugin
 Gathers scattered data to make the project portable
                             -------------------
        begin                : 2021-10-28
        copyright            : (C) 2021 by Tarot Osuji
        email                : tarot@sdf.org
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
from qgis.PyQt.QtCore import QDir, QFile, QIODevice
from qgis.core import QgsSymbolLayerUtils, QgsLayoutItemPicture


# Get stock svg paths
stock_svgs = list(map(lambda x: QDir(x).canonicalPath(),
                        QgsSymbolLayerUtils.listSvgFiles()))


def get_symbol_layers_from_symbol(symbol):
    slyrs = []
    for slyr in symbol.symbolLayers():
        sub = slyr.subSymbol()
        if sub:
            slyrs.extend(get_symbol_layers_from_symbol(sub))
        slyrs.append(slyr)

    return slyrs


def get_path_from_symbol_layer(symbol_layer):
    try: return symbol_layer.path()
    except AttributeError: pass
    try: return symbol_layer.svgFilePath()
    except AttributeError: pass
    try: return symbol_layer.imageFilePath()
    except AttributeError: pass


def get_symbol_layer_map_from_symbol(symbol):
    slyr_map = {}
    slyrs = get_symbol_layers_from_symbol(symbol)
    for slyr in slyrs:
        # large embedded base64 encoded becomes ''
        path = get_path_from_symbol_layer(slyr)
        if path:
            # small embedded base64 encoded will remain
            path = QDir(path).canonicalPath()
        else:
            path = ''
        if os.path.exists(path) and not (path in stock_svgs):
            slyr_map[slyr] = path

    return slyr_map


def get_symbol_layer_map(project, context):
    slyr_map = {}
    for lyr in project.mapLayers().values():
        try:
            rend = lyr.renderer()
            syms = rend.symbols(context)
        except AttributeError:
            continue
        for sym in syms:
            slyr_map.update(get_symbol_layer_map_from_symbol(sym))

    for layout in project.layoutManager().printLayouts():
        model = layout.itemsModel()
        for row in range(model.rowCount()):
            item = model.itemFromIndex(model.index(row, 0))
            if isinstance(item, QgsLayoutItemPicture):
                path = item.picturePath()
                if path:
                    path = QDir(path).canonicalPath()
                else:
                    path = ''
                if os.path.exists(path) and not (path in stock_svgs):
                    slyr_map[item] = path
            else:
                try:
                    sym = item.symbol()
                except AttributeError:
                    continue
                slyr_map.update(get_symbol_layer_map_from_symbol(sym))

    return slyr_map


# https://github.com/qgis/QGIS/search?q=embedFile
def encode_to_base64path(filepath):
    fileSource = QFile(filepath)
    if not fileSource.open(QIODevice.ReadOnly):
        return
    try:
        blob = fileSource.readAll()
    finally:
        fileSource.close()
    encoded = blob.toBase64()
    path = 'base64:' + encoded.data().decode()

    return path


def set_path_to_symbol_layer(symbol_layer, path):
    try: symbol_layer.setPath(path); return
    except AttributeError: pass
    try: symbol_layer.setSvgFilePath(path); return
    except AttributeError: pass
    try: symbol_layer.setImageFilePath(path); return
    except AttributeError: pass


def embed_images_to_project(project, context):
    slyr_map = get_symbol_layer_map(project, context)
    for slyr, filepath in slyr_map.items():
        base64path = encode_to_base64path(filepath)
        if isinstance(slyr, QgsLayoutItemPicture):
            format = (QgsLayoutItemPicture.FormatSVG
                    if filepath.endswith('.svg') or filepath.endswith('.svgz')
                    else QgsLayoutItemPicture.FormatRaster) 
            slyr.setPicturePath(base64path, format)
        else:
            set_path_to_symbol_layer(slyr, base64path)
