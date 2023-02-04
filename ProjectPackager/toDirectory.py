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
import shutil
import sqlite3
from contextlib import closing
from osgeo import gdal
from qgis.PyQt.QtCore import QDir
from qgis.PyQt.QtWidgets import qApp
from qgis.core import QgsDataProvider, QgsProviderRegistry


class ToDirectory(object):
    def copyOriginalData(self):
        # Organize target names
        paths_set = list(set(path for path, _, _ in self.src_map.values()))
        dirs = [os.path.dirname(x) for x in paths_set]
        path_map = dict(zip(paths_set, dirs))
        
        dirs_set = list(set(dirs))
        bases = [os.path.basename(x) for x in dirs_set]
        names = []
        names.append(self.pj.baseName() + '.qgz')
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
        del names[0]
        dir_map = dict(zip(dirs_set, names))
        path_map = {path: dir_map[path_map[path]] for path in paths_set}

        self.pd.setMaximum(len(path_map))
        self.pd.setValue(self.pd.maximum())
        self.pd.setValue(self.pd.minimum())
        qApp.processEvents()

        # Copy data files
        for path in path_map:
            if self.pd.wasCanceled():
                return
            
            dstdir = os.path.join(self.outdir, path_map[path])
            try:
                os.makedirs(dstdir)
            except FileExistsError:
                pass
            try:
                ds = gdal.OpenEx(path)
                fl = ds.GetFileList()
            except AttributeError:
                fl = [path]  # for vsifile
            finally:
                ds = None
            for filepath in fl:
                self.pd.setCopyingLabel(os.path.basename(filepath))
                qApp.processEvents()
                try:
                    shutil.copy2(filepath, dstdir)
                except FileNotFoundError:
                    pass
                # Vacuum
                if self.dialog.checkVacuum.isChecked():
                    try:
                        filename = os.path.join(dstdir, os.path.basename(filepath))
                        with open(filename, 'rb') as f:
                            header = f.read(16)
                        if header == b'SQLite format 3\000':
                            self.pd.setVacuumingLabel(os.path.basename(filename))
                            qApp.processEvents()
                            with closing(sqlite3.connect(filename)) as conn:
                                conn.execute('VACUUM')
                    except:
                        pass

            self.pd.setValue(self.pd.value() + 1)

        self.pd.setLabelText('')
        qApp.processEvents()

        # Reset data source for layer
        reg = QgsProviderRegistry.instance()
        for lyr, src in self.src_map.items():
            if src is None:
                continue
            path, _, _ = src
            dp = lyr.dataProvider()
            parts = reg.decodeUri(dp.name(), lyr.source())
            parts['path'] = QDir(os.path.join(self.outdir,
                    path_map[path], os.path.basename(path))).absolutePath()
            data_source = reg.encodeUri(dp.name(), parts)  # QGIS 3.12
            lyr.setDataSource(data_source,
                    lyr.name(), lyr.providerType(),
                    QgsDataProvider.ProviderOptions())
