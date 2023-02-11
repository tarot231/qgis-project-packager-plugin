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
import uuid
import sqlite3
from contextlib import closing
from osgeo import gdal
from qgis.PyQt.QtWidgets import qApp
from qgis.core import (Qgis, QgsMapLayerType, QgsDataProvider, QgsProviderRegistry,
        QgsVectorFileWriter, QgsFields,
        QgsRasterFileWriter, QgsRasterPipe, QgsRasterProjector, QgsRasterBlockFeedback,
        QgsRenderContext)
from .symbol import embed_images_to_project


class ToGPKG(object):
    def storeDataToGPKG(self):
        for lyr in list(self.src_map):
            if lyr.type() not in (QgsMapLayerType.VectorLayer, QgsMapLayerType.RasterLayer):
                del self.src_map[lyr]

        # Organize target names
        paths_set = list(set(self.src_map.values()))
        bases = []
        for path, layername, options in paths_set:
            if isinstance(options, str) and options.startswith('/'):
                bases.append(os.path.splitext(os.path.basename(options))[0])
            elif layername:
                bases.append(layername)
            else:
                bases.append(os.path.splitext(os.path.basename(path))[0])
        names = []
        if self.dialog.checkStoreProject.isChecked():
            names.append(self.pj.baseName())
        for name in bases:
            if name in names:
                suffix = 1
                while True:
                    newname = name + ('_%d' % suffix)
                    if not newname in names:
                        break
                    suffix += 1
                name = newname
            names.append(name)
        if self.dialog.checkStoreProject.isChecked():
            del names[0]
        path_map = dict(zip(paths_set, names))
        
        dstgpkg = '/'.join([self.outdir, self.pj.baseName() + '.gpkg'])
        os.makedirs(self.outdir)

        reg = QgsProviderRegistry.instance()
        tc = self.pj.transformContext()

        self.pd.setMaximum(len(self.src_map))
        self.pd.setValue(self.pd.maximum())
        self.pd.setValue(self.pd.minimum())
        qApp.processEvents()

        for lyr in self.src_map:
            if self.pd.wasCanceled():
                return

            # Store data to GeoPackage
            layername = path_map[self.src_map[lyr]]
            dp = lyr.dataProvider()
            provider = dp.name()
            if not is_layer_in_gpkg(dstgpkg, layername):
                self.pd.setStoringLabel(layername)
                qApp.processEvents()
                err = write_layer(lyr, dstgpkg, tc, layername)
                if err[0]:
                    raise RuntimeError('%s: %s' % (layername, err[1]))
            else:
                self.pd.setLabelText('')
                qApp.processEvents()
            if provider not in ('gdal', 'ogr'):
                provider = 'ogr'

            # Reset data source for layer
            parts = {'path': dstgpkg, 'layerName': layername}
            if provider == 'gdal':
                data_source = 'GPKG:{path}:{layerName}'.format(**parts)
            else:
                data_source = reg.encodeUri(provider, parts)  # QGIS 3.12
            lyr.setDataSource(data_source,
                    lyr.name(), provider,
                    QgsDataProvider.ProviderOptions())

            self.pd.setValue(self.pd.value() + 1)
        
        context = QgsRenderContext.fromMapSettings(
                        self.iface.mapCanvas().mapSettings())
        embed_images_to_project(self.pj, context)


def is_layer_in_gpkg(filename, layerName):
    try:
        ds = gdal.OpenEx(filename)
        res = bool(ds.GetLayerByName(layerName))
    except AttributeError:
        res = False
    finally:
        ds = None
    return res


