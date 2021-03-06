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
from qgis.PyQt.QtGui import QIcon, QFont, QFontMetrics
from qgis.PyQt.QtWidgets import *


class FolderNaming:
    (
        NUM_ONLY,
        NUM_FOLDER,
        ORIGINAL,
    ) = range(3)


class ProjectPackagerDialog(QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.dirEdit = QLineEdit()
        self.dirEdit.setReadOnly(True)
        self.dirEdit.setMinimumWidth(QFontMetrics(QFont()).height() * 28)
        self.dirButton = QToolButton()
        self.dirButton.setIcon(QIcon(':/images/themes/default/mActionFileOpen.svg'))
        self.dirButton.clicked.connect(self.dirButton_clicked)
        hbox = QHBoxLayout()
        hbox.addWidget(self.dirEdit)
        hbox.addWidget(self.dirButton)
        form = QFormLayout()
        form.addRow(self.tr('Output folder'), hbox)

        self.radiosNaming = []
        self.radiosNaming += [QRadioButton(self.tr('Number only'))]
        self.radiosNaming += [QRadioButton(self.tr('Number and folder name'))]
        self.radiosNaming += [QRadioButton(self.tr('Original folder name (append underscores for duplicates)'))]
        self.radiosNaming[0].setChecked(True)
        vbox = QVBoxLayout()
        for w in self.radiosNaming:
            vbox.addWidget(w)
        groupNaming = QGroupBox(self.tr('Folder name outside the project home (copied in the _EXTRA folder)'))
        groupNaming.setLayout(vbox)

        buttonBox = QDialogButtonBox(
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
                accepted=self.accept, rejected=self.reject)

        vbox = QVBoxLayout()
        vbox.addLayout(form)
        vbox.addWidget(groupNaming)
        vbox.addWidget(buttonBox)

        self.setLayout(vbox)
        self.setMaximumHeight(0)

    def dirButton_clicked(self):
        res = QFileDialog.getExistingDirectory(self, directory=self.dirEdit.text())
        if res:
            self.dirEdit.setText(res)

    def get_folderNaming(self):
        for i, w in enumerate(self.radiosNaming):
            if w.isChecked():
                return i


class ProgressDialog(QProgressDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setAutoReset(False)
        self.setMinimumDuration(0)
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumWidth(QFontMetrics(QFont()).height() * 30)


if __name__ == '__main__':
    app = QApplication([])
    w = ProjectPackagerDialog()
    w.exec()
