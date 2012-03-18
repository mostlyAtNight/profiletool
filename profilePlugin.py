# -*- coding: utf-8 -*-
#-----------------------------------------------------------
# 
# Profile
# Copyright (C) 2008  Borys Jurgiel
# Copyright (C) 2012  Patrice Verchere
#-----------------------------------------------------------
# 
# licensed under the terms of GNU GPL 2
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along
# with this progsram; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
# 
#---------------------------------------------------------------------

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *

#from selectPointTool import *
import resources
import tools
from tools.ui_profiletool2 import ui_ProfileTool2
from tools.doProfile import DoProfile

class profilePlugin:

	def __init__(self, iface):
		self.iface = iface
		self.canvas = iface.mapCanvas()


	def initGui(self):
		# create action 
		self.action = QAction(QIcon(":/plugins/profiletool/icons/profileIcon.png"), "Terrain profile", self.iface.mainWindow())
		self.action.setWhatsThis("Plots terrain profiles")
		QObject.connect(self.action, SIGNAL("triggered()"), self.run)
		# add toolbar button and menu item
		self.iface.addToolBarIcon(self.action)
		self.iface.addPluginToMenu("&Analyses", self.action)
		#Init classe variables
		self.tool = tools.selectPointTool.selectPointTool(self.iface.mapCanvas(),self.action)		#the mouselistener
		self.dockOpened = False		#remember for not reopening dock if there's already one opened
		#self.layerlist = []			#layers which are analysed
		self.pointstoDraw = None	#Polyline in mapcanvas CRS analysed
		self.dblclktemp = None		#enable disctinction between leftclick and doubleclick
		self.mdl = None				#the model whitch in are saved layers analysed caracteristics


	def unload(self):
		self.iface.removePluginMenu("&Analyses",self.action)
		self.iface.removeToolBarIcon(self.action)


	def run(self):
		# first, check posibility
		ver = str(QGis.QGIS_VERSION)
		if ver[0] == "0" and ((ver[2] != "1") or (ver[3] != "1")):		#Check qgis version
			QMessageBox.warning(self.iface.mainWindow(), "Profile", "Quantum GIS version detected: "+ver+"\nProfile plugin requires version at least 0.11")
			return 1
		if self.iface.mapCanvas().layerCount() == 0:					#Check a layer is opened
			QMessageBox.warning(self.iface.mainWindow(), "Profile", "First open any raster layer, please")
			return 2
		layer = self.iface.activeLayer()
		if layer == None or layer.type() != layer.RasterLayer :			#Check if a raster layer is opened and selectionned
			QMessageBox.warning(self.iface.mainWindow(), "Profile", "Please select one raster layer")
			#self.choosenBand = 0
			return 3
		
		#if dock not already opened, open the dock and all the necessary thing (model,doProfile...)
		if self.dockOpened == False : 
			self.dockOpened = True
			self.wdg = ui_ProfileTool2(self.iface.mainWindow(), self.iface)
			#Deal with dockwidget properties
			self.wdg.setLocation( Qt.BottomDockWidgetArea )
			minsize = self.wdg.minimumSize()
			maxsize = self.wdg.maximumSize()
			self.wdg.setMinimumSize(minsize)
			self.wdg.setMaximumSize(maxsize)
			self.iface.mapCanvas().setRenderFlag(False)
			self.iface.addDockWidget(self.wdg.getLocation(), self.wdg)
			QObject.connect(self.wdg, SIGNAL( "closed(PyQt_PyObject)" ), self.cleaning2)
			QObject.connect(self.wdg.butPrint, SIGNAL("clicked()"), self.outPrint)
			QObject.connect(self.wdg.butPDF, SIGNAL("clicked()"), self.outPDF)
			QObject.connect(self.wdg.butSVG, SIGNAL("clicked()"), self.outSVG)
			if QT_VERSION >= 0X040100:
				self.wdg.butPDF.setEnabled(True)
			if QT_VERSION >= 0X040300:
				self.wdg.butSVG.setEnabled(True)
			#init the doProfile class
			self.doprofile = DoProfile(self.iface,self.wdg,self.tool)
			#Deal with model properties - that 's where the layers to be analysed are saved
			self.mdl = QStandardItemModel(0, 5)
			self.wdg.tableView.setModel(self.mdl)
			self.wdg.tableView.setColumnWidth(0, 20)
			self.wdg.tableView.setColumnWidth(1, 20)
			self.wdg.tableView.setColumnWidth(2, 150)
			hh = self.wdg.tableView.horizontalHeader()
			hh.setStretchLastSection(True)
			self.wdg.tableView.setColumnHidden(4 , True)
			self.mdl.setHorizontalHeaderLabels(["","","Layer","Band"])
			QObject.connect(self.wdg.tableView,SIGNAL("clicked(QModelIndex)"), self._onClick) 
			self.iface.mapCanvas().setRenderFlag(True)
			#Listener add raster
			QObject.connect(self.wdg.pushButton_2, SIGNAL("clicked()"), self.addLayer)
			#Add the selctionned raster to model
			self.addLayer(self.iface.activeLayer())		
			
		#Listeners of mouse
		QObject.connect(self.tool, SIGNAL("moved"), self.moved)
		QObject.connect(self.tool, SIGNAL("rightClicked"), self.rightClicked)
		QObject.connect(self.tool, SIGNAL("leftClicked"), self.leftClicked)
		QObject.connect(self.tool, SIGNAL("doubleClicked"), self.doubleClicked)

		#init the mouse listener comportement and save the classic to restore it on quit
		self.saveTool = self.canvas.mapTool()
		self.canvas.setMapTool(self.tool)
		#init the temp layer where the polyline is draw
		self.polygon = False
		self.rubberband = QgsRubberBand(self.canvas, self.polygon)
		#init the table where is saved the poyline
		self.pointstoDraw = []
		self.pointstoCal = []
		self.lastClicked = [[-9999999999.9,9999999999.9]]
		self.iface.mainWindow().statusBar().showMessage(QString("Select starting and ending point"))

	#************************* Mouse listener actions ***********************************************

	def moved(self,position):			#draw the polyline on the temp layer (rubberband)
		if len(self.pointstoDraw) > 0:
			#Get mouse coords
			mapPos = self.canvas.getCoordinateTransform().toMapCoordinates(position["x"],position["y"])
			#Draw on temp layer
			self.rubberband.reset(self.polygon)
			for i in range(0,len(self.pointstoDraw)):
 				self.rubberband.addPoint(QgsPoint(self.pointstoDraw[i][0],self.pointstoDraw[i][1]))
			self.rubberband.addPoint(QgsPoint(mapPos.x(),mapPos.y()))


	def rightClicked(self,position):	#used to quit the current action
		mapPos = self.canvas.getCoordinateTransform().toMapCoordinates(position["x"],position["y"])
		newPoints = [[mapPos.x(), mapPos.y()]]
		if newPoints == self.lastClicked: return # sometimes a strange "double click" is given
		if len(self.pointstoDraw) > 0:
			self.pointstoDraw = []
			self.pointstoCal = []
			self.rubberband.reset(self.polygon)
		else:
			self.cleaning()
			self.lastClicked = newPoints


	def leftClicked(self,position):		#Add point to analyse
		mapPos = self.canvas.getCoordinateTransform().toMapCoordinates(position["x"],position["y"])
		newPoints = [[mapPos.x(), mapPos.y()]]
		if newPoints == self.dblclktemp:
			return
		else :
			self.pointstoDraw += newPoints
   
	def doubleClicked(self,position):
		#Validation of line
		mapPos = self.canvas.getCoordinateTransform().toMapCoordinates(position["x"],position["y"])
		newPoints = [[mapPos.x(), mapPos.y()]]
		self.pointstoDraw += newPoints
		#launch analyses
		self.doprofile.calculateProfil(self.pointstoDraw,self.mdl)
		#Reset
		self.rubberband.reset(self.polygon)
		self.pointstoDraw = []
		#temp point to distinct leftclick and dbleclick
		self.dblclktemp = newPoints

	#***************************** Quit functions *******************************************
	
	def cleaning(self):			#used on right click
		QObject.disconnect(self.tool, SIGNAL("moved"), self.moved)
		QObject.disconnect(self.tool, SIGNAL("leftClicked"), self.leftClicked)
		QObject.disconnect(self.tool, SIGNAL("rightClicked"), self.rightClicked)
		QObject.disconnect(self.tool, SIGNAL("doubleClicked"), self.doubleClicked)
		self.canvas.setMapTool(self.saveTool)
		self.rubberband.reset(self.polygon)
		self.points = []
		self.iface.mainWindow().statusBar().showMessage(QString(""))


	def cleaning2(self):		#used when Dock dialog is closed
		self.mdl = None
		self.dockOpened = False
		self.cleaning()

	#************************* tableview function ******************************************

	def addLayer(self , layer1 = None):
		if layer1 == None:
			templist=[]
			tempdico=[]
			j=0
			# Ask the layer by a input dialog - there is certainly a way to simplify this..
			for i in range(0,self.iface.mapCanvas().layerCount()):
				layer = self.iface.mapCanvas().layer(i)
				if layer.type() == layer.RasterLayer:
					tempdico += [{"layer": layer , "layername" : layer.name()}]
			testqt, ok = QInputDialog.getItem(self.iface.mainWindow(), "Layer selector", "Choose layer", [tempdico[j]["layername"] for j in range(0,len(tempdico))], False)
			if ok:
				for i in range (0,len(tempdico)):
					if tempdico[i]["layername"] == testqt:
						layer2 = tempdico[i]["layer"]
			else: return
		else : 
			layer2 = layer1

		# Ask the Band by a input dialog
		if layer2.bandCount() != 1:
			listband = []
			for i in range(0,layer2.bandCount()):
				listband.append(str(i+1))
			testqt, ok = QInputDialog.getItem(self.iface.mainWindow(), "Band selector", "Choose the band", listband, False)
			if ok :
				choosenBand = int(testqt) - 1
			else:
				return 2
		else:
			choosenBand = 0

		#Complete the tableview
		row = self.mdl.rowCount()
		self.mdl.insertRow(row)
		self.mdl.setData( self.mdl.index(row, 0, QModelIndex())  ,QVariant(True), Qt.CheckStateRole)
		self.mdl.item(row,0).setFlags(Qt.ItemIsSelectable) 
		self.mdl.setData( self.mdl.index(row, 1, QModelIndex())  ,QVariant(QColor(Qt.red)) , Qt.BackgroundRole)
		self.mdl.item(row,1).setFlags(Qt.NoItemFlags) 
		self.mdl.setData( self.mdl.index(row, 2, QModelIndex())  ,QVariant(layer2.name()))
		self.mdl.item(row,2).setFlags(Qt.NoItemFlags) 
		self.mdl.setData( self.mdl.index(row, 3, QModelIndex())  ,QVariant(choosenBand + 1))
		self.mdl.item(row,3).setFlags(Qt.NoItemFlags) 
		self.mdl.setData( self.mdl.index(row, 4, QModelIndex())  ,layer2)
		self.mdl.item(row,4).setFlags(Qt.NoItemFlags) 


	def _onClick(self,index1):					#action when clicking the tableview
		temp = self.mdl.itemFromIndex(index1)
		if index1.column() == 1:				#modifying color
			color = QColorDialog().getColor(temp.data(Qt.BackgroundRole).toPyObject())
			self.mdl.setData( self.mdl.index(temp.row(), 1, QModelIndex())  ,QVariant(color) , Qt.BackgroundRole)
			self.doprofile.changeColor(color,temp.row())
		elif index1.column() == 0:				#modifying checkbox
			booltemp = temp.data(Qt.CheckStateRole).toPyObject()
			if booltemp == True:
				booltemp = False
			else:
				booltemp = True
			self.mdl.setData( self.mdl.index(temp.row(), 0, QModelIndex())  ,QVariant(booltemp), Qt.CheckStateRole)
			self.doprofile.changeattachcurve(booltemp,temp.row())
		else:
			return

	#******************************** Button of Dock for printing ****************************************

	def outPrint(self): # Postscript file rendering doesn't work properly yet.
		for i in range (0,self.mdl.rowCount()):
			if  model1.item(i,0).data(Qt.CheckStateRole).toPyObject():
				name = str(model1.item(i,2).data(Qt.EditRole).toPyObject())
				return
		fileName = "Profile of " + name + ".ps"
		printer = QPrinter()
		printer.setCreator("QGIS Profile Plugin")
		printer.setDocName("QGIS Profile")
		printer.setOutputFileName(fileName)
		printer.setColorMode(QPrinter.Color)
		printer.setOrientation(QPrinter.Portrait)
		dialog = QPrintDialog(printer)
		if dialog.exec_():
			self.wdg.qwtPlot.print_(printer)


	def outPDF(self):
		for i in range (0,self.mdl.rowCount()):
			if  model1.item(i,0).data(Qt.CheckStateRole).toPyObject():
				name = str(model1.item(i,2).data(Qt.EditRole).toPyObject())
				return
		fileName = QFileDialog.getSaveFileName(self.iface.mainWindow(), "Save As","Profile of " + name + ".pdf","Portable Document Format (*.pdf)")
		if not fileName.isEmpty():
			printer = QPrinter()
			printer.setCreator('QGIS Profile Plugin')
			printer.setOutputFileName(fileName)
			printer.setOutputFormat(QPrinter.PdfFormat)
			printer.setOrientation(QPrinter.Landscape)
			self.wdg.qwtPlot.print_(printer)

	def outSVG(self):
		for i in range (0,self.mdl.rowCount()):
			if  model1.item(i,0).data(Qt.CheckStateRole).toPyObject():
				name = str(model1.item(i,2).data(Qt.EditRole).toPyObject())
				return
		fileName = QFileDialog.getSaveFileName(self.iface.mainWindow(), "Save As","Profile of " + name + ".svg","Scalable Vector Graphics (*.svg)")
		if not fileName.isEmpty():
			printer = QSvgGenerator()
			printer.setFileName(fileName)
			printer.setSize(QSize(800, 400))
			self.wdg.qwtPlot.print_(printer)


