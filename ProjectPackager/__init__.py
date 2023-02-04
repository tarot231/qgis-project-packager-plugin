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
from qgis.PyQt.QtCore import (QObject, QTranslator, QLocale, QDir, QUrl,
        QStandardPaths, QXmlStreamReader)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import qApp, QAction, QMessageBox, QDialog
from qgis.core import QgsApplication, QgsProject, QgsProviderRegistry, QgsMapLayerType
from .ui import ProjectPackagerDialog, ProgressDialog
from .toDirectory import ToDirectory
from .toGPKG import ToGPKG


class StorageMethod:
    (
        COPY,
        GPKG,
    ) = range(2)


# https://stackoverflow.com/q/3812849
def is_in_dir(parent, child):
    parent = os.path.abspath(parent)
    child = os.path.abspath(child)
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        return False


class ProjectPackager(QObject, ToDirectory, ToGPKG):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.translator = QTranslator()
        if self.translator.load(QLocale(QgsApplication.locale()),
                '', '', os.path.join(os.path.dirname(__file__), 'i18n')):
            qApp.installTranslator(self.translator)

    def initGui(self):
        self.pj = QgsProject.instance()
        self.mw = self.iface.mainWindow()
        self.mb = self.iface.messageBar()
        self.plugin_name = self.tr('Project Packager')
        self.plugin_act = QAction(
                QIcon(os.path.join(os.path.dirname(__file__), 'icon.png')),
                self.plugin_name, self.mw)
        self.plugin_act.setObjectName('mActionProjectPackager')
        self.plugin_act.triggered.connect(self.run)

        self.mw.windowTitleChanged.connect(self.filename_changed)
        self.filename_changed()

        self.dialog = ProjectPackagerDialog(parent=self.mw)
        self.dialog.setWindowTitle(self.plugin_name)

        self.iface.addToolBarIcon(self.plugin_act)
        self.iface.addPluginToMenu(self.plugin_name, self.plugin_act)

    def unload(self):
        self.iface.removePluginMenu(self.plugin_name, self.plugin_act)
        self.iface.removeToolBarIcon(self.plugin_act)
        self.mw.windowTitleChanged.disconnect(self.filename_changed)

    def filename_changed(self):
        self.plugin_act.setEnabled(bool(QgsProject.instance().fileName()))

    def get_sourceinfo(self, lyr):
        dp = lyr.dataProvider()
        if dp is None:
            return None
        d = QgsProviderRegistry.instance().decodeUri(dp.name(), lyr.source())  # QGIS 3.4
        path = d.get('path')
        if path:  # required. QDir(None or '').canonicalPath() returns home path 
            path = QDir(path).canonicalPath()  # '' if invalid
        layername = d.get('layerName')
        options = None
        if dp.name() == 'delimitedtext':
            options = d.get('openOptions')
            if isinstance(options, list):
                options = str(options)
        elif lyr.source().startswith('/vsi'):
            options = d.get('vsiSuffix')
        if path:
            if not layername and path.lower().endswith('.gpkg'):
                # GeoPackage raster  # TODO: replace with smarter way
                reader = QXmlStreamReader(lyr.htmlMetadata())
                while not reader.atEnd():
                    text = reader.text()
                    l = text.split('=', 1)
                    if len(l) == 2 and l[0] == 'IDENTIFIER':
                        layername = l[1]
                        break
                    reader.readNext()
            return path, layername, options
        return None

    def run(self):
        if self.pj.isDirty():
            self.mb.pushWarning(self.plugin_name, self.tr(
                    'The project has been modified. Please save it and try again.'))
            return

        if not os.path.exists(self.dialog.dirEdit.text()):
            self.dialog.dirEdit.setText(
                    QStandardPaths.standardLocations(
                            QStandardPaths.DocumentsLocation)[0])
        
        try:
            enable_gpkg = True
            self.src_map = {}
            for lyr in self.pj.mapLayers().values():
                info = self.get_sourceinfo(lyr)
                if info:  # Ignore non-file-based data
                    self.src_map[lyr] = info
                    if lyr.type() not in (QgsMapLayerType.VectorLayer, QgsMapLayerType.RasterLayer):
                        enable_gpkg = False
        except Exception as e:
            self.mb.pushCritical(self.plugin_name, str(e))
            return
        self.dialog.set_gpkg_enabled(enable_gpkg)

        res = self.dialog.exec()
        if res == QDialog.Rejected:
            return

        home = self.pj.homePath()
        if home.startswith('geopackage:'):
            home = home[11:]
        self.outdir = '/'.join([self.dialog.dirEdit.text(), self.pj.baseName()])
        if is_in_dir(home, self.outdir):
            self.mb.pushWarning(self.plugin_name, self.tr(
                    'The output folder cannot be in the project home.'))
            return
        if os.path.exists(self.outdir):
            res = QMessageBox.question(self.mw, self.plugin_name, self.tr(
                    "The data in the existing folder '%s' will be lost. Are you sure you want to continue?")
                    % self.outdir)
            if res != QMessageBox.Yes:
                return
            try:
                shutil.rmtree(self.outdir)
            except Exception as e:
                self.mb.pushCritical(self.plugin_name, str(e))
                return

        orig_project = self.pj.fileName()
        res = None
        try:
            self.pd = ProgressDialog(self.mw)
            self.pd.setWindowTitle(self.plugin_name)

            method = self.dialog.get_method()
            if method == StorageMethod.COPY:
                self.copyOriginalData()
            else:
                self.storeDataToGPKG()
            
            if not self.pd.wasCanceled():
                self.pd.setValue(self.pd.maximum())
                self.pd.setLabelText(self.tr('Writing project...'))
                qApp.processEvents()

                self.pj.setPresetHomePath('')
                self.pj.writeEntryBool('Paths', '/Absolute', False)
                path = QDir(os.path.join(self.outdir, self.pj.baseName())
                        ).absolutePath()
                if (method == StorageMethod.GPKG and
                        self.dialog.checkStoreProject.isChecked()):
                    # https://gis.stackexchange.com/q/368285
                    filename = ('geopackage:%s.gpkg?projectName=%s' %
                            (path, self.pj.baseName()))
                else:
                    filename = '%s.qgz' % path
                res = self.pj.write(filename)
        except Exception as e:
            self.mb.pushCritical(self.plugin_name, str(e))
            return
        finally:
            self.pd.hide()
            self.pd.deleteLater()
            self.mb.widgetAdded.connect(self.mb.popWidget)
            self.pj.read(orig_project)
            self.mb.widgetAdded.disconnect(self.mb.popWidget)

        if res:
            self.mb.pushSuccess(self.plugin_name, self.tr(
                    'Successfully exported project to %s')
                    % ('<a href="%s">%s</a>'
                    % (QUrl.fromLocalFile(self.outdir).toEncoded().data().decode(),
                       self.outdir)))


def classFactory(iface):
    return ProjectPackager(iface)