def write_layer(layer, filename, tc, layerName):
    if layer.type() == QgsMapLayerType.VectorLayer:
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.layerName = layerName
        options.attributes = [idx for idx in layer.attributeList()
                if layer.fields().fieldOrigin(idx) == QgsFields.OriginProvider]
        if os.path.exists(filename):
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        if Qgis.QGIS_VERSION_INT >= 32000:
            write = QgsVectorFileWriter.writeAsVectorFormatV3
        else:
            write = QgsVectorFileWriter.writeAsVectorFormatV2  # QGIS 3.10.3
        err = write(
                layer,
                filename,
                tc,
                options)
    elif layer.type() == QgsMapLayerType.RasterLayer:
        tmp_name = uuid.uuid4().hex  # To avoid character corruption
        dp = layer.dataProvider()
        projector = QgsRasterProjector()
        projector.setCrs(dp.crs(), dp.crs(), tc)
        pipe = QgsRasterPipe()
        pipe.set(dp.clone())
        pipe.insert(2, projector)
        writer = QgsRasterFileWriter(filename)
        writer.setOutputFormat('GPKG')
        writer.setCreateOptions([
                'RASTER_TABLE=%s' % tmp_name, 'APPEND_SUBDATASET=YES'])
        feedback = QgsRasterBlockFeedback()
        err = writer.writeRaster(
                pipe,
                dp.xSize(),
                dp.ySize(),
                dp.extent(),
                dp.crs(),
                tc,
                feedback)
        if not err:
            rename_raster_layer(filename, tmp_name, layerName)
        err = (err, feedback.errors())

    return err


def rename_raster_layer(filename, old_name, new_name):
    with closing(sqlite3.connect(filename, isolation_level=None)) as conn:
        sql = 'ALTER TABLE "{old}" RENAME TO "{new}"'
        conn.execute(sql.format(old=old_name.replace('"', '""'),
                                new=new_name.replace('"', '""')))
        sqls = ["UPDATE gpkg_contents SET table_name = '{new}', identifier = '{new}' WHERE table_name = '{old}'",
                "UPDATE gpkg_tile_matrix SET table_name = '{new}' WHERE table_name = '{old}'",
                "UPDATE gpkg_tile_matrix_set SET table_name = '{new}' WHERE table_name = '{old}'"]
        for sql in sqls:
            conn.execute(sql.format(old=old_name.replace("'", "''"),
                                    new=new_name.replace("'", "''")))
        sqls = ["UPDATE gpkg_2d_gridded_coverage_ancillary SET tile_matrix_set_name = '{new}' WHERE tile_matrix_set_name = '{old}'",
                "UPDATE gpkg_2d_gridded_tile_ancillary SET tpudt_name = '{new}' WHERE tpudt_name = '{old}'"]
        for sql in sqls:
            try:
                conn.execute(sql.format(old=old_name.replace("'", "''"),
                                        new=new_name.replace("'", "''")))
            except sqlite3.OperationalError:
                pass

        trigs = ['%s_zoom_insert',
                '%s_zoom_update',
                '%s_tile_column_insert',
                '%s_tile_column_update',
                '%s_tile_row_insert',
                '%s_tile_row_update',
                ]
        for trig in trigs:
            sql = "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = '%s'"
            cur = conn.execute(sql % (trig % old_name.replace("'", "''")))
            sql = cur.fetchone()[0]

            conn.execute('DROP TRIGGER "%s"' % (trig % old_name.replace('"', '""')))

            mark = uuid.uuid4().hex
            sql = sql.replace(
                    'CREATE TRIGGER "%s' % old_name.replace('"', '""'),
                    'CREATE TRIGGER "%s' % mark)
            sql = sql.replace(
                    ' ON "%s" FOR EACH ROW BEGIN ' % old_name.replace('"', '""'),
                    ' ON "%s" FOR EACH ROW BEGIN ' % mark)
            sql = sql.replace(
                    " on table ''%s'' violates constraint: " % old_name.replace("'", "''"),
                    " on table ''%s'' violates constraint: " % mark)
            sql = sql.replace(
                    " WHERE lower(table_name) = lower('%s')" % old_name.replace("'", "''"),
                    " WHERE lower(table_name) = lower('%s')" % mark)
            sql = sql.replace(mark, new_name.replace('"', '""'), 2)
            sql = sql.replace(mark, new_name.replace("'", "''"))
            conn.execute(sql)
