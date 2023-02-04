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

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import *
from qgis.gui import QgsDialog


class ProjectPackagerDialog(QgsDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        x = self.findChild(QLayout); x.insertLayout(0, x.takeAt(0))  # TRICK

        self.dirEdit = QLineEdit()
        self.dirEdit.setReadOnly(True)
        self.dirEdit.setMinimumWidth(self.fontInfo().pixelSize() * 30)
        self.dirButton = QToolButton()
        self.dirButton.setIcon(QIcon(':/images/themes/default/mActionFileOpen.svg'))
        self.dirButton.clicked.connect(self.dirButton_clicked)
        hbox = QHBoxLayout()
        hbox.addWidget(self.dirEdit)
        hbox.addWidget(self.dirButton)
        form = QFormLayout()
        form.addRow(self.tr('Output folder'), hbox)

        self.radiosMethod = [
                QRadioButton(self.tr('Copy original data files')),
                QRadioButton(self.tr('Store data in GeoPackage'))
        ]
        self.radiosMethod[0].setChecked(True)
        self.checkVacuum = QCheckBox(self.tr('Vacuum SQLite-based files after copying'))
        self.checkStoreProject = QCheckBox(self.tr('Store project in GeoPackage'))

        grid = QGridLayout()
        grid.addWidget(self.radiosMethod[0], 0, 0, 1, 0)
        grid.addWidget(self.checkVacuum, 1, 1)
        grid.addWidget(self.radiosMethod[1], 2, 0, 1, 0)
        grid.addWidget(self.checkStoreProject, 3, 1)
        grid.setColumnMinimumWidth(0, QRadioButton().sizeHint().width())
        groupMethod = QGroupBox(self.tr('Data storage method'))
        groupMethod.setLayout(grid)

        buttonBox = self.buttonBox()
        buttonBox.setStandardButtons(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        vbox = self.layout()
        vbox.addLayout(form)
        vbox.addWidget(groupMethod)

        self.setMaximumHeight(0)

    def dirButton_clicked(self):
        res = QFileDialog.getExistingDirectory(self, directory=self.dirEdit.text())
        if res:
            self.dirEdit.setText(res)

    def get_method(self):
        for i, w in enumerate(self.radiosMethod):
            if w.isChecked():
                return i

    def set_gpkg_enabled(self, b):
        self.radiosMethod[1].setEnabled(b)
        self.checkStoreProject.setEnabled(b)
        if b == False:
            self.radiosMethod[0].setChecked(True)


class ProgressDialog(QProgressDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setAutoReset(False)
        self.setMinimumDuration(0)
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumWidth(self.fontInfo().pixelSize() * 30)

    def setCopyingLabel(self, basename):
        self.setLabelText(self.tr('Copying: %s') % basename)

    def setVacuumingLabel(self, basename):
        self.setLabelText(self.tr('Vacuuming: %s') % basename)

    def setStoringLabel(self, layername):
        self.setLabelText(self.tr('Storing: %s') % layername)


if __name__ == '__main__':
    app = QApplication([])
    ProjectPackagerDialog().exec()
