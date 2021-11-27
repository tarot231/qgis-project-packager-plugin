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
from osgeo import gdal
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import Qgis, QgsApplication, QgsProject, QgsDataProvider
from .ProjectPackagerUI import ProjectPackagerDialog, ProgressDialog


class ProjectPackager(QObject):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.translator = QTranslator()
        if self.translator.load(QLocale(QgsApplication.locale()),
                '', '', os.path.join(os.path.dirname(__file__), 'i18n')):
            qApp.installTranslator(self.translator)

    def initGui(self):
        self.mw = self.iface.mainWindow()
        self.plugin_name = self.tr('Project Packager')
        self.plugin_act = QAction(
                QIcon(os.path.join(os.path.dirname(__file__), 'icon.png')),
                self.plugin_name, self.mw)
        self.plugin_act.setObjectName("mActionProjectPackager")
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

    def run(self):
        project = QgsProject.instance()

        if project.projectStorage():
            QMessageBox.warning(self.mw, self.plugin_name, self.tr(
                    'The project stored in a project storage is not supported.'))
            return
        if project.isDirty():
            QMessageBox.warning(self.mw, self.plugin_name, self.tr(
                    'The project has been modified. Please save it and try again.'))
            return

        if not os.path.exists(self.dialog.dirEdit.text()):
            self.dialog.dirEdit.setText(
                    QStandardPaths.standardLocations(
                            QStandardPaths.DocumentsLocation)[0])

        res = self.dialog.exec()
        if res == QDialog.Rejected:
            return

        outdir = os.path.join(
                self.dialog.dirEdit.text(), project.baseName())
        home = project.homePath()

        # https://stackoverflow.com/q/3812849
        def is_in_dir(parent, child):
            parent = os.path.abspath(parent)
            child = os.path.abspath(child)
            try:
                return os.path.commonpath([parent, child]) == parent
            except ValueError:
                return False

        if is_in_dir(home, outdir):
            QMessageBox.warning(self.mw, self.plugin_name, self.tr(
                    'The output directory cannot be in the project home.'))
            return

        if os.path.exists(outdir):
            res = QMessageBox.question(self.mw, self.plugin_name, self.tr(
                    "The data in the existing directory '%s' will be lost. Are you sure you want to continue?")
                    % outdir)
            if res != QMessageBox.Yes:
                return
            try:
                shutil.rmtree(outdir)
            except Exception as e:
                QMessageBox.critical(self.mw, self.plugin_name, str(e))
                return
        try:
            os.makedirs(outdir)
        except Exception as e:
            QMessageBox.critical(self.mw, self.plugin_name, str(e))
            return

        project_file = project.fileName()
        lyrs = project.mapLayers().values()
        srcs = {lyr: lyr.source().split('|')[0] for lyr in lyrs}
        for lyr, src in srcs.items():
            if src.startswith('file:'):
                srcs[lyr] = QUrl(src).toLocalFile()
            if not os.path.exists(srcs[lyr]):
                srcs[lyr] = None

        extras = sorted(set(os.path.dirname(p) for p in srcs.values()
                if p and not is_in_dir(home, p)))
        extra_name = '_EXTRA'
        while os.path.exists(os.path.join(home, extra_name)):
            extra_name = '_' + extra_name

        pd = ProgressDialog(self.mw)
        pd.setMaximum(len(lyrs))
        pd.setWindowTitle(self.plugin_name)

        res = None
        try:
            for lyr in lyrs:
                if pd.wasCanceled():
                    break
                pd.setValue(pd.value() + 1)

                if srcs[lyr] is None:
                    continue
                fl = [srcs[lyr]]
                if lyr.providerType() in ('gdal', 'ogr'):
                    try:
                        ds = gdal.OpenEx(srcs[lyr])
                        fl = ds.GetFileList()
                    finally:
                        ds = None

                srcdir = os.path.dirname(fl[0])
                try:
                    idx = extras.index(srcdir)
                    rel = os.path.join(extra_name, '%03d' % idx)
                except ValueError:
                    rel = os.path.relpath(srcdir, home)

                dstdir = os.path.join(outdir, rel)
                try:
                    os.makedirs(dstdir)
                except FileExistsError:
                    pass

                for p in fl:
                    try:
                        pd.setLabelText(self.tr(
                                'Copying: %s') % os.path.basename(p))
                        qApp.processEvents()
                        shutil.copy2(p, dstdir)
                    except FileNotFoundError as e:
                        pass

                if lyr.source().startswith('file:'):
                    srcdir = QUrl.fromLocalFile(
                            srcdir
                            ).toEncoded().data().decode()
                    dstdir = QUrl.fromLocalFile(
                            os.path.abspath(dstdir)
                            ).toEncoded().data().decode()

                lyr.setDataSource(lyr.source().replace(srcdir, dstdir),
                                  lyr.name(), lyr.providerType(),
                                  QgsDataProvider.ProviderOptions())

            if not pd.wasCanceled():
                pd.setValue(len(lyrs))
                pd.setLabelText(self.tr('Writing project file...'))
                qApp.processEvents()
                rel = os.path.relpath(home, project.absolutePath())
                rev = ''
                if rel.startswith('.'):
                    rev = os.path.relpath(project.absolutePath(), home)
                    project.setPresetHomePath(rel)
                project.writeEntryBool('Paths', '/Absolute', False)
                res = project.write(os.path.join(
                        outdir, rev, os.path.basename(project_file)))

        except Exception as e:
            QMessageBox.critical(self.mw, self.plugin_name, str(e))

        finally:
            pd.hide()
            pd.deleteLater()
            mb = self.iface.messageBar()
            mb.widgetAdded.connect(mb.popWidget)
            project.read(project_file)
            mb.widgetAdded.disconnect(mb.popWidget)

        if res:
            mb.pushSuccess(self.plugin_name, self.tr(
                    'Successfully exported project to %s') % outdir)
